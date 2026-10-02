"""Email reminders before events.

On Render the app checks every 5 minutes by itself (start_reminder_loop), so no outside scheduler is needed.
To send them by hand:
    flask --app wsgi send-reminders          (on the server; locally: .venv/bin/flask --app main send-reminders)
or from another scheduler:
    POST /tasks/send-reminders   with the header  X-Task-Token: <TASK_TOKEN>
"""
import logging
import random
import threading
import time
from datetime import timedelta

import click
from flask import Blueprint, abort, current_app, jsonify, request
from flask.cli import with_appcontext

from .backups import backup_round
from .constants import SPORTS
from .db import get_db
from .digest import weekly_round
from .mail import compose, send_email
from .sms import text_user
from .textutil import same_secret
from .unsubscribe import unsubscribe_url
from .timeutil import fmt_clock, from_db, now_local, real_gap, to_db
from .uwrec import sync_round as uw_rec_round

log = logging.getLogger(__name__)

REMIND_BEFORE = timedelta(minutes=60)  # the earliest a reminder goes out
REMIND_CHOICES = {60: "1 hour before", 30: "30 min before", 0: "No reminder"}  # each player picks on the game page
# Someone who joined 5 minutes before a game doesn't need a reminder about it.
MIN_NOTICE = timedelta(minutes=15)
CHECK_EVERY = timedelta(minutes=5)


def reminder_email(row, minutes):
    """The heads-up email. Returns (subject, plain text, HTML)."""
    title = f"{SPORTS[row['sport']]} pickup game" if row["is_quick"] else row["title"]
    first_name = row["full_name"].split()[0]
    link = f"{current_app.config['PUBLIC_URL'].rstrip('/')}/events/{row['event_id']}"
    others = row["going"] - 1
    crew = f"You + {others} other{'s' if others != 1 else ''}" if others > 0 else "Just you so far. Share the link!"

    if row["host_id"] == row["user_id"]:
        plans_changed = "You're the host. If plans change, cancel the game so nobody shows up for nothing."
    else:
        plans_changed = "Can't make it? Tap “Leave” on the game so someone else can take your spot."

    subject = f"{title} starts in {minutes} min"
    body, html = compose(
        subject, subject,
        [f"Hey {first_name}, your game is coming up:",
         f"{fmt_clock(row['starts_at'])} (in {minutes} min)", row["location"], crew],
        after=[plans_changed],
        button=("See the game", link),
        reason="You're getting this because you joined this game. Pick 30 min or no reminder on the game page, "
               "or turn these off in Settings → Email.",
        preheader=f"{fmt_clock(row['starts_at'])} at {row['location']}",
        unsubscribe=unsubscribe_url(row["email"], "reminders"))
    return subject, body, html


def send_due_reminders():
    """Email everyone going to an event that starts within the next hour. Returns how many were sent."""
    now = now_local()
    db = get_db()
    rows = db.execute(
        """SELECT r.event_id, r.user_id, r.created_at AS joined_at, r.remind_minutes, u.email, u.full_name,
                  u.email_reminders,
                  e.title, e.sport, e.location, e.starts_at, e.is_quick, e.host_id,
                  e.extra_players + (SELECT COUNT(*) FROM rsvps g WHERE g.event_id = e.id) AS going
           FROM rsvps r
           JOIN events e ON e.id = r.event_id
           JOIN users u ON u.id = r.user_id
           WHERE r.reminder_sent = 0 AND r.remind_minutes > 0 AND e.cancelled = 0 AND u.verified = 1 AND u.suspended = 0
             AND (u.email_reminders = 1 OR (u.sms_updates = 1 AND u.phone_verified = 1))
             AND e.starts_at > :now AND e.starts_at <= :soon
             AND NOT EXISTS (SELECT 1 FROM clubs c WHERE c.id = e.club_id AND c.status != 'approved')  -- on hold""",
        # An hour extra: the night clocks jump ahead, 3:30 AM is only an hour after 1:30 (checked below).
        {"now": to_db(now), "soon": to_db(now + REMIND_BEFORE + timedelta(hours=1))},
    ).fetchall()

    sent = 0
    for row in rows:
        if real_gap(now, from_db(row["starts_at"])) > timedelta(minutes=row["remind_minutes"]):
            continue  # picked "30 min before": not yet
        # Mark it before sending, and only send if this run was the one that marked it: the app runs more
        # than one copy of itself, and nobody should get the same reminder twice. (A failed send isn't retried.)
        claimed = db.execute("UPDATE rsvps SET reminder_sent = 1 WHERE event_id = ? AND user_id = ?"
                             " AND reminder_sent = 0", (row["event_id"], row["user_id"])).rowcount
        db.commit()
        starts = from_db(row["starts_at"])
        joined = from_db(row["joined_at"][:16])
        if claimed and starts - joined >= MIN_NOTICE:
            minutes = int(real_gap(now, starts).total_seconds() // 60)
            if row["email_reminders"]:
                subject, body, html = reminder_email(row, minutes=minutes)
                try:
                    send_email(row["email"], subject, body, html=html, unsubscribe=unsubscribe_url(row["email"], "reminders"))
                    sent += 1
                except Exception:  # one bad address or email hiccup must not stop everyone else's reminders
                    log.exception("Couldn't send a reminder to %s", row["email"])
            # A text too, for people who asked for texts (sms.text_user checks that, and never raises).
            title = f"{SPORTS[row['sport']]} pickup game" if row["is_quick"] else row["title"]
            link = f"{current_app.config['PUBLIC_URL'].rstrip('/')}/events/{row['event_id']}"
            if text_user(row["user_id"], f"{title} starts at {fmt_clock(row['starts_at'])} (in {minutes} min) at "
                                         f"{row['location']}. {link}", kind="reminder") and not row["email_reminders"]:
                sent += 1
    return sent


def reminder_round(app):
    """One check: send whatever reminders are due. Never raises (the loop has to keep going)."""
    try:
        with app.app_context():
            sent = send_due_reminders()
        if sent:
            log.info("Sent %d reminder(s).", sent)
    except Exception:
        log.exception("Couldn't check for reminders")


def start_reminder_loop(app):
    """Check for due reminders every few minutes in the background, for as long as the site runs
    (and make the day's database backup, backups.py)."""
    def loop():
        time.sleep(random.uniform(30, 90))  # let the site finish starting; the copies don't all check at once
        while True:
            reminder_round(app)
            backup_round(app)  # once a day; a quick "already done today?" check otherwise
            uw_rec_round(app)  # UW Rec's bookings, copied once a day (uwrec.py)
            weekly_round(app)  # Mondays from 9 AM: the "Games this week" email (digest.py)
            time.sleep(CHECK_EVERY.total_seconds())

    threading.Thread(target=loop, name="reminders", daemon=True).start()


bp = Blueprint("tasks", __name__)


@bp.route("/tasks/send-reminders", methods=("POST",))
def send_reminders_task():
    """For a scheduler (e.g. Render's cron job). Only works with the secret TASK_TOKEN; without one set,
    the page doesn't exist."""
    token = current_app.config.get("TASK_TOKEN")
    sent = request.headers.get("X-Task-Token", "")
    if not token or not same_secret(sent, token):
        abort(404)
    return jsonify(sent=send_due_reminders())


@click.command("send-reminders")
@with_appcontext
def send_reminders_command():
    click.echo(f"Sent {send_due_reminders()} reminder(s).")
