"""Settings: how the app works for you (notifications, look, emails, password, your account).

Kept apart from Edit profile, which is about you (photo, name, bio, socials, sports).
"""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .timeutil import now_local, to_db

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


@bp.route("/settings/weekly", methods=("POST",))
@login_required
def weekly():
    """The Monday "Games this week" email (on unless you switch it off)."""
    on = 1 if request.form.get("weekly_digest") else 0
    db = get_db()
    db.execute("UPDATE users SET weekly_digest = ? WHERE id = ?", (on, g.user["id"]))
    db.commit()
    flash("The Monday email is on." if on else "The Monday email is off.", "success")
    return redirect(url_for("settings.home"))


@bp.route("/settings/texts", methods=("GET", "POST"))
@login_required
def texts():
    """Texts (optional): add a number (with permission), confirm it with a texted code, turn texts on or off,
    or remove the number."""
    from .phones import phone_from_form
    from .sms import check_phone_code, remove_phone, sms_available, start_phone_check
    if not sms_available():
        flash("Texts aren't available yet. Everything comes by email for now.", "info")
        return redirect(url_for("settings.home"))
    me = g.user["id"]
    if request.method == "POST":
        action = request.form.get("action")
        if action == "send":
            phone = phone_from_form(request.form.get("phone_country"), request.form.get("phone"))
            if phone is None:
                flash("That doesn't look like a phone number. Try (206) 555-0142.", "error")
            elif not request.form.get("consent"):
                flash("Tick the box to say it's OK to text you.", "error")
            else:
                problem = start_phone_check(me, phone)
                flash(problem or "We texted you a code. Type it below.", "error" if problem else "success")
        elif action == "confirm":
            problem = check_phone_code(me, request.form.get("code", "").strip())
            flash(problem or "Your number is confirmed. We'll text you reminders and updates.",
                  "error" if problem else "success")
        elif action == "toggle":
            on = 1 if request.form.get("sms_updates") else 0
            db = get_db()
            changed = db.execute("UPDATE users SET sms_updates = ?, sms_consent_at = CASE WHEN ? THEN ? ELSE"
                                 " sms_consent_at END WHERE id = ? AND phone_verified = 1",
                                 (on, on, to_db(now_local()), me)).rowcount
            db.commit()
            if not changed:
                flash("Confirm your number first.", "error")
        elif action == "remove":
            remove_phone(me)
            flash("Your number is removed. No more texts.", "success")
        return redirect(url_for("settings.texts"))
    user = get_db().execute("SELECT phone, phone_verified, sms_updates, sms_code FROM users WHERE id = ?",
                            (me,)).fetchone()
    return render_template("settings/texts.html", user=user)


@bp.route("/settings/texts/not-now", methods=("POST",))
@login_required
def texts_not_now():
    """Close the "New: texts" card on Home for good (Settings -> Texts still works anytime)."""
    db = get_db()
    db.execute("UPDATE users SET texts_card_done = 1 WHERE id = ?", (g.user["id"],))
    db.commit()
    flash("OK. You can add your number anytime in Settings → Texts.", "info")
    return redirect(url_for("events.feed"))


@bp.route("/settings/password")
@login_required
def password():
    return render_template("settings/password.html")
