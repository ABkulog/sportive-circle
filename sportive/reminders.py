"""Email reminders before events.

Run every ~10 minutes (a cron job on the server):
    flask --app "sportive:create_app()" send-reminders
Locally:
    .venv/bin/flask --app main send-reminders
"""
import logging
from datetime import timedelta

import click
from flask import current_app
from flask.cli import with_appcontext

from .constants import SPORT_EMOJI, SPORTS
from .db import get_db
from .mail import send_email
from .timeutil import fmt_clock, from_db, now_local, to_db

log = logging.getLogger(__name__)

REMIND_BEFORE = timedelta(minutes=60)
# Someone who joined 5 minutes before a game doesn't need a reminder about it.
MIN_NOTICE = timedelta(minutes=15)


def reminder_email(row, minutes):
    """The friendly heads-up email. Returns (subject, body)."""
    emoji = SPORT_EMOJI[row["sport"]]
    title = f"{SPORTS[row['sport']]} pickup game" if row["is_quick"] else row["title"]
    first_name = row["full_name"].split()[0]
    link = f"{current_app.config['PUBLIC_URL'].rstrip('/')}/events/{row['event_id']}"
    others = row["going"] - 1
    crew = f"👥 You + {others} other{'s' if others != 1 else ''}" if others > 0 else "👥 Just you so far, share the link!"

    if row["host_id"] == row["user_id"]:
        plans_changed = ("You're the host, so people are counting on you 🙌 If plans change, "
                         "just cancel the event so nobody shows up to an empty field.")
    else:
        plans_changed = ("Can't make it anymore? No worries, just tap “Leave” on the event "
                         "so someone else can grab your spot.")

    subject = f"{emoji} {title} starts in {minutes} min, see you there!"
    body = (
        f"Hey {first_name}! 👋\n\n"
        f"Quick heads up, {title} is coming up soon:\n\n"
        f"🕐 {fmt_clock(row['starts_at'])} (in {minutes} min)\n"
        f"📍 {row['location']}\n"
        f"{crew}\n\n"
        f"See the details and who's going: {link}\n\n"
        f"{plans_changed}\n\n"
        "Have fun out there. Go Dawgs! 🐺💜💛\n"
        "Sportive Circle\n\n"
        "(Don't want these emails? Turn them off in Profile → Edit profile.)"
    )
    return subject, body


def send_due_reminders():
    """Email everyone going to an event that starts within the next hour. Returns how many were sent."""
    now = now_local()
    db = get_db()
    rows = db.execute(
        """SELECT r.event_id, r.user_id, r.created_at AS joined_at, u.email, u.full_name,
                  e.title, e.sport, e.location, e.starts_at, e.is_quick, e.host_id,
                  e.extra_players + (SELECT COUNT(*) FROM rsvps g WHERE g.event_id = e.id) AS going
           FROM rsvps r
           JOIN events e ON e.id = r.event_id
           JOIN users u ON u.id = r.user_id
           WHERE r.reminder_sent = 0 AND e.cancelled = 0 AND u.verified = 1 AND u.suspended = 0 AND u.email_reminders = 1
             AND e.starts_at > :now AND e.starts_at <= :soon""",
        {"now": to_db(now), "soon": to_db(now + REMIND_BEFORE)},
    ).fetchall()

    sent = 0
    for row in rows:
        starts = from_db(row["starts_at"])
        joined = from_db(row["joined_at"][:16])
        if starts - joined >= MIN_NOTICE:
            subject, body = reminder_email(row, minutes=int((starts - now).total_seconds() // 60))
            try:
                send_email(row["email"], subject, body)
                sent += 1
            except Exception:  # one bad address or email hiccup must not stop everyone else's reminders
                log.exception("Couldn't send a reminder to %s", row["email"])
        # Mark it either way, so nobody gets the same reminder twice.
        db.execute("UPDATE rsvps SET reminder_sent = 1 WHERE event_id = ? AND user_id = ?",
                   (row["event_id"], row["user_id"]))
        db.commit()
    return sent


@click.command("send-reminders")
@with_appcontext
def send_reminders_command():
    click.echo(f"Sent {send_due_reminders()} reminder(s).")
