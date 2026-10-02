"""'Maya posted a game': tell a host's friends (and a club's followers and members) when a new game goes up.

Everyone who'd see the game gets a notice in their bell, and an email with a button to the game (where they can
join), unless they turned that email off in Settings. Never for private games; members-only club events only go
to members; nobody blocked (either way), suspended, already in it, or outside who the game is open to. At most
EMAILS_PER_DAY of these emails per person a day, so a busy friend list can't flood an inbox.
"""
import logging
import threading
from datetime import timedelta

from flask import current_app, url_for

from .constants import OPEN_TO_GENDERS, SPORT_EMOJI, SPORTS, STATED_GENDERS
from .db import get_db
from .links import public_url
from .mail import compose, send_email
from .unsubscribe import unsubscribe_url
from .timeutil import fmt_when, now_local, to_db

log = logging.getLogger(__name__)

EMAILS_PER_DAY = 3


def audience(event):
    """Who hears about this new game: the host's friends, plus the club's followers and members for a club
    event (members only, for members-only events). Returns rows of (id, full_name, email, gender, wants_email)."""
    if event["is_private"]:
        return []
    db = get_db()
    params = {"host": event["host_id"], "event": event["id"], "club": event["club_id"] or 0}
    friends = """SELECT CASE WHEN f.requester_id = :host THEN f.addressee_id ELSE f.requester_id END
                 FROM friendships f WHERE f.status = 'accepted' AND (f.requester_id = :host OR f.addressee_id = :host)"""
    club_people = ("SELECT m.user_id FROM club_members m WHERE m.club_id = :club AND m.role IN "
                   + ("('member', 'officer')" if event["members_only"] else "('follower', 'member', 'officer')"))
    people = club_people if event["members_only"] else f"{friends} UNION {club_people}"
    rows = db.execute(
        f"""SELECT u.id, u.full_name, u.email, u.gender, u.email_friend_games AS wants_email FROM users u
            WHERE u.id IN ({people}) AND u.id != :host AND u.verified = 1 AND u.suspended = 0
              AND u.id NOT IN (SELECT user_id FROM rsvps WHERE event_id = :event)
              AND u.id NOT IN (SELECT guest_id FROM invites WHERE event_id = :event AND status IN ('pending', 'requested'))
              AND u.id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = :host)
              AND u.id NOT IN (SELECT blocker_id FROM blocks WHERE blocked_id = :host)""", params).fetchall()
    groups = OPEN_TO_GENDERS.get(event["open_to"])
    return [r for r in rows if not (groups and r["gender"] in STATED_GENDERS and r["gender"] not in groups)]


def announce_new_game(event):
    """Call right after a game is posted (and committed). Bell notices now; emails just after the page answers."""
    from .events import event_title  # events.py imports this module
    from .notifications import notify
    people = audience(event)
    if not people:
        return 0
    db = get_db()
    host = event["host_name"].split()[0]
    title, when = event_title(event), fmt_when(event["starts_at"])
    via = f" for {event['club_name']}" if event["club_id"] else ""
    link = url_for("events.detail", event_id=event["id"])
    since = to_db(now_local() - timedelta(days=1))
    to_email = []
    for person in people:
        notify(person["id"], "friend_games", f"{host} posted {title}{via} ({when}). Want in?", link,
               key=f"friend_game:{event['id']}")
        if person["wants_email"] and db.execute(
                "SELECT COUNT(*) FROM game_alerts WHERE user_id = ? AND sent_at >= ?",
                (person["id"], since)).fetchone()[0] < EMAILS_PER_DAY:
            db.execute("INSERT OR IGNORE INTO game_alerts (user_id, event_id, sent_at) VALUES (?, ?, ?)",
                       (person["id"], event["id"], to_db(now_local())))
            to_email.append((person["email"], person["full_name"].split()[0]))
    db.commit()
    if to_email:
        details = {"host": host, "title": title, "when": when, "via": via, "location": event["location"],
                   "sport": SPORTS[event["sport"]], "emoji": SPORT_EMOJI.get(event["sport"], ""),
                   "url": public_url("events.detail", event_id=event["id"])}
        app = current_app._get_current_object()
        if app.testing:
            _send(app, to_email, details)
        else:  # a host with 200 friends shouldn't wait for 200 emails
            threading.Thread(target=_send, args=(app, to_email, details), name="game-alerts", daemon=True).start()
    return len(people)


def _send(app, recipients, d):
    with app.test_request_context():
        subject = f"{d['host']} posted a game: {d['title']}"
        for email, first in recipients:
            try:
                body, html = compose(
                    subject, f"{d['emoji']} {d['host']} posted a game",
                    [f"Hey {first}, {d['host']} just posted {d['title']}{d['via']}. Want in?",
                     f"🕐 {d['when']}", f"📍 {d['location']}"],
                    button=("See the game and join", d["url"]),
                    reason="You're getting this because you're friends with the host or follow the club. "
                           "Turn these emails off in Settings.",
                    preheader=f"{d['sport']} · {d['when']}", unsubscribe=unsubscribe_url(email, "friend_games"))
                send_email(email, subject, body, html=html, unsubscribe=unsubscribe_url(email, "friend_games"))
            except Exception:  # one bad address shouldn't stop the others
                log.exception("Couldn't email %s about a new game", email)
