"""Club events from HuskyLink (UW's student organization site), posted by themselves.

Once a day the background loop reads HuskyLink's public events feed (huskylink.washington.edu/rss_events). Each
event of a club on the app (matched by its HuskyLink group, clubs.huskylink_id) becomes a club update a week before:
"📅 Group Lift · Fri Oct 23 · 3:00 PM · IMA", with a link to RSVP on HuskyLink. It shows on the club's page and in
the feed, marked "From HuskyLink", even before an officer claims the club. A changed time or title updates the post;
a canceled event's post says so.
"""
import logging
import threading
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from .db import get_db
from .timeutil import SEATTLE, fmt_when, now_local, to_db

log = logging.getLogger(__name__)

FEED_URL = "https://huskylink.washington.edu/rss_events"
LINK_PREFIX = "https://huskylink.washington.edu/"
RUNNING = threading.Lock()
HIDDEN_PLACE = "Private Location"  # "Private Location (sign in to display)": HuskyLink only shows it to members
POST_AHEAD = timedelta(days=7)  # an event is posted when it's a week away: the feed gets a club's quarter bit by bit


def parse(xml_text):
    """The feed's events: [{id, groups, title, starts_at, location, link, deleted}] (bad items left out)."""
    events = []
    for item in ET.fromstring(xml_text).iter("item"):
        text = lambda tag: (item.findtext(tag) or "").strip()  # noqa: E731
        try:
            starts = datetime.fromisoformat(text("eventStartDateTime")[:19] + text("eventStartDateTime")[27:])
            starts = starts.astimezone(SEATTLE).replace(tzinfo=None)
            event_id = int(text("eventId"))
        except ValueError:
            continue
        link = text("eventLink")
        groups = {int(g) for g in (text("groupId") + "," + text("coHostedGroupIds")).split(",") if g.strip().isdigit()}
        events.append({"id": event_id, "groups": groups, "title": " ".join(text("title").split())[:120],
                       "starts_at": to_db(starts), "link": link if link.startswith(LINK_PREFIX) else "",
                       "location": "" if text("eventLocation").startswith(HIDDEN_PLACE)  # the place, not the address
                       else text("eventLocation").split(",")[0][:80],
                       "deleted": text("eventDelete") == "1"})
    return events


def post_text(event):
    where = f" · {event['location']}" if event["location"] else ""
    return f"📅 {event['title']} · {fmt_when(event['starts_at'])}{where}"


def sync(xml_text):
    """Posts each upcoming event of a club on the app once, and keeps its post up to date. Returns how many new."""
    db, now, horizon = get_db(), to_db(now_local()), to_db(now_local() + POST_AHEAD)
    clubs = {row["huskylink_id"]: row["id"] for row in db.execute(
        "SELECT id, huskylink_id FROM clubs WHERE huskylink_id IS NOT NULL AND status = 'approved'")}
    added = 0
    for event in parse(xml_text):
        club_id = next((clubs[g] for g in sorted(event["groups"]) if g in clubs), None)
        if club_id is None or not event["title"]:
            continue
        body = ("Canceled: " if event["deleted"] else "") + post_text(event)
        old = db.execute("SELECT id, body FROM club_posts WHERE huskylink_event = ?", (event["id"],)).fetchone()
        if old:
            if old["body"] != body:
                db.execute("UPDATE club_posts SET body = ?, link = ? WHERE id = ?", (body, event["link"], old["id"]))
        elif now <= event["starts_at"] <= horizon and not event["deleted"]:
            db.execute("INSERT INTO club_posts (club_id, author_id, body, created_at, link, huskylink_event)"
                       " VALUES (?, NULL, ?, ?, ?, ?)", (club_id, body, now, event["link"], event["id"]))
            added += 1
    db.commit()
    return added


def fetch():
    request = urllib.request.Request(FEED_URL, headers={"User-Agent": "SportiveCircle/1.0 (UW student project)"})
    return urllib.request.urlopen(request, timeout=60).read().decode("utf-8")


def sync_round(app):
    """Called from the background loop: once a day (claimed first, so the two copies of the site don't both read
    it), in its own thread so a slow HuskyLink never holds up game reminders. Never raises."""
    if not app.config.get("HUSKYLINK_SYNC", True):
        return
    with app.app_context():
        db = get_db()
        claimed = db.execute("INSERT OR IGNORE INTO app_state (key, value) VALUES (?, ?)",
                             (f"huskylink:{to_db(now_local())[:10]}", to_db(now_local()))).rowcount
        db.commit()
    if claimed:
        threading.Thread(target=_sync_now, args=(app,), name="huskylink", daemon=True).start()


def _sync_now(app):
    if not RUNNING.acquire(blocking=False):
        return
    try:
        with app.app_context():
            added = sync(fetch())
            log.info("HuskyLink: %d new club event post(s).", added)
    except Exception:
        log.exception("Couldn't read HuskyLink's events")
    finally:
        RUNNING.release()
