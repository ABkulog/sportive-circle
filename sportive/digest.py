"""The Monday email: "Games this week" (open games in your sports, plus what you're already going to).

Sent once a week, Monday from 9 AM (Seattle), by the same background loop as reminders, to everyone who has it on
(Settings -> Email; on unless switched off). People with nothing to show get no email at all.

    flask --app wsgi send-weekly     # send it now (e.g. to try it)
"""
import logging
import threading
from datetime import timedelta

import click
from flask import g
from flask.cli import with_appcontext

from .db import get_db, user_sports
from .links import public_url
from .mail import compose, send_email
from .timeutil import fmt_when, now_local, to_db

log = logging.getLogger(__name__)

SEND_DAY, SEND_HOUR = 0, 9    # Monday, 9 AM
MAX_GAMES = 6
RUNNING = threading.Lock()


def games_for(user):
    """(open games this week in their sports, games they're already going to), soonest first."""
    from .events import (IS_FULL_SQL, MEMBERS_ONLY_FOR_MEMBERS, NOT_BLOCKED, event_title, games_open_to_me,
                         query_events)
    g.user = user  # the feed's own filters (blocked people, "open to", members-only) read g.user
    now = now_local()
    params = {"now": to_db(now), "week": to_db(now + timedelta(days=7))}
    base = ["e.cancelled = 0", "e.starts_at >= :now", "e.starts_at < :week"]
    going = query_events(base + ["EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me)"],
                         params, limit=MAX_GAMES)
    sports = user_sports(user["id"])
    sport_filter = []  # no sports picked: every sport
    if sports:
        params.update({f"s{i}": sport for i, sport in enumerate(sports)})
        sport_filter = [f"e.sport IN ({', '.join(f':s{i}' for i in range(len(sports)))})"]
    open_games = query_events(base + sport_filter + [
        "e.is_private = 0", f"NOT {IS_FULL_SQL}", "e.host_id != :me",
        "NOT EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me)",
        NOT_BLOCKED, games_open_to_me(), MEMBERS_ONLY_FOR_MEMBERS], params, limit=MAX_GAMES)
    line = lambda e: f"{event_title(e)} · {fmt_when(e['starts_at'])} · {e['location']}"
    return [line(e) for e in open_games], [line(e) for e in going]


def send_to(user):
    """Email one person their week. Returns True if there was anything to send."""
    open_games, going = games_for(user)
    if not open_games and not going:
        return False
    first = user["full_name"].split()[0]
    lines = []
    if going:
        lines += ["You're going to:"] + [f"• {game}" for game in going]
    if open_games:
        lines += ["Open games you could join:"] + [f"• {game}" for game in open_games]
    subject = f"Games this week, {first}"
    body, html = compose(subject, f"Your week, {first} 🏀", lines,
                         after=["Tap a game to join. Short a few players? Post a Need players and it goes to the "
                                "top of everyone's feed."],
                         button=("See all games", public_url("index")),
                         reason="You're getting this Monday email because you have a Sportive Circle account. "
                                "Turn it off in Settings -> Email.")
    send_email(user["email"], subject, body, html=html)
    return True


def send_weekly():
    """Send this week's email to everyone who wants it. Returns how many were sent."""
    sent = 0
    for user in get_db().execute("SELECT * FROM users WHERE verified = 1 AND suspended = 0 AND weekly_digest = 1"):
        try:
            sent += send_to(user)
        except Exception:
            log.exception("Couldn't send the weekly email to user %s", user["id"])
    g.pop("user", None)
    return sent


def weekly_round(app):
    """Called from the background loop: Mondays from 9 AM, once per week (claimed first, so the two copies of
    the site never both send). In its own thread, so reminders never wait for it. Never raises."""
    now = now_local()
    if now.weekday() != SEND_DAY or now.hour < SEND_HOUR:
        return
    week = now.strftime("%G-W%V")
    with app.app_context():
        db = get_db()
        claimed = db.execute("INSERT OR IGNORE INTO app_state (key, value) VALUES (?, ?)",
                             (f"weekly_email:{week}", to_db(now))).rowcount
        db.commit()
    if claimed:
        threading.Thread(target=_send_now, args=(app,), name="weekly-email", daemon=True).start()


def _send_now(app):
    if not RUNNING.acquire(blocking=False):
        return
    try:
        with app.test_request_context():  # g.user per person, like a page would
            log.info("Sent the weekly email to %d people.", send_weekly())
    except Exception:
        log.exception("Couldn't send the weekly email")
    finally:
        RUNNING.release()


@click.command("send-weekly")
@with_appcontext
def send_weekly_command():
    click.echo(f"Sent the weekly email to {send_weekly()} people.")
