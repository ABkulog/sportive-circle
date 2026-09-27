"""Friends, blocking, direct messages and event group chats.

Safety rules:
- You can DM your friends, anyone you've shared an event with, and officers of verified clubs
  (they're the club's public contact). Officers can message people connected to their club.
  Anyone can reply to someone who messaged them. Everyone else: send a friend request first.
- Blocking someone stops all messages and friend requests between you, both ways.
- Event chats are only for people going to that event.
"""
from datetime import timedelta

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .auth import login_required, safe_next
from .db import get_db
from .timeutil import fmt_clock, fmt_when, now_local, to_db

bp = Blueprint("social", __name__)

MAX_MESSAGE_LENGTH = 1000
MAX_MESSAGES_PER_MINUTE = 20  # stops spam floods


# ---------------------------------------------------------------- helpers

def get_user(user_id):
    user = get_db().execute("SELECT id, full_name, avatar_updated FROM users WHERE id = ? AND verified = 1",
                            (user_id,)).fetchone()
    if user is None:
        abort(404)
    return user


def is_blocked_between(a, b):
    return get_db().execute(
        "SELECT 1 FROM blocks WHERE (blocker_id = ? AND blocked_id = ?) OR (blocker_id = ? AND blocked_id = ?)",
        (a, b, b, a)).fetchone() is not None


def i_blocked(me, other):
    return get_db().execute("SELECT 1 FROM blocks WHERE blocker_id = ? AND blocked_id = ?",
                            (me, other)).fetchone() is not None


def friendship_status(me, other):
    """'friends', 'sent' (I asked), 'received' (they asked), or 'none'."""
    row = get_db().execute(
        """SELECT requester_id, status FROM friendships
           WHERE (requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?)""",
        (me, other, other, me)).fetchone()
    if row is None:
        return "none"
    if row["status"] == "accepted":
        return "friends"
    return "sent" if row["requester_id"] == me else "received"


def shared_an_event(a, b):
    return get_db().execute(
        """SELECT 1 FROM rsvps r1 JOIN rsvps r2 ON r1.event_id = r2.event_id
           WHERE r1.user_id = ? AND r2.user_id = ? LIMIT 1""", (a, b)).fetchone() is not None


def is_club_officer(user_id):
    """Officers of verified clubs are the club's public contact: any student can ask them a question."""
    return get_db().execute(
        """SELECT 1 FROM club_members m JOIN clubs c ON c.id = m.club_id
           WHERE m.user_id = ? AND m.role = 'officer' AND c.status = 'approved' LIMIT 1""",
        (user_id,)).fetchone() is not None


def officer_of_their_club(officer, other):
    """True if `officer` runs a club that `other` follows, asked to join, tried out for, or is in."""
    return get_db().execute(
        """SELECT 1 FROM club_members mine JOIN club_members theirs ON theirs.club_id = mine.club_id
           WHERE mine.user_id = ? AND mine.role = 'officer' AND theirs.user_id = ? LIMIT 1""",
        (officer, other)).fetchone() is not None


def they_messaged_me(me, other):
    return get_db().execute("SELECT 1 FROM direct_messages WHERE sender_id = ? AND recipient_id = ? LIMIT 1",
                            (other, me)).fetchone() is not None


def can_message(me, other):
    if me == other or is_blocked_between(me, other):
        return False
    return (friendship_status(me, other) == "friends" or shared_an_event(me, other)
            or is_club_officer(other) or officer_of_their_club(me, other) or they_messaged_me(me, other))


def block_user(me, other):
    """Block someone: no more messages or friend requests either way, and any friendship ends."""
    db = get_db()
    db.execute("INSERT OR IGNORE INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, ?)",
               (me, other, to_db(now_local())))
    db.execute("""DELETE FROM friendships WHERE (requester_id = ? AND addressee_id = ?)
                  OR (requester_id = ? AND addressee_id = ?)""", (me, other, other, me))


def too_many_messages(me):
    since = to_db(now_local() - timedelta(minutes=1))
    db = get_db()
    recent = db.execute("SELECT COUNT(*) FROM direct_messages WHERE sender_id = ? AND created_at >= ?",
                        (me, since)).fetchone()[0]
    recent += db.execute("SELECT COUNT(*) FROM event_messages WHERE sender_id = ? AND created_at >= ?",
                         (me, since)).fetchone()[0]
    return recent >= MAX_MESSAGES_PER_MINUTE


def clean_body(text):
    """Returns (body, error)."""
    body = (text or "").strip()
    if not body:
        return None, "Type a message first."
    if len(body) > MAX_MESSAGE_LENGTH:
        return None, f"Messages can be up to {MAX_MESSAGE_LENGTH} characters."
    if too_many_messages(g.user["id"]):
        return None, "Whoa, slow down! Wait a minute before sending more messages."
    return body, None


def event_chat_unread():
    """{event_id: unread chat messages} for games I'm going to that aren't canceled or long over
    (computed once per request)."""
    if "chat_unread" not in g:
        g.chat_unread = {}
        if g.get("user") is not None:
            me = g.user["id"]
            recent = to_db(now_local() - timedelta(days=1))
            for row in get_db().execute(
                    """SELECT m.event_id, COUNT(*) AS n FROM event_messages m
                       JOIN events e ON e.id = m.event_id AND e.cancelled = 0 AND e.ends_at >= ?
                       JOIN rsvps r ON r.event_id = m.event_id AND r.user_id = ?
                       LEFT JOIN event_chat_seen s ON s.event_id = m.event_id AND s.user_id = ?
                       WHERE m.sender_id != ? AND m.id > COALESCE(s.last_id, 0)
                       GROUP BY m.event_id""", (recent, me, me, me)):
                g.chat_unread[row["event_id"]] = row["n"]
    return g.chat_unread


def message_json(row, me, kind):
    """kind: 'dm' or 'event_message' (for the report link)."""
    return {
        "id": row["id"],
        "mine": row["sender_id"] == me,
        "name": row["full_name"],
        "avatar": (url_for("profile.photo", user_id=row["sender_id"], v=row["avatar_updated"])
                   if row["avatar_updated"] else None),
        "initial": row["full_name"][:1].upper(),
        "body": row["body"],
        "time": fmt_clock(row["created_at"]),
        "profile": url_for("profile.view", user_id=row["sender_id"]),
        "report": None if row["sender_id"] == me else url_for("moderation.report", target_type=kind, target_id=row["id"]),
    }


# ---------------------------------------------------------------- friends

@bp.route("/friends")
@login_required
def friends():
    me = g.user["id"]
    db = get_db()
    incoming = db.execute(
        """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f JOIN users u ON u.id = f.requester_id
           WHERE f.addressee_id = ? AND f.status = 'pending' ORDER BY f.created_at DESC""", (me,)).fetchall()
    outgoing = db.execute(
        """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f JOIN users u ON u.id = f.addressee_id
           WHERE f.requester_id = ? AND f.status = 'pending' ORDER BY f.created_at DESC""", (me,)).fetchall()
    friend_list = db.execute(
        """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f
           JOIN users u ON u.id = CASE WHEN f.requester_id = ? THEN f.addressee_id ELSE f.requester_id END
           WHERE (f.requester_id = ? OR f.addressee_id = ?) AND f.status = 'accepted'
           ORDER BY u.full_name""", (me, me, me)).fetchall()
    # People you've played with who aren't friends (or pending, or blocked) yet.
    suggestions = db.execute(
        """SELECT u.id, u.full_name, u.avatar_updated, COUNT(DISTINCT r2.event_id) AS games
           FROM rsvps r1 JOIN rsvps r2 ON r1.event_id = r2.event_id AND r2.user_id != r1.user_id
           JOIN events e ON e.id = r1.event_id AND e.cancelled = 0 AND e.ends_at < ?
           JOIN users u ON u.id = r2.user_id AND u.verified = 1
           WHERE r1.user_id = ?
             AND u.id NOT IN (SELECT addressee_id FROM friendships WHERE requester_id = ?)
             AND u.id NOT IN (SELECT requester_id FROM friendships WHERE addressee_id = ?)
             AND u.id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = ?)
             AND u.id NOT IN (SELECT blocker_id FROM blocks WHERE blocked_id = ?)
           GROUP BY u.id ORDER BY games DESC, u.full_name LIMIT 10""",
        (to_db(now_local()), me, me, me, me, me)).fetchall()
    q = request.args.get("q", "").strip()[:MAX_SEARCH_LENGTH]
    return render_template("social/friends.html", incoming=incoming, outgoing=outgoing,
                           friends=friend_list, suggestions=suggestions, q=q, results=search_people(me, q))


MIN_SEARCH_LENGTH = 2
MAX_SEARCH_LENGTH = 60
MAX_SEARCH_RESULTS = 20


def search_people(me, q):
    """Huskies whose name matches the search (first name, last name, or both), for "Add friend".

    Only names, photos and class years are shown. People who blocked you (or you blocked) never appear.
    """
    if len(q) < MIN_SEARCH_LENGTH:
        return []
    words = q.lower().split()[:3]
    where = " AND ".join("LOWER(u.full_name) LIKE ? ESCAPE '\\'" for _ in words)
    like = ["%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for word in words]
    rows = get_db().execute(
        f"""SELECT u.id, u.full_name, u.avatar_updated, u.grad_year FROM users u
            WHERE u.verified = 1 AND u.suspended = 0 AND u.id != ? AND {where}
              AND u.id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = ?)
              AND u.id NOT IN (SELECT blocker_id FROM blocks WHERE blocked_id = ?)
            ORDER BY LOWER(u.full_name) LIKE ? DESC, u.full_name LIMIT ?""",
        (me, *like, me, me, words[0] + "%", MAX_SEARCH_RESULTS)).fetchall()
    return [{**dict(row), "status": friendship_status(me, row["id"])} for row in rows]


def _back(default):
    """Go back to the page the button was on (a hidden "next" field), or to `default`."""
    target = request.form.get("next", "")
    return redirect(safe_next(target) if target else default)


@bp.route("/friends/request/<int:user_id>", methods=("POST",))
@login_required
def send_request(user_id):
    me = g.user["id"]
    get_user(user_id)
    status = friendship_status(me, user_id)
    db = get_db()
    if user_id == me:
        flash("You're already your own best friend 😄", "info")
    elif is_blocked_between(me, user_id):
        flash("You can't send a friend request to this person.", "error")
    elif status == "received":  # they already asked me: just accept
        db.execute("UPDATE friendships SET status = 'accepted' WHERE requester_id = ? AND addressee_id = ?",
                   (user_id, me))
        db.commit()
        flash("You're friends now! 🐺🤝🐺", "celebrate")
    elif status == "none":
        db.execute("INSERT INTO friendships (requester_id, addressee_id, created_at) VALUES (?, ?, ?)",
                   (me, user_id, to_db(now_local())))
        db.commit()
        flash("Friend request sent!", "success")
    return _back(url_for("profile.view", user_id=user_id))


@bp.route("/friends/accept/<int:user_id>", methods=("POST",))
@login_required
def accept_request(user_id):
    db = get_db()
    cur = db.execute("UPDATE friendships SET status = 'accepted' WHERE requester_id = ? AND addressee_id = ?"
                     " AND status = 'pending'", (user_id, g.user["id"]))
    db.commit()
    if cur.rowcount:
        flash("You're friends now! 🐺🤝🐺", "celebrate")
    return _back(url_for("social.friends"))


@bp.route("/friends/remove/<int:user_id>", methods=("POST",))
@login_required
def remove_friend(user_id):
    """Unfriend, cancel a request you sent, or decline one you got."""
    me = g.user["id"]
    db = get_db()
    db.execute("""DELETE FROM friendships WHERE (requester_id = ? AND addressee_id = ?)
                  OR (requester_id = ? AND addressee_id = ?)""", (me, user_id, user_id, me))
    db.commit()
    return _back(url_for("social.friends"))


@bp.route("/block/<int:user_id>", methods=("POST",))
@login_required
def block(user_id):
    me = g.user["id"]
    get_user(user_id)
    if user_id != me:
        block_user(me, user_id)
        get_db().commit()
        flash("Blocked. They can't message you or send you friend requests anymore.", "info")
    return redirect(url_for("profile.view", user_id=user_id))


@bp.route("/unblock/<int:user_id>", methods=("POST",))
@login_required
def unblock(user_id):
    db = get_db()
    db.execute("DELETE FROM blocks WHERE blocker_id = ? AND blocked_id = ?", (g.user["id"], user_id))
    db.commit()
    flash("Unblocked.", "info")
    return redirect(url_for("profile.view", user_id=user_id))


# ---------------------------------------------------------- direct messages

@bp.route("/messages")
@login_required
def inbox():
    me = g.user["id"]
    conversations = get_db().execute(
        """SELECT u.id, u.full_name, u.avatar_updated, m.body, m.created_at, m.sender_id,
                  (SELECT COUNT(*) FROM direct_messages x
                   WHERE x.sender_id = u.id AND x.recipient_id = :me AND x.read_at IS NULL) AS unread
           FROM direct_messages m
           JOIN users u ON u.id = CASE WHEN m.sender_id = :me THEN m.recipient_id ELSE m.sender_id END
           WHERE m.id IN (SELECT MAX(id) FROM direct_messages
                          WHERE sender_id = :me OR recipient_id = :me
                          GROUP BY CASE WHEN sender_id = :me THEN recipient_id ELSE sender_id END)
             AND u.id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = :me)
           ORDER BY m.id DESC""", {"me": me}).fetchall()
    return render_template("social/inbox.html", conversations=conversations)


def _thread_rows(me, other, after=0):
    return get_db().execute(
        """SELECT m.*, u.full_name, u.avatar_updated FROM direct_messages m JOIN users u ON u.id = m.sender_id
           WHERE m.id > ? AND ((m.sender_id = ? AND m.recipient_id = ?) OR (m.sender_id = ? AND m.recipient_id = ?))
           ORDER BY m.id LIMIT 500""", (after, me, other, other, me)).fetchall()


def _mark_read(me, other):
    db = get_db()
    db.execute("UPDATE direct_messages SET read_at = ? WHERE sender_id = ? AND recipient_id = ? AND read_at IS NULL",
               (to_db(now_local()), other, me))
    db.commit()


@bp.route("/messages/<int:user_id>", methods=("GET", "POST"))
@login_required
def thread(user_id):
    me = g.user["id"]
    other = get_user(user_id)
    allowed = can_message(me, user_id)
    if request.method == "POST":
        if not allowed:
            flash("You can message friends, people you've played with, and club officers. "
                  "Send a friend request first!", "error")
        else:
            body, error = clean_body(request.form.get("body"))
            if error:
                flash(error, "error")
            else:
                db = get_db()
                db.execute("INSERT INTO direct_messages (sender_id, recipient_id, body, created_at) VALUES (?, ?, ?, ?)",
                           (me, user_id, body, to_db(now_local())))
                db.commit()
        return redirect(url_for("social.thread", user_id=user_id) + "#composer")
    _mark_read(me, user_id)
    rows = _thread_rows(me, user_id) if not is_blocked_between(me, user_id) else []
    return render_template("social/thread.html", other=other, messages=[message_json(r, me, 'dm') for r in rows],
                           allowed=allowed, poll_url=url_for("social.thread_poll", user_id=user_id),
                           blocked=i_blocked(me, user_id))


@bp.route("/messages/<int:user_id>/poll")
@login_required
def thread_poll(user_id):
    """New messages since ?after=<id> (the page asks every few seconds)."""
    me = g.user["id"]
    if is_blocked_between(me, user_id):
        return jsonify(messages=[])
    rows = _thread_rows(me, user_id, request.args.get("after", 0, type=int))
    _mark_read(me, user_id)
    return jsonify(messages=[message_json(r, me, 'dm') for r in rows])


# -------------------------------------------------------------- event chat

def _event_for_chat(event_id):
    """The event (with player counts, like the event page), and whether I'm going to it.
    Everyone going, including the host, can chat."""
    from .events import get_event  # imported here: events.py also uses this module's helpers
    event = get_event(event_id)
    return event, bool(event["i_am_going"])


def _chat_rows(event_id, after=0):
    return get_db().execute(
        """SELECT m.*, u.full_name, u.avatar_updated FROM event_messages m JOIN users u ON u.id = m.sender_id
           WHERE m.event_id = ? AND m.id > ? ORDER BY m.id LIMIT 500""", (event_id, after)).fetchall()


def _mark_chat_seen(event_id, rows):
    if rows:
        db = get_db()
        db.execute("""INSERT INTO event_chat_seen (event_id, user_id, last_id) VALUES (?, ?, ?)
                      ON CONFLICT(event_id, user_id) DO UPDATE SET last_id = MAX(last_id, excluded.last_id)""",
                   (event_id, g.user["id"], rows[-1]["id"]))
        db.commit()


@bp.route("/events/<int:event_id>/chat", methods=("GET", "POST"))
@login_required
def event_chat(event_id):
    event, going = _event_for_chat(event_id)
    if not going:
        flash("Join the event to see and send messages in its group chat.", "info")
        return redirect(url_for("events.detail", event_id=event_id))
    if request.method == "POST":
        body, error = clean_body(request.form.get("body"))
        if error:
            flash(error, "error")
        elif event["cancelled"]:
            flash("This event was canceled, so its chat is closed.", "error")
        else:
            db = get_db()
            db.execute("INSERT INTO event_messages (event_id, sender_id, body, created_at) VALUES (?, ?, ?, ?)",
                       (event_id, g.user["id"], body, to_db(now_local())))
            db.commit()
        return redirect(url_for("social.event_chat", event_id=event_id) + "#composer")
    rows = _chat_rows(event_id)
    _mark_chat_seen(event_id, rows)
    people = get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (event_id,)).fetchone()[0]
    return render_template("social/event_chat.html", event=event, people=people,
                           messages=[message_json(r, g.user["id"], 'event_message') for r in rows],
                           poll_url=url_for("social.event_chat_poll", event_id=event_id),
                           when=fmt_when(event["starts_at"]))


@bp.route("/events/<int:event_id>/chat/poll")
@login_required
def event_chat_poll(event_id):
    _, going = _event_for_chat(event_id)
    if not going:
        abort(403)
    rows = _chat_rows(event_id, request.args.get("after", 0, type=int))
    _mark_chat_seen(event_id, rows)
    return jsonify(messages=[message_json(r, g.user["id"], 'event_message') for r in rows])
