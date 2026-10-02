"""UW Rec's own bookings (IM leagues, club practices, rentals), copied in automatically once a day.

UW Recreation's public Facility Schedule (https://reg.recreation.uw.edu/Facility/GetSchedule) loads each space's
bookings as JSON. For the places our games use (UW_REC_SPACES), we read the next few weeks, turn weekly repeats
into single dates, and save them in rec_reservations with source 'feed', replacing the previous copy. Bookings an
admin typed in (source 'admin') are never touched. If UW Rec's site is down, yesterday's copy stays.

    flask --app wsgi sync-uw-rec     # run it now
"""
import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import click
from flask import current_app
from flask.cli import with_appcontext

from .db import get_db
from .timeutil import SEATTLE, now_local, to_db

log = logging.getLogger(__name__)

SITE = "https://reg.recreation.uw.edu"
DAYS_AHEAD = 28
MAX_LABEL = 80

# Our place -> UW Rec's spaces there (names as UW Rec lists them; a space's parts like "Field A" count too).
UW_REC_SPACES = {
    "Denny Field": ["Denny Field - Turf"],
    "Recreation Field 1 (by the IMA)": ["Rec Field #1 - Turf"],
    "Recreation Field 2 (by Husky Track)": ["Rec Field #2 - Grass"],
    "Recreation Field 3 (by the golf range)": ["Rec Field #3 - Turf"],
    "Recreation Field 4 (by the golf range)": ["Rec Field #4 - Grass"],
    "IMA North Tennis Courts": ["Tennis North Courts", "TN North Court"],
    "IMA South Tennis Courts": ["Tennis South Courts", "TN South Court"],
    "IMA (Intramural Activities Building)": ["Gym A", "Gym B", "Gym C", "Gym D", "Gym Pariseau"],
}
DAY_CODES = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _get(path, params=None, tries=2):
    """One page from UW Rec's site. A slow moment gets one more try after 5 seconds."""
    url = SITE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    request = urllib.request.Request(url, headers={"User-Agent": "SportiveCircle/1.0 (UW student project)",
                                                   "Accept": "application/json, text/html"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.read().decode("utf-8", "replace")
        except OSError:
            if attempt == tries - 1:
                raise
            time.sleep(5)


def facility_ids():
    """{UW Rec space name: its id}, read from the public Search Facilities page (ids can change)."""
    page = _get("/Facility")
    found = re.findall(r'facilityId=([0-9a-f-]{36})"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{2,80})', page)
    return {name.strip().replace("&#39;", "'").replace("&amp;", "&"): fid for fid, name in found}


def _local(text):
    """"2026-10-01T18:00:00.000" (UW Rec's local time) or "20261218T040000Z" (UTC) -> Seattle time, no tzinfo."""
    text = str(text).strip()
    if "-" in text[:10]:  # ISO: "2026-10-01T18:00:00.000", maybe ending in "Z" or "+00:00" (then not Seattle time)
        when = datetime.fromisoformat(text[:19])
        offset = re.search(r"(Z|[+-]\d\d:?\d\d)$", text[19:])
        if not offset:
            return when
        sign, digits = offset.group(1)[:1], offset.group(1).lstrip("+-").replace(":", "")
        delta = timedelta(0) if sign == "Z" else timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        utc = when - delta if sign != "-" else when + delta
        return utc.replace(tzinfo=timezone.utc).astimezone(SEATTLE).replace(tzinfo=None)
    if text.endswith("Z"):
        return datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(SEATTLE) \
            .replace(tzinfo=None)
    return datetime.strptime(text[:15], "%Y%m%dT%H%M%S")


class UnreadableRule(ValueError):
    """A repeat rule we don't fully understand: the booking is left out (and reported) rather than guessed."""


READABLE_RULE_PARTS = {"FREQ", "UNTIL", "COUNT", "INTERVAL", "BYDAY", "WKST"}
MAX_LENGTH = timedelta(hours=24)   # up to all day (tournaments); longer is reported, not guessed
PAUSE_SECONDS = 1.0                # between requests, to go easy on UW Rec's site
DROP_LIMIT = 0.5                   # a new copy with less than half of yesterday's bookings is suspicious
RUNNING = threading.Lock()


def occurrences(item, until):
    """Every (start, end) of one booking up to `until`, with weekly/daily repeats expanded and exceptions left out.
    Raises UnreadableRule for repeat rules beyond plain daily/weekly ones (monthly, "2nd Tuesday"...)."""
    start, end = _local(item["StartDate"]), _local(item["EndDate"])
    text = item.get("RecurrenceRule") or ""
    if not text:
        return [(start, end)]
    rule = dict(part.split("=", 1) for part in text.split(";") if "=" in part)
    days_text = [d for d in rule.get("BYDAY", "").split(",") if d]
    if (set(rule) - READABLE_RULE_PARTS or rule.get("FREQ") not in ("DAILY", "WEEKLY")
            or any(d not in DAY_CODES for d in days_text)):
        raise UnreadableRule(text)
    skipped = {_local(t) for t in (item.get("RecurrenceException") or "").split(",") if t.strip()}
    last = min(until, _local(rule["UNTIL"])) if "UNTIL" in rule else until
    count = int(rule.get("COUNT", 10**6))
    interval = int(rule.get("INTERVAL", 1))
    length = end - start
    if rule["FREQ"] == "DAILY":
        steps = max(0, (last - start).days) // interval + 2
        candidates = [start + timedelta(days=i * interval) for i in range(min(steps, 2000))]
    else:
        days = sorted(DAY_CODES[d] for d in days_text) or [start.weekday()]
        week_start = start - timedelta(days=start.weekday())
        weeks = max(0, (last - week_start).days) // (7 * interval) + 2
        candidates = [week_start + timedelta(weeks=w * interval, days=d) for w in range(min(weeks, 600)) for d in days]
    found, n = [], 0
    for when in candidates:
        if when < start:
            continue
        if when > last or n >= count:
            break
        n += 1  # COUNT includes skipped dates, like calendar apps count them
        if when not in skipped:
            found.append((when, when + length))
    return found


def fetch(start, end):
    """UW Rec's bookings between start and end (Seattle time): ([(our place, label, starts, ends)], [problems]).
    A booking that fails a check is left out and described in problems."""
    ids = facility_ids()
    rows, seen, problems = [], set(), []
    unread = set()  # our places where a space didn't answer properly: their last copy is kept (see sync)
    asked = set()   # our places with at least one space on UW Rec's site
    spaces_read = 0
    for place, spaces in UW_REC_SPACES.items():
        for name, fid in ids.items():
            if not any(name == s or name.startswith(s + " ") or name.startswith(s + "-") for s in spaces):
                continue
            if spaces_read:
                time.sleep(current_app.config.get("UW_REC_PAUSE", PAUSE_SECONDS))
            spaces_read += 1
            asked.add(place)
            answer = _get("/Facility/GetScheduleCustomAppointmentsForDevExtremeScheduler",
                          {"selectedFacilityId": fid, "start": start.strftime("%Y-%m-%dT%H:%M:%S"),
                           "end": end.strftime("%Y-%m-%dT%H:%M:%S")})
            try:  # an empty or odd answer isn't "no bookings": it's no answer
                items = json.loads(answer) if answer and answer.strip() else None
            except ValueError:
                items = None
            if not isinstance(items, list):
                unread.add(place)
                problems.append(f"{name}: UW Rec sent no schedule, so {place}'s last copy is kept")
                continue
            for item in items:
                if not isinstance(item, dict):
                    problems.append(f"{name}: left out something that isn't a booking ({str(item)[:40]})")
                    continue
                title = str(item.get("Text") or "Reserved").strip() or "Reserved"
                one_space = len(spaces) == 1 and name == spaces[0]  # else say which gym/court/part
                label = (title if one_space else f"{name}: {title}")[:MAX_LABEL]
                try:
                    dates = occurrences(item, end)
                except (UnreadableRule, ValueError, KeyError, TypeError, AttributeError) as error:
                    problems.append(f"{name} · {title}: couldn't read its dates ({error})")
                    continue
                for starts, ends in dates:
                    if ends <= start or starts >= end or (place, starts, ends, title) in seen:
                        continue
                    if not timedelta(0) < ends - starts <= MAX_LENGTH:
                        problems.append(f"{name} · {title}: {starts:%b %d %H:%M}-{ends:%H:%M} isn't a real booking time")
                        continue
                    seen.add((place, starts, ends, title))
                    rows.append((place, label, starts, ends))
    if not spaces_read:
        problems.append("None of our places were found on UW Rec's site (did its page change?)")
    return rows, problems, unread, asked


def sync(days=DAYS_AHEAD):
    """Replace the copy of UW Rec's bookings for the next `days`, after checking it. Returns how many were saved.
    Kept instead (and admins told): when UW Rec can't be reached, or the new copy has less than half of the
    bookings the last one had (UW Rec's page probably changed). The result is saved for the admin page."""
    now = now_local()
    db = get_db()
    by_place = dict(db.execute("SELECT location, COUNT(*) FROM rec_reservations WHERE source = 'feed' AND ends_at >= ?"
                               " GROUP BY location", (to_db(now),)).fetchall())
    previous = sum(by_place.values())
    try:
        rows, problems, unread, asked = fetch(now - timedelta(hours=12), now + timedelta(days=days))
    except Exception as error:
        _report("failed", 0, previous, [f"UW Rec's site didn't answer ({type(error).__name__}: {str(error)[:80]})"])
        raise
    if previous >= 20 and len(rows) < previous * DROP_LIMIT:
        _report("kept", len(rows), previous, problems + [
            f"Only {len(rows)} bookings came back (the last copy had {previous}), so the last copy is kept"])
        return 0
    # A place that suddenly lost most of its bookings probably didn't answer properly: keep its last copy too.
    new_counts = {}
    for place, _, _, _ in rows:
        new_counts[place] = new_counts.get(place, 0) + 1
    for place, before in by_place.items():
        if place not in unread and before >= 10 and new_counts.get(place, 0) < before * DROP_LIMIT:
            unread.add(place)
            problems.append(f"{place}: only {new_counts.get(place, 0)} bookings came back (it had {before}), "
                            "so its last copy is kept")
    # Every place we read gets a fresh copy. Places that didn't answer properly, or that UW Rec's page didn't
    # list this time, keep yesterday's; places we no longer read at all (not in UW_REC_SPACES) lose theirs.
    kept = sorted(unread | (set(UW_REC_SPACES) - asked))
    db.execute(f"DELETE FROM rec_reservations WHERE source = 'feed' AND location NOT IN ({', '.join('?' for _ in kept)})",
               kept)
    db.executemany("""INSERT INTO rec_reservations (location, starts_at, ends_at, label, source, created_by, created_at)
                      VALUES (?, ?, ?, ?, 'feed', NULL, ?)""",
                   [(place, to_db(starts), to_db(ends), label, to_db(now)) for place, label, starts, ends in rows
                    if place not in unread])
    db.commit()
    saved = sum(1 for row in rows if row[0] not in unread)
    replaced_any = bool(asked - unread)
    # Nothing replaced at all (every place sent junk) isn't a good copy, whatever else happened.
    _report(("ok" if not problems else "warnings") if replaced_any else "kept", saved, previous, problems)
    return saved


def _report(status, saved, previous, problems):
    """Save what happened (the admin page shows it) and tell admins when something needs a look."""
    from .moderation import admin_emails
    from .notifications import notify
    report = {"at": to_db(now_local()), "status": status, "saved": saved, "previous": previous,
              "problems": problems[:20], "more": max(0, len(problems) - 20)}
    db = get_db()
    db.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('uw_rec_report', ?)", (json.dumps(report),))
    db.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('uw_rec_synced_at', ?)", (report["at"],))
    if status in ("ok", "warnings"):  # a copy was really saved, not just tried (the admin page says how old it is)
        db.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('uw_rec_copied_at', ?)", (report["at"],))
    if status != "ok":
        emails = sorted(admin_emails())
        for admin in db.execute(f"SELECT id FROM users WHERE email IN ({', '.join('?' for _ in emails)})",
                                emails).fetchall() if emails else []:
            notify(admin["id"], "account", "UW Rec copy needs a look: "
                   + {"failed": "UW Rec's site didn't answer.",
                      "kept": "far fewer bookings came back (or none could be read), so the last copy is kept.",
                      "warnings": f"{len(problems)} booking(s) couldn't be read."}[status],
                   "/admin/uw-rec", key="uw_rec_report")
    db.commit()


def last_report():
    row = get_db().execute("SELECT value FROM app_state WHERE key = 'uw_rec_report'").fetchone()
    return json.loads(row[0]) if row else None


def last_synced():
    """When UW Rec's schedule was last copied (or tried), as a DB time string, or None."""
    row = get_db().execute("SELECT value FROM app_state WHERE key = 'uw_rec_synced_at'").fetchone()
    return row[0] if row else None


def last_copied():
    """When a copy of UW Rec's schedule was last really saved, or None. (A copy saved before this was tracked
    counts too: the last try, if it worked.)"""
    row = get_db().execute("SELECT value FROM app_state WHERE key = 'uw_rec_copied_at'").fetchone()
    if row:
        return row[0]
    report = last_report() or {}
    return last_synced() if report.get("status") in ("ok", "warnings") else None


def sync_round(app):
    """Called from the background loop: at most once a day, even when UW Rec is down, in its own thread so a slow
    UW Rec never holds up game reminders. Never raises."""
    if not app.config.get("UW_REC_SYNC", True):
        return
    with app.app_context():
        last = last_synced()
        if last and last[:10] == to_db(now_local())[:10]:
            return
        get_db().execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('uw_rec_synced_at', ?)",
                         (to_db(now_local()),))  # before trying: a failure waits until tomorrow
        get_db().commit()
    threading.Thread(target=_sync_now, args=(app,), name="uw-rec", daemon=True).start()


def _sync_now(app):
    if not RUNNING.acquire(blocking=False):
        return  # the other copy of the site is on it
    try:
        with app.app_context():
            log.info("Copied %d UW Rec booking(s).", sync())
    except Exception:
        log.exception("Couldn't copy UW Rec's schedule (keeping the last copy)")
    finally:
        RUNNING.release()


@click.command("sync-uw-rec")
@with_appcontext
def sync_uw_rec_command():
    count = sync()
    report = last_report() or {}
    click.echo(f"{report.get('status', '?')}: {count} UW Rec booking(s) saved for the next {DAYS_AHEAD} days.")
    for problem in report.get("problems", []):
        click.echo(f"  - {problem}")
