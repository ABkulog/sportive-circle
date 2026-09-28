"""Invites and held spots (the data side of parties; the pages are in parties.py).

Anyone going to a game can invite friends. Each invite holds a spot for 30 minutes, so a group can
join together without strangers taking their spots while they decide. When the time is up, the
spot is free for anyone again, but the invite still works if there's room.
"""
from datetime import timedelta

from .db import get_db
from .timeutil import from_db, now_local, to_db

HOLD_TIME = timedelta(minutes=30)
MAX_PARTY = 10  # friends one person can reserve spots for at once
MAX_PASSWORD_TRIES = 10              # wrong private-game passwords per person per game...
PASSWORD_WINDOW = timedelta(hours=1)  # ...per hour

# SQL: how many spots are being held right now in event `e` (optionally only on one team).
# Needs the :hold_now parameter.
HELD = ("(SELECT COUNT(*) FROM invites h WHERE h.event_id = e.id AND h.status = 'pending'"
        " AND h.expires_at > :hold_now)")


def now_param():
    return to_db(now_local())


def my_invite(event_id, user_id):
    """This person's open (pending) invite to this game, with the inviter's name, or None."""
    return get_db().execute(
        """SELECT i.*, u.full_name AS inviter_name FROM invites i JOIN users u ON u.id = i.inviter_id
           WHERE i.event_id = ? AND i.guest_id = ? AND i.status = 'pending'""", (event_id, user_id)).fetchone()


def hold_minutes_left(invite):
    """Whole minutes left on the held spot (0 = not held anymore)."""
    if invite is None or invite["status"] != "pending":
        return 0
    left = from_db(invite["expires_at"]) - now_local()
    return max(0, -(-int(left.total_seconds()) // 60))  # round up: "1 min" until it's really over


def hold_spots(event_id, inviter, friend_ids, team, message, link):
    """Reserve a spot for each friend for 30 minutes and send them a "You down?" notice. The caller checks
    there's room and commits. Used when a host creates a game and by "Reserve spots" on a game page."""
    from .notifications import notify  # imported here: notifications.py is loaded after this module
    expires = to_db(now_local() + HOLD_TIME)
    for friend_id in friend_ids:
        get_db().execute("""INSERT OR REPLACE INTO invites (event_id, inviter_id, guest_id, team, status, created_at,
                                                            expires_at)
                            VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                         (event_id, inviter, friend_id, team, now_param(), expires))
        notify(friend_id, "invites", message, link)


def pending_invites(event_id):
    """Everyone invited to this game who hasn't answered yet, for the "Who's going" list."""
    return get_db().execute(
        """SELECT i.*, g.full_name AS guest_name, g.avatar_updated AS guest_avatar, v.full_name AS inviter_name
           FROM invites i JOIN users g ON g.id = i.guest_id JOIN users v ON v.id = i.inviter_id
           WHERE i.event_id = ? AND i.status = 'pending' ORDER BY i.id""", (event_id,)).fetchall()


def requested_invites(event_id):
    """Friends players asked to bring to a private game, waiting for the host's yes."""
    return get_db().execute(
        """SELECT i.*, g.full_name AS guest_name, g.avatar_updated AS guest_avatar, v.full_name AS inviter_name
           FROM invites i JOIN users g ON g.id = i.guest_id JOIN users v ON v.id = i.inviter_id
           WHERE i.event_id = ? AND i.status = 'requested' ORDER BY i.id""", (event_id,)).fetchall()


def held_spots(event_id, team=None, except_user=None):
    """Spots held right now (on one team, if given), not counting `except_user`'s own hold."""
    sql = "SELECT COUNT(*) FROM invites WHERE event_id = ? AND status = 'pending' AND expires_at > ?"
    args = [event_id, now_param()]
    if team is not None:
        sql += " AND team = ?"
        args.append(team)
    if except_user is not None:
        sql += " AND guest_id != ?"
        args.append(except_user)
    return get_db().execute(sql, args).fetchone()[0]


def team_counts(event_id):
    """{1: players on team 1, 2: ...} for a team vs team game."""
    rows = get_db().execute("SELECT team, COUNT(*) AS n FROM rsvps WHERE event_id = ? AND team IS NOT NULL"
                            " GROUP BY team", (event_id,))
    counts = {1: 0, 2: 0}
    counts.update({row["team"]: row["n"] for row in rows})
    return counts


# ---------------------------------------------------------------- private-game passwords

def too_many_password_tries(event_id, user_id):
    row = get_db().execute("SELECT tries, first_try FROM password_tries WHERE event_id = ? AND user_id = ?",
                           (event_id, user_id)).fetchone()
    return bool(row and row["tries"] >= MAX_PASSWORD_TRIES
                and now_local() < from_db(row["first_try"]) + PASSWORD_WINDOW)


def count_wrong_password(event_id, user_id):
    db = get_db()
    row = db.execute("SELECT first_try FROM password_tries WHERE event_id = ? AND user_id = ?",
                     (event_id, user_id)).fetchone()
    if row is None or now_local() >= from_db(row["first_try"]) + PASSWORD_WINDOW:
        db.execute("INSERT OR REPLACE INTO password_tries (event_id, user_id, tries, first_try) VALUES (?, ?, 1, ?)",
                   (event_id, user_id, now_param()))
    else:
        db.execute("UPDATE password_tries SET tries = tries + 1 WHERE event_id = ? AND user_id = ?",
                   (event_id, user_id))
    db.commit()
