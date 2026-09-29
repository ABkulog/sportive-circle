"""Notifications: the 🔔 bell, and numbers on the icons.

Everything new shows up in exactly ONE place, so nothing is counted twice:
- on its own icon when it has a home there: messages (✉️), friend requests (👥), club news (Clubs tab);
- in the bell for everything else: invites, changes to your games, game chats, Need players posts, badges.

Each kind can be switched on or off in Settings -> Notifications. Nothing is pushed or emailed from here.

Two sorts of things show up:
- counts worked out from the data (unread messages, new club updates...), and
- notices: one-off messages saved for one person ("Maya changed the time of Sunday soccer", an invite,
  a reminder to add a photo). A newer notice about the same thing replaces the older one (the `key`),
  so a host editing a game three times means one notice, not three. Opening the bell marks them as read.
"""
from collections import namedtuple
from datetime import timedelta

from flask import Blueprint, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db, user_sports
from .social import event_chat_unread
from .timeutil import now_local, to_db

bp = Blueprint("notifications", __name__)

# key, emoji, its name in Settings, where it shows up ("bell" or an icon/tab), who it's for.
Kind = namedtuple("Kind", "key emoji label place audience")

KINDS = [
    Kind("invites", "🙌", "Invites to games", "bell", "everyone"),
    Kind("game_updates", "📅", "Changes to games you joined", "bell", "everyone"),
    Kind("game_chat", "💬", "Your games' group chats", "bell", "everyone"),
    Kind("need_players", "⚡", "Need players posts for your sports", "bell", "everyone"),
    Kind("badges", "🏅", "Badges you earn", "bell", "everyone"),
    Kind("account", "👤", "Tips about your account", "bell", "everyone"),
    Kind("messages", "✉️", "Direct messages", "messages", "everyone"),
    Kind("friend_requests", "👥", "Friend requests", "friends", "everyone"),
    Kind("club_updates", "📣", "Updates from your clubs", "clubs", "everyone"),
    Kind("club_requests", "🙋", "People asking to join your club", "clubs", "officers"),
    Kind("suggestion_trends", "💡", "Suggestion topics 3+ people bring up", "admin", "admins"),
]
PLACE_NAMES = {"bell": "In the bell", "messages": "On the messages icon", "friends": "On the friends icon",
               "clubs": "On the Clubs tab", "admin": "On the admin icon"}
NOTICE_KINDS = ("invites", "game_updates", "account")  # saved as notices (the rest are counted)
NOTICE_DAYS = 30  # the bell shows notices from the last month
KIND_BY_KEY = {kind.key: kind for kind in KINDS}
TABS = ("home", "clubs", "profile", "messages", "friends", "admin")


# ---------------------------------------------------------------- settings

def settings(user_id):
    """{kind: on?} Everything is on unless this person switched it off. (Older rows stored two switches,
    "badge" and "screen"; either one on counts as on.)"""
    chosen = {row["kind"]: bool(row["badge"] or row["screen"]) for row in get_db().execute(
        "SELECT kind, badge, screen FROM notification_settings WHERE user_id = ?", (user_id,))}
    return {kind.key: chosen.get(kind.key, True) for kind in KINDS}


def save_settings(user_id, form, shown):
    """Save the switches that were on the page (`shown`). Kinds that weren't shown (club requests for
    someone who isn't an officer yet) keep their setting, instead of being saved as off."""
    db = get_db()
    db.executemany(
        "INSERT OR REPLACE INTO notification_settings (user_id, kind, badge, screen) VALUES (?, ?, ?, ?)",
        [(user_id, kind.key, 1 if form.get(kind.key) else 0, 1 if form.get(kind.key) else 0) for kind in shown])
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

def notify(user_id, kind, text, url, key=None):
    """Save a notice for one person (shown in their bell). A notice with the same `key` (e.g. "change:7" for
    game 7) replaces the older one, so the bell never repeats itself. The caller commits."""
    assert kind in NOTICE_KINDS, kind
    db = get_db()
    if key:
        db.execute("DELETE FROM notices WHERE user_id = ? AND key = ?", (user_id, key))
    db.execute("INSERT INTO notices (user_id, kind, text, url, created_at, key) VALUES (?, ?, ?, ?, ?, ?)",
               (user_id, kind, text, url, to_db(now_local()), key))


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
    """{kind: how many new} for the logged-in person, for the kinds they have on (once per page)."""
    if "notification_counts" not in g:
        g.notification_counts = {}
        if g.get("user") is not None:
            chosen = settings(g.user["id"])
            g.notification_counts = {kind.key: _count(kind.key, g.user["id"]) for kind in KINDS if chosen[kind.key]}
    return g.notification_counts


def tab_badges():
    """{tab: number on its icon}: only the kinds that live on that icon (never the bell's)."""
    totals = dict.fromkeys(TABS, 0)
    for key, n in counts().items():
        place = KIND_BY_KEY[key].place
        if place != "bell":
            totals[place] += n
    return totals


def bell_count():
    """The number on the bell: only the kinds that live in the bell."""
    return sum(n for key, n in counts().items() if KIND_BY_KEY[key].place == "bell")


def bell_items():
    """[(emoji, text, url)] for what's counted rather than saved as notices: game chats (one line per game),
    Need players posts and badges. Written as sentences."""
    found = counts()
    items = []
    if found.get("game_chat"):
        from .events import event_title, query_events  # imported here because events.py imports this module
        unread = event_chat_unread()
        games = {e["id"]: e for e in query_events([f"e.id IN ({', '.join(str(int(i)) for i in unread)})"])} if unread else {}
        for event_id, n in sorted(unread.items(), key=lambda item: -item[1]):
            if event_id in games and n:
                items.append(("💬", f"{n} new message{'s' if n != 1 else ''} in {event_title(games[event_id])}",
                              url_for("social.event_chat", event_id=event_id)))
    if found.get("need_players"):
        n = found["need_players"]
        items.append(("⚡", f"{n} new Need players post{'s' if n != 1 else ''} for your sports",
                      url_for("events.feed", _anchor="now")))
    if found.get("badges"):
        n = found["badges"]
        items.append(("🏅", "You earned a new badge" if n == 1 else f"You earned {n} new badges",
                      url_for("profile.badge_locker")))
    return items


def badge_text(n):
    return "9+" if n > 9 else str(n)


# ---------------------------------------------------------------- the bell page

@bp.route("/notifications")
@login_required
def bell():
    me = g.user["id"]
    chosen = settings(me)
    items = bell_items()
    notices = [notice for notice in recent_notices(me) if chosen[notice["kind"]]]
    db = get_db()
    # Only what was shown counts as read: a kind switched off now still shows up if it's switched back on.
    shown_kinds = [kind for kind in NOTICE_KINDS if chosen[kind]]
    if shown_kinds:
        db.execute(f"UPDATE notices SET read_at = ? WHERE user_id = ? AND read_at IS NULL"
                   f" AND kind IN ({', '.join('?' for _ in shown_kinds)})", (to_db(now_local()), me, *shown_kinds))
    db.commit()
    g.pop("notification_counts", None)  # the bell in the top bar shows 0 on this page
    return render_template("notifications/bell.html", items=items, notices=notices, kinds=KIND_BY_KEY)


# ---------------------------------------------------------------- Settings -> Notifications

def kinds_for(user_id):
    """The kinds this person can get (club requests only for officers, trends only for admins)."""
    from .moderation import is_admin
    is_officer = get_db().execute(
        "SELECT 1 FROM club_members WHERE user_id = ? AND role = 'officer' LIMIT 1", (user_id,)).fetchone() is not None
    return [kind for kind in KINDS if kind.audience == "everyone" or (kind.audience == "officers" and is_officer)
            or (kind.audience == "admins" and is_admin())]


@bp.route("/settings/notifications", methods=("GET", "POST"))
@login_required
def notification_settings():
    me = g.user["id"]
    if request.method == "POST":
        save_settings(me, request.form, kinds_for(me))
        return redirect(url_for("notifications.notification_settings"))  # the switches show what's saved
    return render_template("settings/notifications.html", kinds=kinds_for(me), chosen=settings(me),
                           places=PLACE_NAMES)


@bp.route("/profile/notifications")
@login_required
def old_notification_settings():
    return redirect(url_for("notifications.notification_settings"))
