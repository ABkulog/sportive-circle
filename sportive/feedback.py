"""Suggestions: any logged-in Husky can send an idea or a problem; only admins can read them.

People can send anonymously: then admins see the suggestion but not who sent it. (The account is still
stored, only to enforce the hourly limit and to count people for trends, and is never shown.)

So admins don't burn out, they aren't notified about every suggestion. Each one is scanned for keywords,
and a keyword becomes a *trending topic* (with a notification) once 3+ different people mention it within
30 days. Everything is still readable on the Suggestions page.
"""
import re
from datetime import timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .moderation import admin_required, is_admin
from .notifications import mark_seen_value, seen_value
from .textutil import multi_line
from .timeutil import now_local, to_db

bp = Blueprint("feedback", __name__)

KINDS = {"idea": "Idea", "bug": "Something's broken", "other": "Other"}
MIN_LENGTH, MAX_LENGTH = 5, 2000
MAX_PER_HOUR = 5

TREND_PEOPLE = 3                 # different people who must mention a keyword before admins hear about it
TREND_WINDOW = timedelta(days=30)
MAX_TRENDS = 10

# Words that say nothing about the topic (plus words every suggestion about this app would use).
STOPWORDS = set("""
a about above after again all also am an and any are aren't as at be because been before being below between both
but by can can't cannot could couldn't did didn't do does doesn't doing don't dont down during each few for from
further get gets getting got had hasn't has have haven't having he her here hers him his how i i'd i'm i've if in
into is isn't it it's its itself just let's lets like likes me more most much must my no nor not now of off on once
only or other our ours out over own really same she should shouldn't so some such than that that's the their
theirs them then there there's these they they're this those through to too under until up upon us very was wasn't
we we're were weren't what what's when where which while who whom why will with won't would wouldn't you you'd
you're your yours yourself
app apps sportive circle please add adding make making want wanted wish would could maybe think feel need needs
able use using used thing things stuff lot lots way ways one ones someone something everything anything people
person time times good great nice cool better best bad awesome love idea ideas feature features option options
page pages see seeing new more also even still well yeah hey hi thanks thank pls plz lol kinda sorta
""".split())

# Different words for the same topic count together.
ALIASES = {
    "noti": "notification", "notis": "notification", "notif": "notification", "notifs": "notification",
    "notifications": "notification", "signin": "login", "log-in": "login", "logins": "login",
    "pw": "password", "passwords": "password", "e-mail": "email", "emails": "email", "dms": "message",
    "dm": "message", "messages": "message", "texting": "message", "clubs": "club", "games": "game",
    "maps": "map", "bugs": "bug", "crash": "bug", "crashes": "bug", "broken": "bug", "glitch": "bug",
}


def keywords(text):
    """The topic words in one suggestion (each counted once): lowercase, no stopwords, simple plurals merged."""
    found = set()
    for word in re.findall(r"[a-z][a-z'+-]*[a-z]", text.lower()):
        word = ALIASES.get(word, word)
        if word in STOPWORDS or len(word) < 3:
            continue
        if word.endswith("s") and not word.endswith("ss") and len(word) > 4:  # "courts" -> "court"
            word = ALIASES.get(word[:-1], word[:-1])
        if word not in STOPWORDS:
            found.add(word)
    return found


def trending(now=None):
    """[(keyword, people, suggestions)] for keywords 3+ different people used in the last 30 days, biggest first."""
    since = to_db((now or now_local()) - TREND_WINDOW)
    people, mentions = {}, {}
    for row in get_db().execute("SELECT id, user_id, body FROM suggestions WHERE created_at >= ?", (since,)):
        who = row["user_id"] if row["user_id"] is not None else f"gone-{row['id']}"
        for word in keywords(row["body"]):
            people.setdefault(word, set()).add(who)
            mentions[word] = mentions.get(word, 0) + 1
    trends = [(word, len(who), mentions[word]) for word, who in people.items() if len(who) >= TREND_PEOPLE]
    return sorted(trends, key=lambda t: (-t[1], -t[2], t[0]))[:MAX_TRENDS]


def unseen_trends():
    """Trending keywords this admin hasn't looked at yet (each topic notifies once, not every time it grows)."""
    if not is_admin():
        return []
    seen = set((seen_value("suggestion_trends") or "").split(","))
    return [trend for trend in trending() if trend[0] not in seen]


@bp.route("/suggestions", methods=("GET", "POST"))
@login_required
def suggest():
    form = request.form
    if request.method == "POST":
        kind = form.get("kind", "")
        body = multi_line(form.get("body"))
        db = get_db()
        recent = db.execute("SELECT COUNT(*) FROM suggestions WHERE user_id = ? AND created_at >= ?",
                            (g.user["id"], to_db(now_local() - timedelta(hours=1)))).fetchone()[0]
        if kind not in KINDS:
            error = "Please choose what your suggestion is about."
        elif not MIN_LENGTH <= len(body) <= MAX_LENGTH:
            error = f"Please write {MIN_LENGTH} to {MAX_LENGTH} characters."
        elif recent >= MAX_PER_HOUR:
            error = "Thanks for all the ideas! You can send more in an hour."
        else:
            error = None
        if error:
            flash(error, "error")
        else:
            db.execute("INSERT INTO suggestions (user_id, anonymous, kind, body, created_at) VALUES (?, ?, ?, ?, ?)",
                       (g.user["id"], 1 if form.get("anonymous") else 0, kind, body, to_db(now_local())))
            db.commit()
            flash("Thanks! We read every one.", "success")
            return redirect(url_for("feedback.suggest"))
    return render_template("feedback/suggest.html", form=form, kinds=KINDS, max_length=MAX_LENGTH)


@bp.route("/admin/suggestions")
@admin_required
def admin_suggestions():
    kind = request.args.get("kind", "")
    topic = request.args.get("topic", "").strip().lower()[:40]
    where, params = "", ()
    if kind in KINDS:
        where, params = "WHERE s.kind = ?", (kind,)
    rows = get_db().execute(
        f"""SELECT s.*, u.full_name, u.email FROM suggestions s LEFT JOIN users u ON u.id = s.user_id
            {where} ORDER BY s.id DESC LIMIT 500""", params).fetchall()
    if topic:
        rows = [row for row in rows if topic in keywords(row["body"])]
    trends = trending()
    fresh = {word for word, *_ in unseen_trends()}
    # Opening the page counts as seeing every current trend and every suggestion so far.
    seen = set((seen_value("suggestion_trends") or "").split(",")) | {word for word, *_ in trends}
    mark_seen_value("suggestion_trends", ",".join(sorted(filter(None, seen))))
    last_seen = int(seen_value("suggestions") or 0)
    if not kind and not topic:
        mark_seen_value("suggestions", max([row["id"] for row in rows] + [last_seen]))
    return render_template("feedback/admin.html", suggestions=rows[:300], kinds=KINDS, kind=kind, topic=topic,
                           trends=trends, fresh=fresh, last_seen=last_seen, trend_people=TREND_PEOPLE)
