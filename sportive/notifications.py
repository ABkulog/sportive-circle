"""Notifications: numbers on the tab icons, and the 🔔 bell at the top.

People choose, for each kind of notification, whether it shows on the tab icons, in the bell,
both, or neither (Profile -> Edit profile -> Notifications). Nothing is ever pushed from here, so
nobody gets spammed.

Two sorts of things show up:
- counts worked out from the data (unread messages, new club updates...), and
- notices: one-off messages saved for one person ("Maya changed the time of Sunday soccer",
  an invite, a reminder to add a photo). Opening the bell marks them as read.

"New" means newer than the last time you looked: opening Club updates clears the club number, opening
your badges clears the badge number, and so on. Those "last looked" markers live in the seen_markers table.
"""
from collections import namedtuple
from datetime import timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db, user_sports
from .social import event_chat_unread
from .timeutil import now_local, to_db

bp = Blueprint("notifications", __name__)

# key, emoji, what it's about, which tab/icon shows the number, default for (tab icon, bell), link text.
# (The bell setting is stored in the "screen" column.)
Kind = namedtuple("Kind", "key emoji label tab badge screen link")

KINDS = [
    Kind("invites", "🙌", "Invites from friends", "home", True, True, "invite"),
    Kind("game_updates", "📅", "Changes to games you're going to", "home", True, True, "game update"),
    Kind("messages", "✉️", "Direct messages", "messages", True, True, "new message"),
    Kind("friend_requests", "👥", "Friend requests", "friends", True, True, "friend request"),
    Kind("game_chat", "💬", "Group chats of games you're going to", "home", True, True, "new message in your games' chats"),
    Kind("need_players", "⚡", "New \"Need players\" posts for your sports", "home", False, True, "new Need players post"),
    Kind("club_updates", "📣", "Updates from clubs you follow or joined", "clubs", True, True, "new club update"),
    Kind("club_requests", "🙋", "People asking to join a club you run", "clubs", True, True, "person waiting to join your club"),
    Kind("badges", "🏅", "New badges you earned", "profile", True, True, "new badge"),
    Kind("suggestion_trends", "💡", "Suggestion topics 3+ people asked for (admins)", "admin", True, True,
         "suggestion topic trending"),
    Kind("account", "👤", "Tips about your account", "profile", False, True, "tip"),
]
NOTICE_KINDS = ("invites", "game_updates", "account")  # saved as notices (the rest are counted)
NOTICE_DAYS = 30  # the bell shows notices from the last month
KIND_BY_KEY = {kind.key: kind for kind in KINDS}
TABS = ("home", "clubs", "profile", "messages", "friends", "admin")


# ---------------------------------------------------------------- settings

def settings(user_id):
    """{kind: {"badge": bool, "screen": bool}}: the defaults, plus whatever this person changed."""
    chosen = {row["kind"]: row for row in get_db().execute(
        "SELECT kind, badge, screen FROM notification_settings WHERE user_id = ?", (user_id,))}
    return {kind.key: {"badge": bool(chosen[kind.key]["badge"]) if kind.key in chosen else kind.badge,
                       "screen": bool(chosen[kind.key]["screen"]) if kind.key in chosen else kind.screen}
            for kind in KINDS}


def save_settings(user_id, form):
    db = get_db()
    db.executemany(
        "INSERT OR REPLACE INTO notification_settings (user_id, kind, badge, screen) VALUES (?, ?, ?, ?)",
        [(user_id, kind.key, 1 if form.get(f"{kind.key}_badge") else 0, 1 if form.get(f"{kind.key}_screen") else 0)
         for kind in KINDS])
    db.commit()


# ---------------------------------------------------------------- "last looked" markers

def _marker(user_id, kind):
    row = get_db().execute("SELECT value FROM seen_markers WHERE user_id = ? AND kind = ?",
                           (user_id, kind)).fetchone()
    return row["value"] if row else None


def _set_marker(user_id, kind, value):
    get_db().execute("INSERT OR REPLACE INTO seen_markers (user_id, kind, value) VALUES (?, ?, ?)",
                     (user_id, kind, str(value)))


def _latest(kind):
    """The newest thing of this kind right now (an id, or a time), to remember as "seen"."""
    db = get_db()
    if kind == "need_players":
        return db.execute("SELECT COALESCE(MAX(id), 0) FROM events WHERE is_quick = 1").fetchone()[0]
    if kind == "club_updates":
        return db.execute("SELECT COALESCE(MAX(id), 0) FROM club_posts").fetchone()[0]
    return to_db(now_local())  # badges: by time


def mark_seen(kind):
    """Call when someone opens the place a notification points to (e.g. the News tab)."""
    if g.get("user") is None:
        return
    _set_marker(g.user["id"], kind, _latest(kind))
    get_db().commit()
    g.pop("notification_counts", None)


def start_markers(user_id):
    """For a brand-new account: everything that exists right now counts as already seen, and
    anything posted from now on is new."""
    for kind in ("need_players", "club_updates", "badges"):
        _set_marker(user_id, kind, _latest(kind))


def seen_value(kind):
    """The logged-in person's "last looked" marker for any kind (None if they never looked)."""
    return _marker(g.user["id"], kind) if g.get("user") is not None else None


def mark_seen_value(kind, value):
    if g.get("user") is not None:
        _set_marker(g.user["id"], kind, value)
        get_db().commit()


def _since(user_id, kind):
    """The marker. Accounts made before notifications existed get one on first use."""
    value = _marker(user_id, kind)
    if value is None:
        value = _latest(kind)
        _set_marker(user_id, kind, value)
        get_db().commit()
    return value


# ---------------------------------------------------------------- notices

def notify(user_id, kind, text, url):
    """Save a notice for one person (shown in their bell). The caller commits."""
    assert kind in NOTICE_KINDS, kind
    get_db().execute("INSERT INTO notices (user_id, kind, text, url, created_at) VALUES (?, ?, ?, ?, ?)",
                     (user_id, kind, text, url, to_db(now_local())))


def recent_notices(user_id):
    since = to_db(now_local() - timedelta(days=NOTICE_DAYS))
    return get_db().execute("SELECT * FROM notices WHERE user_id = ? AND created_at >= ? ORDER BY id DESC LIMIT 50",
                            (user_id, since)).fetchall()


# ---------------------------------------------------------------- counting

def _count(kind, me):
    db = get_db()
    now = to_db(now_local())
    if kind in NOTICE_KINDS:
        return db.execute("SELECT COUNT(*) FROM notices WHERE user_id = ? AND kind = ? AND read_at IS NULL",
                          (me, kind)).fetchone()[0]
    if kind == "messages":
        return db.execute(
            """SELECT COUNT(*) FROM direct_messages WHERE recipient_id = ? AND read_at IS NULL
               AND sender_id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = ?)""", (me, me)).fetchone()[0]
    if kind == "friend_requests":
        return db.execute("SELECT COUNT(*) FROM friendships WHERE addressee_id = ? AND status = 'pending'",
                          (me,)).fetchone()[0]
    if kind == "game_chat":
        return sum(event_chat_unread().values())
    if kind == "need_players":
        from .events import games_open_to_me  # imported here because events.py imports this module
        sports = user_sports(me)
        if not sports:
            return 0
        marks = ", ".join("?" for _ in sports)
        return db.execute(
            f"""SELECT COUNT(*) FROM events e
                WHERE e.is_quick = 1 AND e.is_private = 0 AND e.cancelled = 0 AND e.ends_at >= ? AND e.host_id != ?
                  AND e.id > ? AND {games_open_to_me()}
                  AND (e.max_players IS NULL
                       OR e.extra_players + (SELECT COUNT(*) FROM rsvps x WHERE x.event_id = e.id) < e.max_players)
                  AND e.sport IN ({marks})
                  AND NOT EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = ?)
                  AND NOT EXISTS (SELECT 1 FROM blocks b WHERE (b.blocker_id = ? AND b.blocked_id = e.host_id)
                                                          OR (b.blocker_id = e.host_id AND b.blocked_id = ?))""",
            (now, me, int(_since(me, kind)), *sports, me, me, me)).fetchone()[0]
    if kind == "club_updates":
        return db.execute(
            """SELECT COUNT(*) FROM club_posts p JOIN clubs c ON c.id = p.club_id
               WHERE c.status = 'approved' AND p.id > ? AND (p.author_id IS NULL OR p.author_id != ?)
                 AND EXISTS (SELECT 1 FROM club_members m WHERE m.club_id = c.id AND m.user_id = ?)""",
            (int(_since(me, kind)), me, me)).fetchone()[0]
    if kind == "club_requests":
        return db.execute(
            """SELECT COUNT(*) FROM club_members waiting JOIN club_members mine ON mine.club_id = waiting.club_id
               WHERE mine.user_id = ? AND mine.role = 'officer' AND waiting.role IN ('requested', 'tryout')""",
            (me,)).fetchone()[0]
    if kind == "badges":
        return db.execute("SELECT COUNT(*) FROM user_badges WHERE user_id = ? AND earned_at > ?",
                          (me, _since(me, kind))).fetchone()[0]
    if kind == "suggestion_trends":
        from .feedback import unseen_trends  # imported here because feedback.py imports this module
        return len(unseen_trends())
    raise ValueError(kind)


def counts():
    """{kind: how many new} for the logged-in person (computed once per page)."""
    if "notification_counts" not in g:
        g.notification_counts = {}
        if g.get("user") is not None:
            chosen = settings(g.user["id"])
            for kind in KINDS:
                if chosen[kind.key]["badge"] or chosen[kind.key]["screen"]:
                    g.notification_counts[kind.key] = _count(kind.key, g.user["id"])
            g.notification_settings = chosen
    return g.notification_counts


def tab_badges():
    """{tab: number to show on its icon}, only counting the kinds this person wants on their icons."""
    totals = dict.fromkeys(TABS, 0)
    found = counts()
    for kind in KINDS:
        if found.get(kind.key) and g.notification_settings[kind.key]["badge"]:
            totals[kind.tab] += found[kind.key]
    return totals


LINKS = {
    "messages": ("social.inbox", {}), "friend_requests": ("social.friends", {}),
    "game_chat": ("events.my_events", {}), "need_players": ("events.feed", {"_anchor": "now"}),
    "club_updates": ("clubs.updates", {}), "club_requests": ("clubs.directory", {"mine": 1}),  # officers' club cards show who's waiting
    "badges": ("profile.badge_locker", {}),
    "suggestion_trends": ("feedback.admin_suggestions", {}),
}


def bell_items():
    """[(emoji, text, url)] for the bell: counted kinds this person wants in the bell (notices are listed
    one by one on the bell page instead)."""
    items = []
    found = counts()
    for kind in KINDS:
        n = found.get(kind.key)
        if n and g.notification_settings[kind.key]["screen"] and kind.key not in NOTICE_KINDS:
            endpoint, values = LINKS[kind.key]
            text = f"{n} {kind.link}{'' if n == 1 else 's'}".replace("persons", "people")
            if kind.key == "game_chat" and n != 1:
                text = f"{n} new messages in your games' chats"
            if kind.key == "suggestion_trends":
                text = "1 suggestion topic is trending" if n == 1 else f"{n} suggestion topics are trending"
            items.append((kind.emoji, text, url_for(endpoint, **values)))
    return items


def bell_count():
    """The number on the bell: everything new this person wants in the bell."""
    found = counts()
    return sum(n for key, n in found.items() if g.notification_settings[key]["screen"])


def badge_text(n):
    return "9+" if n > 9 else str(n)


# ---------------------------------------------------------------- the bell page

@bp.route("/notifications")
@login_required
def bell():
    me = g.user["id"]
    items, notices = bell_items(), recent_notices(me)
    chosen = settings(me)
    notices = [notice for notice in notices if chosen[notice["kind"]]["screen"]]
    db = get_db()
    db.execute("UPDATE notices SET read_at = ? WHERE user_id = ? AND read_at IS NULL", (to_db(now_local()), me))
    db.commit()
    g.pop("notification_counts", None)  # the bell in the top bar shows 0 on this page
    return render_template("notifications/bell.html", items=items, notices=notices, kinds=KIND_BY_KEY)


# ---------------------------------------------------------------- settings page

@bp.route("/profile/notifications", methods=("GET", "POST"))
@login_required
def notification_settings():
    me = g.user["id"]
    if request.method == "POST":
        save_settings(me, request.form)
        flash("Notification settings saved.", "success")
        return redirect(url_for("notifications.notification_settings"))
    is_officer = get_db().execute(
        "SELECT 1 FROM club_members WHERE user_id = ? AND role = 'officer' LIMIT 1", (me,)).fetchone() is not None
    from .moderation import is_admin
    kinds = [kind for kind in KINDS
             if (kind.key != "club_requests" or is_officer) and (kind.key != "suggestion_trends" or is_admin())]
    return render_template("profile/notifications.html", kinds=kinds, chosen=settings(me))
