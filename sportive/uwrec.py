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
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import click
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


def _get(path, params=None):
    url = SITE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    request = urllib.request.Request(url, headers={"User-Agent": "SportiveCircle/1.0 (UW student project)",
                                                   "Accept": "application/json, text/html"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", "replace")


def facility_ids():
    """{UW Rec space name: its id}, read from the public Search Facilities page (ids can change)."""
    page = _get("/Facility")
    found = re.findall(r'facilityId=([0-9a-f-]{36})"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{2,80})', page)
    return {name.strip().replace("&#39;", "'").replace("&amp;", "&"): fid for fid, name in found}


def _local(text):
    """"2026-10-01T18:00:00.000" (UW Rec's local time) or "20261218T040000Z" (UTC) -> Seattle time, no tzinfo."""
    text = text.strip()
    if text.endswith("Z"):
        return datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(SEATTLE) \
            .replace(tzinfo=None)
    if "-" in text:
        return datetime.fromisoformat(text[:19])
    return datetime.strptime(text[:15], "%Y%m%dT%H%M%S")


def occurrences(item, until):
    """Every (start, end) of one booking up to `until`, with weekly/daily repeats expanded and exceptions left out."""
    start, end = _local(item["StartDate"]), _local(item["EndDate"])
    rule = dict(part.split("=", 1) for part in (item.get("RecurrenceRule") or "").split(";") if "=" in part)
    if not rule:
        return [(start, end)]
    skipped = {_local(t) for t in (item.get("RecurrenceException") or "").split(",") if t.strip()}
    last = min(until, _local(rule["UNTIL"])) if "UNTIL" in rule else until
    count = int(rule.get("COUNT", 10**6))
    interval = int(rule.get("INTERVAL", 1))
    length = end - start
    days = sorted(DAY_CODES[d[-2:]] for d in rule.get("BYDAY", "").split(",") if d[-2:] in DAY_CODES) \
        or [start.weekday()]
    found, n = [], 0
    if rule.get("FREQ") == "DAILY":
        candidates = (start + timedelta(days=i * interval) for i in range(400))
    elif rule.get("FREQ") == "WEEKLY":
        week_start = start - timedelta(days=start.weekday())
        candidates = (week_start + timedelta(weeks=w * interval, days=d) for w in range(60) for d in days)
    else:
        return [(start, end)]
    for when in candidates:
        if when < start:
            continue
        if when > last or n >= count:
            break
        n += 1
        if when not in skipped:
            found.append((when, when + length))
    return found


def fetch(start, end):
    """[(our place, label, starts, ends)] from UW Rec between start and end (datetimes, Seattle time)."""
    ids = facility_ids()
    rows, seen = [], set()
    for place, spaces in UW_REC_SPACES.items():
        for name, fid in ids.items():
            if not any(name == s or name.startswith(s + " ") or name.startswith(s + "-") for s in spaces):
                continue
            items = json.loads(_get("/Facility/GetScheduleCustomAppointmentsForDevExtremeScheduler",
                                    {"selectedFacilityId": fid, "start": start.strftime("%Y-%m-%dT%H:%M:%S"),
                                     "end": end.strftime("%Y-%m-%dT%H:%M:%S")}) or "[]")
            for item in items:
                title = (item.get("Text") or "Reserved").strip()
                one_space = len(spaces) == 1 and name == spaces[0]  # else say which gym/court/part
                label = (title if one_space else f"{name}: {title}")[:MAX_LABEL]
                for starts, ends in occurrences(item, end):
                    if ends <= start or starts >= end or (place, starts, ends, title) in seen:
                        continue
                    seen.add((place, starts, ends, title))
                    rows.append((place, label, starts, ends))
    return rows


def sync(days=DAYS_AHEAD):
    """Replace the copy of UW Rec's bookings for the next `days`. Returns how many were saved; on any failure
    the old copy stays (and the error goes to the log)."""
    now = now_local()
    rows = fetch(now - timedelta(hours=12), now + timedelta(days=days))
    db = get_db()
    db.execute("DELETE FROM rec_reservations WHERE source = 'feed'")
    db.executemany("""INSERT INTO rec_reservations (location, starts_at, ends_at, label, source, created_by, created_at)
                      VALUES (?, ?, ?, ?, 'feed', NULL, ?)""",
                   [(place, to_db(starts), to_db(ends), label, to_db(now)) for place, label, starts, ends in rows])
    db.commit()
    _mark_tried()
    return len(rows)


def last_synced():
    """When UW Rec's schedule was last copied (or tried), as a DB time string, or None."""
    row = get_db().execute("SELECT value FROM app_state WHERE key = 'uw_rec_synced_at'").fetchone()
    return row[0] if row else None


def _mark_tried():
    get_db().execute("INSERT OR REPLACE INTO app_state (key, value) VALUES ('uw_rec_synced_at', ?)",
                     (to_db(now_local()),))
    get_db().commit()


def sync_round(app):
    """Called from the background loop: at most once a day, even when UW Rec is down. Never raises."""
    if not app.config.get("UW_REC_SYNC", True):
        return
    with app.app_context():
        last = last_synced()
        if last and last[:10] == to_db(now_local())[:10]:
            return
        _mark_tried()  # before trying: a failure waits until tomorrow instead of retrying every few minutes
        try:
            log.info("Copied %d UW Rec booking(s).", sync())
        except Exception:
            log.exception("Couldn't copy UW Rec's schedule (keeping the last copy)")


@click.command("sync-uw-rec")
@with_appcontext
def sync_uw_rec_command():
    click.echo(f"Copied {sync()} UW Rec booking(s) for the next {DAYS_AHEAD} days.")
