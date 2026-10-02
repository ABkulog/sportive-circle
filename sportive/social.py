"""Friends, blocking, direct messages and event group chats.

Safety rules:
- You can DM your friends, anyone you've shared an event with, and officers of verified clubs
  (they're the club's public contact). Officers can message people connected to their club.
  Anyone can reply to someone who messaged them. Everyone else: send a friend request first.
- Blocking someone stops all messages and friend requests between you, both ways.
- Event chats are only for people going to that event.
"""
import json
from datetime import timedelta

from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)

from .auth import login_required, safe_next
from .constants import SPORT_EMOJI
from .db import get_db
from .textutil import fold, initial, multi_line, one_line, person_name
from .photos import make_chat_photo
from .timeutil import fmt_clock, fmt_when, from_db, now_local, to_db

bp = Blueprint("social", __name__)

MAX_MESSAGE_LENGTH = 1000
MAX_MESSAGES_PER_MINUTE = 20  # stops spam floods
MAX_DRAFT_COOKIE_BYTES = 2500


# ---------------------------------------------------------------- helpers

def get_user(user_id):
    user = get_db().execute("SELECT id, full_name, avatar_updated FROM users WHERE id = ? AND verified = 1"
                            " AND suspended = 0", (user_id,)).fetchone()
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


def friends_of(user_id):
    """Accepted friends (id, name, photo), A to Z. Blocking ends a friendship, so blocked people aren't here."""
    return get_db().execute(
        """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f
           JOIN users u ON u.id = CASE WHEN f.requester_id = :me THEN f.addressee_id ELSE f.requester_id END
           WHERE (f.requester_id = :me OR f.addressee_id = :me) AND f.status = 'accepted' AND u.suspended = 0
           ORDER BY fold(u.full_name)""", {"me": user_id}).fetchall()


def shared_an_event(a, b):
    """They played a game together (it has ended). Just joining a stranger's game doesn't unlock messaging:
    the game's group chat is there for planning it."""
    return get_db().execute(
        """SELECT 1 FROM rsvps r1 JOIN rsvps r2 ON r1.event_id = r2.event_id JOIN events e ON e.id = r1.event_id
           WHERE r1.user_id = ? AND r2.user_id = ? AND e.cancelled = 0 AND e.ends_at < ? LIMIT 1""",
        (a, b, to_db(now_local()))).fetchone() is not None


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
    if get_db().execute("SELECT suspended FROM users WHERE id = ?", (other,)).fetchone()["suspended"]:
        return False  # suspended accounts are hidden everywhere; an old chat link doesn't reach them either
    return (friendship_status(me, other) == "friends" or shared_an_event(me, other)
            or is_club_officer(other) or officer_of_their_club(me, other) or they_messaged_me(me, other))


def block_user(me, other):
    """Block someone: no more messages or friend requests either way, and any friendship ends."""
    db = get_db()
    db.execute("INSERT OR IGNORE INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, ?)",
               (me, other, to_db(now_local())))
    db.execute("""DELETE FROM friendships WHERE (requester_id = ? AND addressee_id = ?)
                  OR (requester_id = ? AND addressee_id = ?)""", (me, other, other, me))
    # They come off my upcoming games (and their open invites to them close), like the host removing them.
    now = to_db(now_local())
    db.execute("""DELETE FROM rsvps WHERE user_id = ? AND event_id IN
                  (SELECT id FROM events WHERE host_id = ? AND cancelled = 0 AND ends_at >= ?)""", (other, me, now))
    db.execute("""UPDATE invites SET status = 'canceled' WHERE guest_id = ? AND status IN ('pending', 'requested')
                  AND event_id IN (SELECT id FROM events WHERE host_id = ?)""", (other, me))
    cancel_invites_between(me, other)


def cancel_invites_between(a, b):
    """Spots held and invites either of them sent the other, in any game, end (with their "You down?" notices):
    after an unfriend or a block, nobody gets in on the other's invite."""
    db = get_db()
    pair = "((guest_id = :a AND inviter_id = :b) OR (guest_id = :b AND inviter_id = :a)) AND status IN ('pending', 'requested')"
    for row in db.execute(f"SELECT event_id, guest_id FROM invites WHERE {pair}", {"a": a, "b": b}).fetchall():
        db.execute("DELETE FROM notices WHERE user_id = ? AND key = ?", (row["guest_id"], f"invite:{row['event_id']}"))
    db.execute(f"UPDATE invites SET status = 'canceled' WHERE {pair}", {"a": a, "b": b})


def too_many_messages(me, sending=1):
    """True if sending `sending` more messages now would go over the per-minute limit."""
    since = to_db(now_local() - timedelta(minutes=1))
    db = get_db()
    recent = db.execute("SELECT COUNT(*) FROM direct_messages WHERE sender_id = ? AND created_at >= ?",
                        (me, since)).fetchone()[0]
    recent += db.execute("SELECT COUNT(*) FROM event_messages WHERE sender_id = ? AND created_at >= ?",
                         (me, since)).fetchone()[0]
    return recent + sending > MAX_MESSAGES_PER_MINUTE


def clean_body(text, photo=False):
    """Returns (body, error). With a photo, the words are optional."""
    body = multi_line(text)
    if body and not person_name(body).strip():  # only invisible characters (zero-width spaces): an empty bubble
        body = ""
    if not body and not photo:
        return None, "Type a message first."
    if len(body) > MAX_MESSAGE_LENGTH:
        return None, f"Messages can be up to {MAX_MESSAGE_LENGTH} characters."
    if too_many_messages(g.user["id"]):
        return None, "Whoa, slow down! Wait a minute before sending more messages."
    return body, None


def read_chat_photo():
    """The photo picked in the chat box, saved (resized, hidden info removed): (photo id or None, error or None)."""
    upload = request.files.get("photo")
    if upload is None or not upload.filename:
        return None, None
    try:
        image = make_chat_photo(upload.read())
    except ValueError as error:
        return None, str(error)
    cur = get_db().execute("INSERT INTO chat_photos (uploader_id, image, created_at) VALUES (?, ?, ?)",
                           (g.user["id"], image, to_db(now_local())))
    return cur.lastrowid, None


def day_label(value):
    """"Today", "Yesterday", "Mon, Sep 28" or "Sep 28, 2025": the dividers between days in a chat."""
    day = from_db(value).date()
    today = now_local().date()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    if (today - day).days < 7:
        return day.strftime("%A")
    return f"{day:%a, %b} {day.day}" + (f", {day.year}" if day.year != today.year else "")


def chat_sent(error, back):
    """After sending: the chat page sends in the background (chat.js asks with X-Chat-Send) and gets a small
    answer, so the page doesn't reload; without JavaScript, the page reloads with the message (or the problem)."""
    if request.headers.get("X-Chat-Send"):
        return jsonify(ok=error is None, error=error)
    if error:
        flash(error, "error")
        keep_draft(request.form.get("body"))
    return redirect(back)


def keep_draft(text):
    """A message that couldn't be sent goes back in the box after the redirect, instead of vanishing."""
    body = (text or "")[:MAX_MESSAGE_LENGTH]
    # The session is a cookie (browsers cap them at 4 KB) and an emoji takes 12 bytes in it: keep as much as fits.
    while body and len(json.dumps(body)) > MAX_DRAFT_COOKIE_BYTES:
        body = body[:len(body) * 3 // 4]
    if body:
        session["chat_draft"] = {"path": request.path, "body": body}


def take_draft():
    draft = session.pop("chat_draft", None)
    return draft["body"] if draft and draft.get("path") == request.path else ""


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
                         AND m.sender_id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = ?)
                       GROUP BY m.event_id""", (recent, me, me, me, me)):
                g.chat_unread[row["event_id"]] = row["n"]
    return g.chat_unread


def message_json(row, me, kind):
    """kind: 'dm' or 'event_message' (for the report link)."""
    return {
        "id": row["id"],
        "mine": row["sender_id"] == me,
        "name": row["full_name"],
        "avatar": (url_for("profile.photo", user_id=row["sender_id"], v=row["avatar_updated"], s=96)
                   if row["avatar_updated"] else None),
        "initial": initial(row["full_name"]),
        "body": row["body"],
        "time": fmt_clock(row["created_at"]),
        "day": day_label(row["created_at"]),
        "sender": row["sender_id"],
        "photo": url_for("social.chat_photo", photo_id=row["photo_id"]) if row["photo_id"] else None,
        "profile": url_for("profile.view", user_id=row["sender_id"]),
        "report": None if row["sender_id"] == me else url_for("moderation.report", target_type=kind, target_id=row["id"]),
        "game": shared_game(row),
    }


def shared_game(row):
    """The game card on a message sent with "Send to friends" (None for ordinary messages)."""
    if "game_title" not in row.keys() or row["game_title"] is None:
        return None
    return {"title": row["game_title"], "when": fmt_when(row["game_starts"]), "where": row["game_location"],
            "emoji": SPORT_EMOJI.get(row["game_sport"], ""), "cancelled": bool(row["game_cancelled"]),
            "url": url_for("events.detail", event_id=row["event_id"])}


# ---------------------------------------------------------------- friends

@bp.route("/friends")
@login_required
def friends():
    me = g.user["id"]
    db = get_db()
    incoming = db.execute(
        """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f JOIN users u ON u.id = f.requester_id
           WHERE f.addressee_id = ? AND f.status = 'pending' AND u.suspended = 0 ORDER BY f.created_at DESC""",
        (me,)).fetchall()
    outgoing = db.execute(
        """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f JOIN users u ON u.id = f.addressee_id
           WHERE f.requester_id = ? AND f.status = 'pending' AND u.suspended = 0 ORDER BY f.created_at DESC""",
        (me,)).fetchall()
    friend_list = db.execute(
        """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f
           JOIN users u ON u.id = CASE WHEN f.requester_id = ? THEN f.addressee_id ELSE f.requester_id END
           WHERE (f.requester_id = ? OR f.addressee_id = ?) AND f.status = 'accepted' AND u.suspended = 0
           ORDER BY fold(u.full_name)""", (me, me, me)).fetchall()
    q = request.args.get("q", "").strip()[:MAX_SEARCH_LENGTH]
    suggestions = friend_suggestions(me)
    return render_template("social/friends.html", incoming=incoming, outgoing=outgoing,
                           friends=friend_list, suggestions=suggestions, suggestion_reason=suggestion_reason,
                           q=q, results=search_people(me, q))


MAX_SUGGESTIONS = 10


def friend_suggestions(me):
    """"Suggested for you": friends of your friends and people you've played with, most in common first.
    Leaves out your friends, anyone with a request pending either way, blocked people and unverified or
    suspended accounts. Each row has `mutual` (friends in common), `via` (one of them, for "Friends with Maya")
    and `games` (finished games played together)."""
    return get_db().execute(
        """WITH my_friends AS (  -- not suspended ones: nobody can see them, so they can't be "Friends with ..."
               SELECT CASE WHEN requester_id = :me THEN addressee_id ELSE requester_id END AS id
               FROM friendships WHERE status = 'accepted' AND (requester_id = :me OR addressee_id = :me)
               AND (CASE WHEN requester_id = :me THEN addressee_id ELSE requester_id END)
                   NOT IN (SELECT id FROM users WHERE suspended = 1)),
           friends_of_friends AS (
               SELECT f.addressee_id AS id, m.id AS via
               FROM my_friends m JOIN friendships f ON f.requester_id = m.id WHERE f.status = 'accepted'
               UNION ALL
               SELECT f.requester_id, m.id
               FROM my_friends m JOIN friendships f ON f.addressee_id = m.id WHERE f.status = 'accepted'),
           played AS (
               SELECT r2.user_id AS id, COUNT(DISTINCT r2.event_id) AS games
               FROM rsvps r1 JOIN rsvps r2 ON r2.event_id = r1.event_id AND r2.user_id != r1.user_id
               JOIN events e ON e.id = r1.event_id AND e.cancelled = 0 AND e.ends_at < :now
               WHERE r1.user_id = :me GROUP BY r2.user_id),
           candidates AS (
               SELECT id, COUNT(DISTINCT via) AS mutual, MIN(via) AS via, 0 AS games FROM friends_of_friends GROUP BY id
               UNION ALL
               SELECT id, 0, NULL, games FROM played)
           SELECT s.*, v.full_name AS via_name FROM (
               SELECT u.id, u.full_name, u.avatar_updated, SUM(c.mutual) AS mutual, SUM(c.games) AS games,
                      MIN(c.via) AS via_id
               FROM candidates c JOIN users u ON u.id = c.id
               WHERE u.id != :me AND u.verified = 1 AND u.suspended = 0
                 AND u.id NOT IN (SELECT addressee_id FROM friendships WHERE requester_id = :me)
                 AND u.id NOT IN (SELECT requester_id FROM friendships WHERE addressee_id = :me)
                 AND u.id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = :me)
                 AND u.id NOT IN (SELECT blocker_id FROM blocks WHERE blocked_id = :me)
               GROUP BY u.id) s
           LEFT JOIN users v ON v.id = s.via_id
           ORDER BY s.mutual + s.games DESC, s.mutual DESC, fold(s.full_name)
           LIMIT :limit""",
        {"me": me, "now": to_db(now_local()), "limit": MAX_SUGGESTIONS}).fetchall()


def suggestion_reason(p):
    """ "Friends with Maya + 2 more · 3 games together" """
    parts = []
    if p["mutual"]:
        first = p["via_name"].split()[0] if p["via_name"] else "a friend"
        parts.append(f"Friends with {first}" + (f" + {p['mutual'] - 1} more" if p["mutual"] > 1 else ""))
    if p["games"]:
        parts.append(f"{p['games']} game{'s' if p['games'] != 1 else ''} together")
    return " · ".join(parts)


MIN_SEARCH_LENGTH = 2
MAX_SEARCH_LENGTH = 60
MAX_SEARCH_RESULTS = 20


def search_people(me, q):
    """Huskies whose name matches the search (first name, last name, or both), or whose UW NetID is exactly
    what was typed ("mchen7" or "mchen7@uw.edu"), for "Add friend".

    Only whole NetIDs match, so nobody can discover emails letter by letter. Each result carries clues to
    tell people with the same name apart: class year, mutual friends, and whether you've played together.
    People who blocked you (or you blocked) never appear.
    """
    if len(q) < MIN_SEARCH_LENGTH:
        return []
    words = fold(q).split()[:3]
    if not words:  # only accent marks or spaces: nothing left to look for
        return []
    params = {"me": me, "starts": words[0] + "%", "limit": MAX_SEARCH_RESULTS}
    for n, word in enumerate(words):
        params[f"w{n}"] = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    name_match = " AND ".join(f"fold(u.full_name) LIKE :w{n} ESCAPE '\\'" for n in range(len(words)))
    netid_match = "0"
    if len(words) == 1:
        netid = words[0].split("@")[0]
        domains = current_app.config["ALLOWED_EMAIL_DOMAINS"]
        params.update({f"e{n}": f"{netid}@{domain}" for n, domain in enumerate(domains)})
        netid_match = f"LOWER(u.email) IN ({', '.join(f':e{n}' for n in range(len(domains)))})"
    rows = get_db().execute(
        f"""WITH my_friends AS (  -- suspended friends don't count as mutual friends (nobody can see them)
               SELECT CASE WHEN requester_id = :me THEN addressee_id ELSE requester_id END AS id
               FROM friendships WHERE status = 'accepted' AND (requester_id = :me OR addressee_id = :me)
               AND (CASE WHEN requester_id = :me THEN addressee_id ELSE requester_id END)
                   NOT IN (SELECT id FROM users WHERE suspended = 1)),
            co_players AS (
               SELECT DISTINCT theirs.user_id FROM rsvps mine JOIN rsvps theirs ON mine.event_id = theirs.event_id
               JOIN events e ON e.id = mine.event_id WHERE mine.user_id = :me AND e.cancelled = 0)
            SELECT u.id, u.full_name, u.avatar_updated, u.grad_year, {netid_match} AS by_netid,
                   (SELECT COUNT(*) FROM friendships b WHERE b.status = 'accepted' AND b.requester_id = u.id
                      AND b.addressee_id IN my_friends)
                   + (SELECT COUNT(*) FROM friendships b WHERE b.status = 'accepted' AND b.addressee_id = u.id
                      AND b.requester_id IN my_friends) AS mutual,
                   u.id IN co_players AS played
            FROM users u
            WHERE u.verified = 1 AND u.suspended = 0 AND u.id != :me AND (({name_match}) OR {netid_match})
              AND u.id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = :me)
              AND u.id NOT IN (SELECT blocker_id FROM blocks WHERE blocked_id = :me)
            ORDER BY by_netid DESC, u.id IN my_friends DESC, played DESC, mutual DESC,
                     fold(u.full_name) LIKE :starts DESC, fold(u.full_name)
            LIMIT :limit""", params).fetchall()  # friends first: Messages search keeps only people you can message
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
    db = get_db()
    db.commit()
    db.execute("BEGIN IMMEDIATE")  # read and write together: two crossing requests can't both insert
    status = friendship_status(me, user_id)
    if user_id == me:
        flash("That's you!", "info")
    elif is_blocked_between(me, user_id):
        flash("You can't send a friend request to this person.", "error")
    elif status == "received":  # they already asked me: just accept
        db.execute("UPDATE friendships SET status = 'accepted' WHERE requester_id = ? AND addressee_id = ?",
                   (user_id, me))
        db.commit()
        flash("You're friends now!", "celebrate")
    elif status == "none":
        db.execute("INSERT OR IGNORE INTO friendships (requester_id, addressee_id, created_at) VALUES (?, ?, ?)",
                   (me, user_id, to_db(now_local())))
        db.commit()
        flash("Friend request sent!", "success")
    db.commit()
    return _back(url_for("profile.view", user_id=user_id))


@bp.route("/friends/accept/<int:user_id>", methods=("POST",))
@login_required
def accept_request(user_id):
    db = get_db()
    cur = db.execute("UPDATE friendships SET status = 'accepted' WHERE requester_id = ? AND addressee_id = ?"
                     " AND status = 'pending' AND requester_id IN (SELECT id FROM users WHERE suspended = 0)",
                     (user_id, g.user["id"]))
    db.commit()
    if cur.rowcount:
        flash("You're friends now!", "celebrate")
    return _back(url_for("social.friends"))


@bp.route("/friends/remove/<int:user_id>", methods=("POST",))
@login_required
def remove_friend(user_id):
    """Unfriend, cancel a request you sent, or decline one you got."""
    me = g.user["id"]
    db = get_db()
    db.execute("""DELETE FROM friendships WHERE (requester_id = ? AND addressee_id = ?)
                  OR (requester_id = ? AND addressee_id = ?)""", (me, user_id, user_id, me))
    cancel_invites_between(me, user_id)
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
        flash("Blocked. They can't message you, send you friend requests or join your games anymore.", "info")
    return redirect(url_for("profile.view", user_id=user_id))


@bp.route("/unblock/<int:user_id>", methods=("POST",))
@login_required
def unblock(user_id):
    db = get_db()
    db.execute("DELETE FROM blocks WHERE blocker_id = ? AND blocked_id = ?", (g.user["id"], user_id))
    db.commit()
    flash("Unblocked.", "info")
    if request.form.get("from") == "blocked":
        return redirect(url_for("social.blocked_people"))
    return redirect(url_for("profile.view", user_id=user_id))


@bp.route("/settings/blocked")
@login_required
def blocked_people():
    """Everyone I've blocked, so I can find and unblock them without remembering who they were."""
    people = get_db().execute(
        """SELECT u.id, u.full_name, u.avatar_updated, b.created_at FROM blocks b JOIN users u ON u.id = b.blocked_id
           WHERE b.blocker_id = ? ORDER BY b.created_at DESC""", (g.user["id"],)).fetchall()
    return render_template("settings/blocked.html", people=people)


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
             AND u.id NOT IN (SELECT blocker_id FROM blocks WHERE blocked_id = :me)
             AND u.suspended = 0
           ORDER BY m.id DESC""", {"me": me}).fetchall()
    # Friends I haven't messaged yet show too ("Start a chat"), so every friend is one tap away.
    talked = {c["id"] for c in conversations}
    new_friends = [f for f in friends_of(me) if f["id"] not in talked]
    q = one_line(request.args.get("q", ""))[:60]
    results = None
    if q:
        # Anyone I can message whose name (or exact UW NetID) matches: friends, people I've played with,
        # club officers, people who messaged me. Strangers only show up in Friends -> search, to add first.
        results = [p for p in search_people(me, q) if can_message(me, p["id"])]
    return render_template("social/inbox.html", conversations=conversations, new_friends=new_friends,
                           q=q, results=results, min_search=MIN_SEARCH_LENGTH)


MAX_SHOWN_MESSAGES = 500  # a chat shows its newest 500 messages, oldest first


def _thread_rows(me, other, after=0):
    return get_db().execute(
        f"""SELECT * FROM (
               SELECT m.*, u.full_name, u.avatar_updated, ge.title AS game_title, ge.sport AS game_sport,
                      ge.starts_at AS game_starts, ge.location AS game_location, ge.cancelled AS game_cancelled
               FROM direct_messages m JOIN users u ON u.id = m.sender_id
               LEFT JOIN events ge ON ge.id = m.event_id
               WHERE m.id > ? AND ((m.sender_id = ? AND m.recipient_id = ?) OR (m.sender_id = ? AND m.recipient_id = ?))
               ORDER BY m.id DESC LIMIT {MAX_SHOWN_MESSAGES}) ORDER BY id""", (after, me, other, other, me)).fetchall()


def _mark_read(me, other):
    db = get_db()
    db.execute("UPDATE direct_messages SET read_at = ? WHERE sender_id = ? AND recipient_id = ? AND read_at IS NULL",
               (to_db(now_local()), other, me))
    db.commit()


REACTIONS = ["❤️", "😂", "👍", "🔥", "😮", "😢"]  # hold a message to pick one; a double tap is ❤️


def _reaction_rows(kind, me, other_or_event, start):
    """Reactions on a chat's messages from id `start` on: (message_id, emoji, user_id) rows."""
    if kind == "dm":
        return get_db().execute(
            """SELECT r.message_id, r.emoji, r.user_id FROM message_reactions r
               JOIN direct_messages m ON m.id = r.message_id
               WHERE r.kind = 'dm' AND m.id >= ? AND ((m.sender_id = ? AND m.recipient_id = ?)
                                                   OR (m.sender_id = ? AND m.recipient_id = ?))""",
            (start, me, other_or_event, other_or_event, me)).fetchall()
    return get_db().execute(
        """SELECT r.message_id, r.emoji, r.user_id FROM message_reactions r
           JOIN event_messages m ON m.id = r.message_id
           WHERE r.kind = 'game' AND m.event_id = ? AND m.id >= ?
             AND r.user_id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = ?)""",
        (other_or_event, start, me)).fetchall()


def reactions_by_message(rows, me):
    """{message id: [{"emoji", "count", "mine"}, ...]} in the picker's order."""
    found = {}
    for row in rows:
        counts = found.setdefault(row["message_id"], {})
        entry = counts.setdefault(row["emoji"], {"emoji": row["emoji"], "count": 0, "mine": False})
        entry["count"] += 1
        entry["mine"] = entry["mine"] or row["user_id"] == me
    order = {emoji: i for i, emoji in enumerate(REACTIONS)}
    return {mid: sorted(counts.values(), key=lambda e: order.get(e["emoji"], 99)) for mid, counts in found.items()}


def with_reactions(messages, kind, me, other_or_event, start=None):
    """Adds each message's reactions (for the page and the poll)."""
    if start is None:
        start = messages[0]["id"] if messages else 0
    found = reactions_by_message(_reaction_rows(kind, me, other_or_event, start), me)
    for message in messages:
        message["reactions"] = found.get(message["id"], [])
    return messages, {str(mid): found[mid] for mid in found}


@bp.route("/chat/react", methods=("POST",))
@login_required
def react():
    """Toggle a reaction on a chat message: the same one again takes it off; another one replaces it."""
    me = g.user["id"]
    kind, emoji = request.form.get("kind"), request.form.get("emoji")
    message_id = request.form.get("id", type=int)
    if kind not in ("dm", "game") or emoji not in REACTIONS or not message_id:
        abort(400)
    db = get_db()
    if kind == "dm":
        message = db.execute("SELECT sender_id, recipient_id FROM direct_messages WHERE id = ?", (message_id,)).fetchone()
        if message is None or me not in (message["sender_id"], message["recipient_id"]):
            abort(404)
        other = message["recipient_id"] if message["sender_id"] == me else message["sender_id"]
        if is_blocked_between(me, other):
            abort(403)
        place = other
    else:
        message = db.execute("""SELECT m.event_id, m.sender_id, e.cancelled FROM event_messages m
                                JOIN events e ON e.id = m.event_id WHERE m.id = ?""", (message_id,)).fetchone()
        if message is None or is_blocked_between(me, message["sender_id"]):
            abort(404)  # a blocked person's messages are hidden from you, so they can't be reacted to either
        if message["cancelled"]:
            abort(403)  # the chat of a canceled game is closed
        if db.execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (message["event_id"], me)).fetchone() is None:
            abort(403)  # only people going can see (and react in) a game's chat
        place = message["event_id"]
    current = db.execute("SELECT emoji FROM message_reactions WHERE kind = ? AND message_id = ? AND user_id = ?",
                         (kind, message_id, me)).fetchone()
    if current is not None and current["emoji"] == emoji:
        db.execute("DELETE FROM message_reactions WHERE kind = ? AND message_id = ? AND user_id = ?",
                   (kind, message_id, me))
    else:
        db.execute("""INSERT INTO message_reactions (kind, message_id, user_id, emoji, created_at) VALUES (?, ?, ?, ?, ?)
                      ON CONFLICT(kind, message_id, user_id) DO UPDATE SET emoji = excluded.emoji,
                                                                          created_at = excluded.created_at""",
                   (kind, message_id, me, emoji, to_db(now_local())))
    db.commit()
    found = reactions_by_message(_reaction_rows(kind, me, place, message_id), me)
    return jsonify(id=message_id, reactions=found.get(message_id, []))


def dm_status(me, other):
    """What shows under my newest DM, if the newest message is mine: "Seen" once they've opened it, else
    "Delivered". Like WhatsApp, "Seen" only shows when both people have read receipts on."""
    db = get_db()
    last = db.execute("""SELECT id, sender_id, read_at FROM direct_messages
                         WHERE (sender_id = ? AND recipient_id = ?) OR (sender_id = ? AND recipient_id = ?)
                         ORDER BY id DESC LIMIT 1""", (me, other, other, me)).fetchone()
    if last is None or last["sender_id"] != me:
        return None
    receipts = db.execute("SELECT MIN(read_receipts) FROM users WHERE id IN (?, ?)", (me, other)).fetchone()[0]
    return {"id": last["id"], "text": "Seen" if last["read_at"] and receipts else "Delivered"}


def group_status(event_id, me):
    """Under my newest message in a game chat: "Seen" once everyone else going has seen it, else "Delivered".
    (Always on: the read receipts setting is for DMs.)"""
    db = get_db()
    last = db.execute("""SELECT id, sender_id FROM event_messages WHERE event_id = ?
                           AND sender_id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = ?)
                         ORDER BY id DESC LIMIT 1""", (event_id, me)).fetchone()
    if last is None or last["sender_id"] != me:
        return None
    others, behind = db.execute(
        """SELECT COUNT(*), COALESCE(SUM(COALESCE(s.last_id, 0) < :last), 0) FROM rsvps r
           LEFT JOIN event_chat_seen s ON s.event_id = r.event_id AND s.user_id = r.user_id
           WHERE r.event_id = :event AND r.user_id != :me""", {"last": last["id"], "event": event_id, "me": me}).fetchone()
    return {"id": last["id"], "text": "Seen" if others and not behind else "Delivered"}


@bp.route("/messages/<int:user_id>", methods=("GET", "POST"))
@login_required
def thread(user_id):
    me = g.user["id"]
    other = get_user(user_id)
    allowed = can_message(me, user_id)
    if request.method == "POST":
        error = None
        if not allowed:
            error = "You can message friends, people you've played with, and club officers."
        else:
            photo_id, error = read_chat_photo()
            body, error = (None, error) if error else clean_body(request.form.get("body"), photo=bool(photo_id))
            if error:
                get_db().rollback()
            else:
                db = get_db()
                db.execute("INSERT INTO direct_messages (sender_id, recipient_id, body, created_at, photo_id)"
                           " VALUES (?, ?, ?, ?, ?)", (me, user_id, body, to_db(now_local()), photo_id))
                db.commit()
        return chat_sent(error, url_for("social.thread", user_id=user_id) + "#composer")
    blocked_now = is_blocked_between(me, user_id)
    if not blocked_now:
        _mark_read(me, user_id)
    rows = _thread_rows(me, user_id) if not blocked_now else []
    messages, _ = with_reactions([message_json(r, me, 'dm') for r in rows], "dm", me, user_id)
    return render_template("social/thread.html", other=other, messages=messages,
                           allowed=allowed, poll_url=url_for("social.thread_poll", user_id=user_id), draft=take_draft(),
                           blocked=i_blocked(me, user_id), status=dm_status(me, user_id))


@bp.route("/messages/<int:user_id>/poll")
@login_required
def thread_poll(user_id):
    """New messages since ?after=<id> (the page asks every few seconds)."""
    me = g.user["id"]
    if is_blocked_between(me, user_id):
        return jsonify(messages=[])
    rows = _thread_rows(me, user_id, request.args.get("after", 0, type=int))
    _mark_read(me, user_id)
    messages, reactions = with_reactions([message_json(r, me, 'dm') for r in rows], "dm", me, user_id,
                                         start=request.args.get("from", 0, type=int))
    return jsonify(messages=messages, status=dm_status(me, user_id), reactions=reactions)


# -------------------------------------------------------------- event chat

def _event_for_chat(event_id):
    """The event (with player counts, like the event page), and whether I'm going to it.
    Everyone going, including the host, can chat."""
    from .events import get_event  # imported here: events.py also uses this module's helpers
    event = get_event(event_id)
    return event, bool(event["i_am_going"])


def _chat_rows(event_id, after=0):
    return get_db().execute(
        f"""SELECT * FROM (
               SELECT m.*, u.full_name, u.avatar_updated FROM event_messages m JOIN users u ON u.id = m.sender_id
               WHERE m.event_id = ? AND m.id > ?
                 AND m.sender_id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = ?)
               ORDER BY m.id DESC LIMIT {MAX_SHOWN_MESSAGES}) ORDER BY id""",
        (event_id, after, g.user["id"])).fetchall()


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
        flash("Join the game to use its chat.", "info")
        return redirect(url_for("events.detail", event_id=event_id))
    if request.method == "POST":
        photo_id, error = (None, None) if event["cancelled"] else read_chat_photo()
        body, error = (None, error) if error else clean_body(request.form.get("body"), photo=bool(photo_id))
        if error:
            get_db().rollback()
        elif event["cancelled"]:
            error = "This game was canceled, so its chat is closed."
        else:
            db = get_db()
            db.execute("INSERT INTO event_messages (event_id, sender_id, body, created_at, photo_id) VALUES (?, ?, ?, ?, ?)",
                       (event_id, g.user["id"], body, to_db(now_local()), photo_id))
            db.commit()
        return chat_sent(error, url_for("social.event_chat", event_id=event_id) + "#composer")
    rows = _chat_rows(event_id)
    _mark_chat_seen(event_id, rows)
    people = get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (event_id,)).fetchone()[0]
    messages, _ = with_reactions([message_json(r, g.user["id"], 'event_message') for r in rows], "game",
                                 g.user["id"], event_id)
    return render_template("social/event_chat.html", event=event, people=people, messages=messages,
                           poll_url=url_for("social.event_chat_poll", event_id=event_id),
                           when=fmt_when(event["starts_at"]), draft=take_draft(),
                           status=group_status(event_id, g.user["id"]))


@bp.route("/events/<int:event_id>/chat/poll")
@login_required
def event_chat_poll(event_id):
    _, going = _event_for_chat(event_id)
    if not going:
        abort(403)
    rows = _chat_rows(event_id, request.args.get("after", 0, type=int))
    _mark_chat_seen(event_id, rows)
    messages, reactions = with_reactions([message_json(r, g.user["id"], 'event_message') for r in rows], "game",
                                         g.user["id"], event_id, start=request.args.get("from", 0, type=int))
    return jsonify(messages=messages, status=group_status(event_id, g.user["id"]), reactions=reactions)


@bp.route("/chat-photos/<int:photo_id>")
@login_required
def chat_photo(photo_id):
    """A photo from a chat, only for the people in that chat (the two people in a DM, or the game's players)."""
    me = g.user["id"]
    db = get_db()
    dm = db.execute("SELECT sender_id, recipient_id FROM direct_messages WHERE photo_id = ?", (photo_id,)).fetchone()
    game = db.execute("SELECT event_id FROM event_messages WHERE photo_id = ?", (photo_id,)).fetchone()
    allowed = (dm is not None and me in (dm["sender_id"], dm["recipient_id"])
               and not is_blocked_between(dm["sender_id"], dm["recipient_id"])) or (
        game is not None and db.execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?",
                                        (game["event_id"], me)).fetchone() is not None)
    row = db.execute("SELECT image FROM chat_photos WHERE id = ?", (photo_id,)).fetchone() if allowed else None
    if row is None:
        abort(404)
    response = Response(row["image"], mimetype="image/jpeg")
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"  # a photo never changes
    return response
