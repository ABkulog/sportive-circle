"""Suggestions: any logged-in Husky can send an idea or a problem; only admins can read them.

People can send anonymously: then admins see the suggestion but not who sent it. (The account is still
stored, only to enforce the hourly limit, and is never shown.)
"""
from datetime import timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .moderation import admin_required, is_admin
from .notifications import mark_seen_value, seen_value
from .timeutil import now_local, to_db

bp = Blueprint("feedback", __name__)

KINDS = {"idea": "💡 An idea", "bug": "🐞 Something's broken", "other": "💬 Something else"}
MIN_LENGTH, MAX_LENGTH = 5, 2000
MAX_PER_HOUR = 5


@bp.route("/suggestions", methods=("GET", "POST"))
@login_required
def suggest():
    form = request.form
    if request.method == "POST":
        kind = form.get("kind", "")
        body = form.get("body", "").strip()
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
            flash("Thank you! 💜 The Sportive Circle team reads every suggestion.", "success")
            return redirect(url_for("feedback.suggest"))
    return render_template("feedback/suggest.html", form=form, kinds=KINDS, max_length=MAX_LENGTH)


@bp.route("/admin/suggestions")
@admin_required
def admin_suggestions():
    kind = request.args.get("kind", "")
    where, params = "", ()
    if kind in KINDS:
        where, params = "WHERE s.kind = ?", (kind,)
    rows = get_db().execute(
        f"""SELECT s.*, u.full_name, u.email FROM suggestions s LEFT JOIN users u ON u.id = s.user_id
            {where} ORDER BY s.id DESC LIMIT 300""", params).fetchall()
    last_seen = int(seen_value("suggestions") or 0)
    mark_seen_value("suggestions", max([row["id"] for row in rows] + [last_seen]))
    return render_template("feedback/admin.html", suggestions=rows, kinds=KINDS, kind=kind, last_seen=last_seen)


def new_suggestion_count():
    """For the admin menu: suggestions sent since this admin last opened the page."""
    if not is_admin():
        return 0
    return get_db().execute("SELECT COUNT(*) FROM suggestions WHERE id > ?",
                            (int(seen_value("suggestions") or 0),)).fetchone()[0]
