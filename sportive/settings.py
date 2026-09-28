"""Settings: how the app works for you (notifications, look, emails, password, your account).

Kept apart from Edit profile, which is about you (photo, name, bio, socials, sports).
"""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db

bp = Blueprint("settings", __name__)

# The app's look. Light is the default, like UW's own pages.
THEMES = {"light": "Light", "dark": "Dark", "system": "Match my phone"}


def current_theme():
    """For <html data-theme>: the logged-in person's choice, or the one picked while signing up."""
    from flask import session
    if g.get("user") is not None and g.user["theme"] in THEMES:
        return g.user["theme"]
    return session.get("theme") if session.get("theme") in THEMES else "light"


@bp.route("/settings")
@login_required
def home():
    return render_template("settings/home.html", themes=THEMES)


@bp.route("/settings/look", methods=("POST",))
@login_required
def look():
    theme = request.form.get("theme", "")
    if theme in THEMES:
        db = get_db()
        db.execute("UPDATE users SET theme = ? WHERE id = ?", (theme, g.user["id"]))
        db.commit()
    return redirect(url_for("settings.home"))


@bp.route("/settings/reminders", methods=("POST",))
@login_required
def reminders():
    """Emails an hour before your games (on unless you switch them off)."""
    on = 1 if request.form.get("email_reminders") else 0
    db = get_db()
    db.execute("UPDATE users SET email_reminders = ? WHERE id = ?", (on, g.user["id"]))
    db.commit()
    flash("Game reminder emails are on." if on else "Game reminder emails are off.", "success")
    return redirect(url_for("settings.home"))


@bp.route("/settings/password")
@login_required
def password():
    return render_template("settings/password.html")
