"""Public profiles, editing your own, and profile pictures."""
import secrets

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template, request, session,
                   url_for)
from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash

from .auth import login_required, safe_next
from .constants import SPORTS
from .db import get_db, set_user_sports, user_sports
from .events import query_events
from .photos import make_avatar
from .timeutil import now_local, to_db

bp = Blueprint("profile", __name__)

# Pages you can still open before adding a profile picture.
ALLOWED_WITHOUT_PHOTO = {"profile.photo_upload", "profile.photo_skip", "profile.photo", "profile.delete_account",
                         "auth.logout", "how_it_works", "static", "favicon",
                         "touch_icon_apple_touch_icon_png", "touch_icon_apple_touch_icon_precomposed_png"}


@bp.before_app_request
def require_profile_picture():
    """Everyone needs a profile picture, so people know who they're meeting at the court."""
    if g.get("user") is not None and not g.user["avatar_updated"] and not session.get("photo_skipped") \
            and request.endpoint not in ALLOWED_WITHOUT_PHOTO:
        if request.method == "GET" and request.path != "/":
            session["after_photo"] = request.full_path  # e.g. a shared event link; go there afterwards
        return redirect(url_for("profile.photo_upload"))


@bp.route("/profile/photo", methods=("GET", "POST"))
@login_required
def photo_upload():
    first_time = not g.user["avatar_updated"]
    if request.method == "POST":
        upload = request.files.get("photo")
        if upload is None or not upload.filename:
            flash("Choose a photo first.", "error")
        else:
            try:
                image = make_avatar(upload.read())
            except ValueError as error:
                flash(str(error), "error")
            else:
                db = get_db()
                db.execute("INSERT OR REPLACE INTO avatars (user_id, image) VALUES (?, ?)", (g.user["id"], image))
                # A new value every time, so browsers show the new picture instead of a cached old one.
                version = f"{now_local().strftime('%Y%m%d%H%M')}-{secrets.token_hex(3)}"
                db.execute("UPDATE users SET avatar_updated = ? WHERE id = ?", (version, g.user["id"]))
                db.commit()
                if first_time:
                    destination = session.pop("after_photo", None)
                    if destination:
                        flash("Looking good! You're all set.", "success")
                        return redirect(safe_next(destination))
                    flash("Looking good! You're all set. Here's how Sportive Circle works.", "success")
                    return redirect(url_for("how_it_works"))
                flash("Profile picture updated.", "success")
                return redirect(url_for("profile.view", user_id=g.user["id"]))
    return render_template("profile/photo.html", first_time=first_time)


@bp.route("/profile/photo/skip", methods=("POST",))
@login_required
def photo_skip():
    """'Add later': let them in for now. They're asked again next time they log in,
    and a banner reminds them until they add one."""
    session["photo_skipped"] = True
    flash("No problem! You can add a profile picture any time from your profile.", "info")
    destination = session.pop("after_photo", None)
    return redirect(safe_next(destination) if destination else url_for("how_it_works"))


@bp.route("/u/<int:user_id>/photo")
@login_required
def photo(user_id):
    row = get_db().execute("SELECT image FROM avatars WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        abort(404)
    response = Response(row["image"], mimetype="image/jpeg")
    # The URL changes whenever the picture does (?v=...), so it can be cached for a long time.
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return response


@bp.route("/u/<int:user_id>")
@login_required
def view(user_id):
    user = get_db().execute(
        "SELECT id, full_name, email, grad_year, bio, avatar_updated, created_at FROM users"
        " WHERE id = ? AND verified = 1",
        (user_id,),
    ).fetchone()
    if user is None:
        abort(404)
    hosting = query_events(["e.host_id = :uid", "e.cancelled = 0", "e.ends_at >= :now"],
                           {"uid": user_id, "now": to_db(now_local())}, limit=10)
    # Emails are private: only visible to yourself and people you share an event with.
    show_email = user_id == g.user["id"] or get_db().execute(
        """SELECT 1 FROM rsvps mine JOIN rsvps theirs ON mine.event_id = theirs.event_id
           WHERE mine.user_id = ? AND theirs.user_id = ?""",
        (g.user["id"], user_id),
    ).fetchone() is not None
    return render_template("profile/view.html", user=user, sports=user_sports(user_id), hosting=hosting,
                           show_email=show_email)


@bp.route("/profile/edit", methods=("GET", "POST"))
@login_required
def edit():
    me = g.user
    if request.method == "POST":
        form = request.form
        full_name = form.get("full_name", "").strip()
        grad_year = form.get("grad_year", "").strip()
        bio = form.get("bio", "").strip()
        sports = [s for s in form.getlist("sports") if s in SPORTS]
        email_reminders = 1 if form.get("email_reminders") else 0

        error = None
        if not full_name:
            error = "Full name cannot be empty."
        elif grad_year and (not grad_year.isdigit() or not 1950 <= int(grad_year) <= now_local().year + 8):
            error = "Please enter a valid graduation year."
        elif len(bio) > 300:
            error = "Bio is too long (300 characters max)."

        if error is None:
            db = get_db()
            db.execute("UPDATE users SET full_name = ?, grad_year = ?, bio = ?, email_reminders = ? WHERE id = ?",
                       (full_name, int(grad_year) if grad_year else None, bio, email_reminders, me["id"]))
            set_user_sports(me["id"], sports)
            db.commit()
            flash("Profile saved.", "success")
            return redirect(url_for("profile.view", user_id=me["id"]))
        flash(error, "error")
    else:
        form = MultiDict([("full_name", me["full_name"]), ("grad_year", me["grad_year"] or ""), ("bio", me["bio"])]
                         + [("sports", s) for s in user_sports(me["id"])]
                         + ([("email_reminders", "1")] if me["email_reminders"] else []))
    return render_template("profile/edit.html", form=form)


@bp.route("/profile/delete", methods=("POST",))
@login_required
def delete_account():
    """Permanently delete your account, your RSVPs and the events you host."""
    if not check_password_hash(g.user["password_hash"], request.form.get("password", "")):
        flash("That password isn't right, so your account was not deleted.", "error")
        return redirect(url_for("profile.edit"))
    db = get_db()
    # ON DELETE CASCADE (schema.sql) also removes your sports, RSVPs and hosted events.
    db.execute("DELETE FROM users WHERE id = ?", (g.user["id"],))
    db.commit()
    session.clear()
    flash("Your account and everything in it was deleted. Hope to see you back!", "info")
    return redirect(url_for("index"))
