"""The feed: what's going on in sports on campus, in one place.

People post with a sport tag (words, up to 10 photos), and a post can be a plan ("hiking Mt Si tomorrow, have a
car, need 2"): a real game behind the scenes, so "I'm in" gives it a headcount, a group chat and a reminder.
The feed mixes those posts with what the app already makes: new games, club updates and club events, for the
sports you picked. Tapping a sport tag shows just that sport (its "channel").
"""
from datetime import timedelta

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required, safe_next
from .clubs import MEMBER_ROLES
from .constants import LOCATIONS, OFF_CAMPUS, SPORT_LOCATIONS, SPORTS
from .db import get_db, user_sports
from .events import (MEMBERS_ONLY_FOR_MEMBERS, NOT_BLOCKED, SHOWN_UNLESS_FULL, games_open_to_me, insert_event,
                     posting_too_fast, query_events)
from .friendgames import announce_new_game
from .moderation import is_admin
from .photos import make_chat_photo
from .placehours import closed_message
from .social import is_blocked_between
from .textutil import multi_line
from .timeutil import add_real, exists_in_seattle, from_sqlite_utc, now_local, parse_form, to_db

bp = Blueprint("posts", __name__)

MAX_BODY = 1000          # characters in a post
MAX_PHOTOS = 10          # photos in one post
MAX_POST_UPLOAD_MB = 80  # all of a post's photos together (each one is shrunk to ~200 KB when saved)
POSTS_PER_HOUR = 10      # stops one person (or a script) flooding everyone's feed
PAGE = 25                # feed items per page ("Show older")
NEW_GAME_DAYS = 14       # new games show up in the feed for this long (while they're still to come)
PLAN_DAYS_AHEAD = 60     # how far ahead a plan can be
PLAN_DURATIONS = [(60, "1 hour"), (120, "2 hours"), (180, "3 hours"), (240, "4 hours"), (480, "All day")]
MAX_PLAN_SPOTS = 50

# Posts by people I blocked (or who blocked me), or by suspended people, never show.
POST_VISIBLE = """u.suspended = 0 AND NOT EXISTS (SELECT 1 FROM blocks b
                     WHERE (b.blocker_id = :me AND b.blocked_id = p.author_id)
                        OR (b.blocker_id = p.author_id AND b.blocked_id = :me))"""


# Replies whose author I can see (not suspended, no block either way), as SQL on post_replies r / users ru.
REPLY_VISIBLE = """ru.suspended = 0 AND NOT EXISTS (SELECT 1 FROM blocks b
                      WHERE (b.blocker_id = :me AND b.blocked_id = r.author_id)
                         OR (b.blocker_id = r.author_id AND b.blocked_id = :me))"""
POST_COUNTS = f"""(SELECT COUNT(*) FROM post_photos ph WHERE ph.post_id = p.id) AS photo_count,
                  (SELECT COUNT(*) FROM post_likes l JOIN users lu ON lu.id = l.user_id
                   WHERE l.post_id = p.id AND lu.suspended = 0) AS like_count,
                  EXISTS (SELECT 1 FROM post_likes l WHERE l.post_id = p.id AND l.user_id = :me) AS i_liked,
                  (SELECT COUNT(*) FROM post_replies r JOIN users ru ON ru.id = r.author_id
                   WHERE r.post_id = p.id AND {REPLY_VISIBLE}) AS reply_count"""
MAX_REPLY = 500
REPLIES_PER_HOUR = 30


def _sports_clause(column, sports, params):
    names = [f":sp{i}" for i in range(len(sports))]
    params.update({f"sp{i}": sport for i, sport in enumerate(sports)})
    return f"{column} IN ({', '.join(names)})"


def _events_by_id(ids):
    """The games behind plan posts and club event posts, with the rules for who can see what (blocked hosts,
    members-only events, who a game is open to). A game you can't see isn't in the result."""
    if not ids:
        return {}
    params = {f"id{i}": event_id for i, event_id in enumerate(ids)}
    rows = query_events([f"e.id IN ({', '.join(':' + key for key in params)})", NOT_BLOCKED, MEMBERS_ONLY_FOR_MEMBERS,
                         "(e.is_private = 0 OR EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me))"],
                        params, limit=len(ids))
    return {row["id"]: row for row in rows}


def feed_items(sport=None, before=None, limit=PAGE):
    """The feed for the person logged in: posts, club updates and new games, newest first.
    sport: one sport's channel. before: a Seattle-time string, for "Show older".
    Returns (items, older) where older is the `before` value for the next page, or None."""
    db = get_db()
    me = g.user["id"]
    sports = [sport] if sport else (user_sports(me) or list(SPORTS))
    params = {"me": me, "limit": limit + 1, "before": before or "9999"}
    items = []

    # 1. What people posted (your own posts always show in your feed, whatever their sport)
    in_sports = _sports_clause("p.sport", sports, params)
    mine = "" if sport else " OR p.author_id = :me"
    for row in db.execute(
            f"""SELECT p.*, u.full_name, u.avatar_updated, {POST_COUNTS}
                FROM posts p JOIN users u ON u.id = p.author_id
                WHERE ({in_sports}{mine}) AND {POST_VISIBLE} AND p.created_at < :before
                ORDER BY p.created_at DESC, p.id DESC LIMIT :limit""", params).fetchall():
        items.append({"kind": "post", "at": row["created_at"], "post": row})

    # 2. Club updates (and the automatic "New event" posts): verified clubs in these sports, and clubs you're in or
    # follow (in the full feed)
    club_sports = _sports_clause("c.sport", sports, params)
    mine = "" if sport else " OR EXISTS (SELECT 1 FROM club_members m WHERE m.club_id = c.id AND m.user_id = :me)"
    for row in db.execute(
            f"""SELECT cp.*, c.name AS club_name, c.sport, c.logo_updated AS club_logo,
                       (SELECT m.role FROM club_members m WHERE m.club_id = c.id AND m.user_id = :me) AS my_role
                FROM club_posts cp JOIN clubs c ON c.id = cp.club_id
                WHERE c.status = 'approved' AND ({club_sports}{mine}) AND cp.created_at < :before
                ORDER BY cp.created_at DESC, cp.id DESC LIMIT :limit""", params).fetchall():
        items.append({"kind": "club_post", "at": row["created_at"], "club_post": row})

    # 3. New games people posted (not club events, which come as club updates, and not plan posts, which are posts)
    now = now_local()
    game_params = {"now": to_db(now), "since": (now - timedelta(days=NEW_GAME_DAYS)).strftime("%Y-%m-%d")}
    game_sports = _sports_clause("e.sport", sports, game_params)
    for row in query_events(
            ["e.cancelled = 0", "e.ends_at >= :now", "e.club_id IS NULL", "e.is_private = 0", game_sports,
             "NOT EXISTS (SELECT 1 FROM posts p WHERE p.event_id = e.id)", "e.created_at >= :since",
             NOT_BLOCKED, games_open_to_me(), SHOWN_UNLESS_FULL],
            game_params, order="e.created_at DESC", limit=limit + 1):
        posted = to_db(from_sqlite_utc(row["created_at"]))  # (SQLite's UTC -> Seattle time)
        if posted < params["before"]:
            items.append({"kind": "game", "at": posted, "event": row})

    # 4. Husky news: scores and results from UW's teams in these sports (from GoHuskies.com)
    from .news import feed_news
    items += feed_news(sports, params["before"], limit + 1, channel=bool(sport))

    items.sort(key=lambda item: item["at"], reverse=True)
    older = items[limit - 1]["at"] if len(items) > limit else None
    items = items[:limit]
    # The games behind plan posts and club event posts, for their "I'm in" buttons
    events = _events_by_id([i["post"]["event_id"] for i in items if i["kind"] == "post" and i["post"]["event_id"]]
                           + [i["club_post"]["event_id"] for i in items
                              if i["kind"] == "club_post" and i["club_post"]["event_id"]])
    for item in items:
        source = item.get("post") or item.get("club_post")
        item["event"] = item.get("event") or (events.get(source["event_id"]) if source and source["event_id"] else None)
    return items, older


def photos_of(post_ids):
    """{post id: [photo positions]} for the posts on the page."""
    if not post_ids:
        return {}
    marks = ", ".join("?" for _ in post_ids)
    photos = {}
    for row in get_db().execute(f"SELECT post_id, position FROM post_photos WHERE post_id IN ({marks})"
                                " ORDER BY post_id, position", list(post_ids)):
        photos.setdefault(row["post_id"], []).append(row["position"])
    return photos


@bp.route("/feed")
@login_required
def feed():
    sport = request.args.get("sport", "")
    sport = sport if sport in SPORTS else None
    before = request.args.get("before", "")
    before = before if len(before) == 16 and before[:4].isdigit() else None
    items, older = feed_items(sport, before)
    if not sport and not before:
        from .notifications import mark_seen  # (notifications.py is loaded after this module)
        mark_seen("feed_posts")  # the new-posts number on Home is cleared once you've seen the top of your feed
    return render_template("feed/feed.html", items=items, older=older, sport=sport, my_sports=user_sports(g.user["id"]),
                           photos=photos_of([i["post"]["id"] for i in items if i["kind"] == "post"]),
                           durations=PLAN_DURATIONS, max_photos=MAX_PHOTOS, max_body=MAX_BODY, form={},
                           member_roles=MEMBER_ROLES)


def get_post(post_id):
    """A post the person logged in can see (or 404)."""
    post = get_db().execute(
        f"""SELECT p.*, u.full_name, u.avatar_updated, {POST_COUNTS}
            FROM posts p JOIN users u ON u.id = p.author_id WHERE p.id = :id AND {POST_VISIBLE}""",
        {"id": post_id, "me": g.user["id"]}).fetchone()
    if post is None:
        abort(404)
    return post


@bp.route("/posts/<int:post_id>")
@login_required
def view(post_id):
    """One post on its own page (for links from notifications, reports and sharing)."""
    post = get_post(post_id)
    event = _events_by_id([post["event_id"]]).get(post["event_id"]) if post["event_id"] else None
    replies = get_db().execute(
        f"""SELECT r.*, ru.full_name, ru.avatar_updated FROM post_replies r JOIN users ru ON ru.id = r.author_id
            WHERE r.post_id = :id AND {REPLY_VISIBLE} ORDER BY r.id""", {"id": post_id, "me": g.user["id"]}).fetchall()
    return render_template("feed/post.html", item={"kind": "post", "at": post["created_at"], "post": post,
                                                   "event": event},
                           photos=photos_of([post_id]), replies=replies, max_reply=MAX_REPLY)


def _can_interact(post):
    """Replying and 🔥 aren't for blocked pairs (get_post already hides the post from them)."""
    return post["author_id"] == g.user["id"] or not is_blocked_between(g.user["id"], post["author_id"])


def _tell_author(post, text, key):
    """A notice in the post author's bell (one per post and kind, replaced as more come in)."""
    if post["author_id"] != g.user["id"]:
        from .notifications import notify  # (notifications.py is loaded after this module)
        notify(post["author_id"], "post_activity", text, url_for("posts.view", post_id=post["id"]), key=key)


@bp.route("/posts/<int:post_id>/like", methods=("POST",))
@login_required
def like(post_id):
    """🔥 a post, or take it back (a second tap)."""
    post = get_post(post_id)
    if not _can_interact(post):
        abort(403)
    db = get_db()
    me = g.user["id"]
    if db.execute("DELETE FROM post_likes WHERE post_id = ? AND user_id = ?", (post_id, me)).rowcount == 0:
        db.execute("INSERT INTO post_likes (post_id, user_id, created_at) VALUES (?, ?, ?)",
                   (post_id, me, to_db(now_local())))
        count = db.execute("SELECT COUNT(*) FROM post_likes WHERE post_id = ?", (post_id,)).fetchone()[0]
        first = g.user["full_name"].split()[0]
        others = f" and {count - 1} other{'s' if count > 2 else ''}" if count > 1 else ""
        _tell_author(post, f"🔥 {first}{others} liked your post.", f"likes:{post_id}")
    db.commit()
    back = request.form.get("next") or ""
    return redirect(back if back.startswith(("/feed", "/posts/")) and safe_next(back) == back
                    else url_for("posts.view", post_id=post_id))


@bp.route("/posts/<int:post_id>/replies", methods=("POST",))
@login_required
def reply(post_id):
    post = get_post(post_id)
    if not _can_interact(post):
        abort(403)
    body = multi_line(request.form.get("body"))
    db = get_db()
    back = url_for("posts.view", post_id=post_id) + "#replies"
    if not body or len(body) > MAX_REPLY:
        flash(f"Replies are 1 to {MAX_REPLY} characters.", "error")
        return redirect(back)
    recent = db.execute("SELECT COUNT(*) FROM post_replies WHERE author_id = ? AND created_at >= ?",
                        (g.user["id"], to_db(now_local() - timedelta(hours=1)))).fetchone()[0]
    if recent >= REPLIES_PER_HOUR:
        flash(f"You can reply up to {REPLIES_PER_HOUR} times an hour. Try again in a bit.", "error")
        return redirect(back)
    db.execute("INSERT INTO post_replies (post_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
               (post_id, g.user["id"], body, to_db(now_local())))
    preview = body if len(body) <= 60 else body[:57] + "…"
    _tell_author(post, f"💬 {g.user['full_name'].split()[0]} replied to your post: “{preview}”", f"replies:{post_id}")
    db.commit()
    return redirect(back)


@bp.route("/replies/<int:reply_id>/delete", methods=("POST",))
@login_required
def delete_reply(reply_id):
    """Your own reply, a reply on your post, or (admins) any reply."""
    row = get_db().execute("""SELECT r.author_id, r.post_id, p.author_id AS post_author FROM post_replies r
                              JOIN posts p ON p.id = r.post_id WHERE r.id = ?""", (reply_id,)).fetchone()
    if row is None:
        abort(404)
    if g.user["id"] not in (row["author_id"], row["post_author"]) and not is_admin():
        abort(403)
    get_db().execute("DELETE FROM post_replies WHERE id = ?", (reply_id,))
    get_db().commit()
    flash("Reply deleted.", "info")
    return redirect(url_for("posts.view", post_id=row["post_id"]) + "#replies")


@bp.route("/posts/<int:post_id>/photos/<int:position>")
@login_required
def photo(post_id, position):
    get_post(post_id)  # only for people who can see the post
    row = get_db().execute("SELECT image FROM post_photos WHERE post_id = ? AND position = ?",
                           (post_id, position)).fetchone()
    if row is None:
        abort(404)
    response = Response(row["image"], mimetype="image/jpeg")
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"  # a photo never changes
    return response


def _read_photos():
    """The photos picked in the composer, cleaned (resized, hidden info like GPS removed): (jpegs, error)."""
    uploads = [upload for upload in request.files.getlist("photos") if upload and upload.filename]
    if len(uploads) > MAX_PHOTOS:
        return [], f"You can add up to {MAX_PHOTOS} photos to a post."
    jpegs = []
    for upload in uploads:
        try:
            jpegs.append(make_chat_photo(upload.read()))
        except ValueError as error:
            return [], str(error)
    return jpegs, None


def _read_plan(form, sport, body):
    """'Make it a plan': (game data for insert_event, error). The post's words become the game's note."""
    location = form.get("location", "")
    spots = form.get("spots", "")
    duration = dict(PLAN_DURATIONS).get(int(form["duration"]) if form.get("duration", "").isdigit() else None)
    try:
        starts = parse_form(form.get("starts_at", ""))
    except ValueError:
        return None, "Pick when the plan starts."
    now = now_local()
    if location not in LOCATIONS:
        return None, "Pick where you're meeting."
    if location not in SPORT_LOCATIONS[sport]:
        return None, f"{SPORTS[sport]} can't be played at {location}. Pick another place."
    if location == OFF_CAMPUS and not body:
        return None, "Off campus: say where in your post, so people can find you."
    if not spots.isdigit() or not 1 <= int(spots) <= MAX_PLAN_SPOTS:
        return None, f"How many more people do you need? (1 to {MAX_PLAN_SPOTS})"
    if duration is None:
        return None, "Pick how long it is."
    if starts <= now:
        return None, "Pick a time that hasn't passed yet."
    if starts > now + timedelta(days=PLAN_DAYS_AHEAD):
        return None, f"Plans can be up to {PLAN_DAYS_AHEAD} days ahead."
    if not exists_in_seattle(starts):
        return None, "That time doesn't exist (the clocks skip it). Pick another time."
    ends = add_real(starts, timedelta(minutes=int(form["duration"])))
    error = closed_message(location, starts, ends)
    if error:
        return None, error
    first_line = body.split("\n", 1)[0].strip()
    title = (first_line[:57] + "…") if len(first_line) > 60 else (first_line or f"{SPORTS[sport]} plan")
    return {"title": title, "sport": sport, "location": location, "starts_at": to_db(starts), "ends_at": to_db(ends),
            "skill_level": "All levels", "max_players": int(spots) + 1, "note": body[:500]}, None


@bp.route("/posts/new", methods=("POST",))
@login_required
def create():
    request.max_content_length = MAX_POST_UPLOAD_MB * 1024 * 1024  # several phone photos in one go
    form = request.form
    sport = form.get("sport", "")
    body = multi_line(form.get("body"))
    back = url_for("posts.feed", sport=form.get("channel") or None)
    error = None
    jpegs = []
    if sport not in SPORTS:
        error = "Tag your post with a sport."
    elif len(body) > MAX_BODY:
        error = f"Posts can be up to {MAX_BODY} characters."
    if error is None:
        jpegs, error = _read_photos()
    if error is None and not body and not jpegs:
        error = "Write something or add a photo."
    db = get_db()
    if error is None:
        recent = db.execute("SELECT COUNT(*) FROM posts WHERE author_id = ? AND created_at >= ?",
                            (g.user["id"], to_db(now_local() - timedelta(hours=1)))).fetchone()[0]
        if recent >= POSTS_PER_HOUR:
            error = f"You can post up to {POSTS_PER_HOUR} times an hour. Try again in a bit."
    plan = None
    if error is None and form.get("plan") == "1":
        plan, error = _read_plan(form, sport, body)
        if error is None:
            error = posting_too_fast(1)
    if error is not None:
        flash(error, "error")
        return redirect(back)
    event_id = insert_event(plan) if plan else None  # (commits)
    cur = db.execute("INSERT INTO posts (author_id, sport, body, event_id, created_at) VALUES (?, ?, ?, ?, ?)",
                     (g.user["id"], sport, body, event_id, to_db(now_local())))
    for position, jpeg in enumerate(jpegs, start=1):
        db.execute("INSERT INTO post_photos (post_id, position, image) VALUES (?, ?, ?)", (cur.lastrowid, position, jpeg))
    db.commit()
    if event_id:
        from .events import get_event  # (the game with its host's name, for the "Maya posted" notices)
        announce_new_game(get_event(event_id))
    flash("Posted! People can tap I'm in to join your plan." if plan else "Posted!", "success")
    return redirect(back)


@bp.route("/posts/<int:post_id>/delete", methods=("POST",))
@login_required
def delete(post_id):
    """The author (or an admin) takes a post down. A plan's game stays: it has players, and its page can cancel it."""
    post = get_db().execute("SELECT author_id, event_id FROM posts WHERE id = ?", (post_id,)).fetchone()
    if post is None:
        abort(404)
    if post["author_id"] != g.user["id"] and not is_admin():
        abort(403)
    db = get_db()
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    flash("Post deleted." + (" The plan's game is still on: cancel it from its page if it's off."
                             if post["event_id"] and post["author_id"] == g.user["id"] else ""), "info")
    return redirect(request.form.get("next") if (request.form.get("next") or "").startswith("/feed")
                    else url_for("posts.feed"))
