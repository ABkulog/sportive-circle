"""One-time "what's new" emails to everyone already on the app (run by hand with tools/announce_texts.py).

Each person gets each announcement once: the time it went out is saved on their row, so running the
script again only reaches people who joined since, or whose email failed last time.
"""
import logging

from flask import current_app

from .db import get_db
from .links import public_url
from .unsubscribe import unsubscribe_url
from .mail import send_designed
from .sms import sms_available
from .timeutil import now_local, to_db

log = logging.getLogger(__name__)


def texts_audience():
    """Verified, active people without a confirmed number who haven't been told about texts yet."""
    return get_db().execute(
        """SELECT id, email, full_name FROM users
           WHERE verified = 1 AND suspended = 0 AND phone_verified = 0 AND texts_announced_at IS NULL
             AND weekly_digest = 1  -- turned off our optional (Monday/news) email: no announcement either
           ORDER BY id""").fetchall()


def announce_texts(send=False):
    """Works from a script too: links and email templates need a request, so it makes one."""
    with current_app.test_request_context():
        return _announce_texts(send)


def _announce_texts(send):
    """Email everyone in texts_audience() that texts are here. With send=False nothing is sent (a dry run).
    Returns (how many would get it / got it, how many failed)."""
    if not sms_available():
        raise RuntimeError("Texts aren't set up on this server (TWILIO_* settings), so there's nothing to announce.")
    people = texts_audience()
    if not send:
        return len(people), 0
    db = get_db()
    link = public_url("settings.texts")
    sent = failed = 0
    for person in people:
        first = person["full_name"].split()[0]
        try:
            send_designed(person["email"], "New on Sportive Circle: game updates by text 📱",
                          f"Hey {first}, you can get texts now",
                          ["Add your number and we'll text you game reminders, time or place changes, "
                           "cancellations, and friends' invites to games (those are in your bell, not email).",
                           "It's optional and takes 30 seconds. Reminders, changes and cancellations still come "
                           "by email too, and you can turn texts off anytime or reply STOP."],
                          button=("Add my number", link),
                          reason="You're getting this one-time update because you have a Sportive Circle account.",
                          unsubscribe=unsubscribe_url(person["email"], "digest"))
        except Exception:
            failed += 1
            log.exception("Couldn't email %s about texts", person["email"])
            continue
        db.execute("UPDATE users SET texts_announced_at = ? WHERE id = ?", (to_db(now_local()), person["id"]))
        db.commit()  # saved one by one, so a crash halfway never emails anyone twice
        sent += 1
    current_app.logger.info("Texts announcement: %s sent, %s failed", sent, failed)
    return sent, failed
