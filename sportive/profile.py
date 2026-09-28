"""Public profiles, editing your own, and profile pictures."""
import re
import secrets

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template, request, session,
                   url_for)
from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash

from .auth import MAX_NAME_LENGTH, hash_password, login_required, password_problem, safe_next
from .constants import SPORTS
from .db import get_db, set_user_sports, user_sports
from .events import celebrate_progress, query_events, tell_players_it_was_cancelled
from .photos import make_avatar
from .badges import (GIVEN_BADGES, ROLE_BADGES, SHOWCASE_SLOTS, TESTER, catalog, earned_badges, is_retired,
                     give_badge, rarity, set_showcase, showcase, sync_badges)
from .clubs import SOCIALS
from .moderation import admin_required, is_admin
from .notifications import mark_seen, notify
from .textutil import one_line
from .social import can_message, friendship_status, i_blocked, is_blocked_between
from .timeutil import now_local, to_db

bp = Blueprint("profile", __name__)

# Optional profile details. Gender is shown only if someone picks one.
GENDERS = {"": "Prefer not to say", "woman": "Woman", "man": "Man", "nonbinary": "Nonbinary", "other": "Another identity"}
MAX_PRONOUNS = 20
PERSON_SOCIALS = ("instagram", "snapchat", "tiktok", "x_handle")  # same checks as club socials (clubs.SOCIALS)


def person_socials(user):
    """[(label, url, "@handle")] for the socials someone added, so people can DM them where they already are."""
    return [(SOCIALS[key][0], SOCIALS[key][3].format(user[key]), f"@{user[key]}")
            for key in PERSON_SOCIALS if user[key]]

# Pages you can still open before adding a profile picture.
ALLOWED_WITHOUT_PHOTO = {"profile.photo_upload", "profile.photo_skip", "profile.photo", "profile.delete_account",
                         "auth.logout", "how_it_works", "faq", "robots", "sitemap", "parties.open_invite_link", "privacy", "terms", "static", "favicon", "touch_icon",
                         "touch_icon_precomposed"}


@bp.before_app_request
def require_profile_picture():
    """New accounts see the photo step once, so people know who they're meeting at the court.
    "Add later" is remembered: nobody gets asked again on every page or every login."""
    if g.get("user") is not None and not g.user["avatar_updated"] and not g.user["photo_skipped"] \
            and request.endpoint not in ALLOWED_WITHOUT_PHOTO:
        if request.method == "GET" and request.path != "/":
            session["after_photo"] = request.full_path  # e.g. a shared event link; go there afterwards
        return redirect(url_for("profile.photo_upload"))


@bp.route("/profile/photo", methods=("GET", "POST"))
@login_required
def photo_upload():
    first_time = not g.user["avatar_updated"] and not g.user["photo_skipped"]  # the sign-up step
    if request.method == "POST":
        upload = request.files.get("photo")
        if (upload is None or not upload.filename) and not first_time:
            # Saved without picking a new photo: keep the current one and go back to the profile.
            return redirect(url_for("profile.view", user_id=g.user["id"]))
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
                db.execute("DELETE FROM notices WHERE user_id = ? AND kind = 'account' AND url = ?",
                           (g.user["id"], url_for("profile.photo_upload")))  # the photo reminder is done
                db.commit()
                if first_time:
                    flash("Looking good. You're all set!", "celebrate")
                    destination = session.pop("after_photo", None)
                    return redirect(safe_next(destination) if destination else url_for("events.feed"))
                flash("Photo updated.", "success")
                return redirect(url_for("profile.view", user_id=g.user["id"]))
    return render_template("profile/photo.html", first_time=first_time)


@bp.route("/profile/photo/remove", methods=("POST",))
@login_required
def photo_remove():
    """Remove your photo. You won't be sent back to the "add a photo" step."""
    db = get_db()
    db.execute("DELETE FROM avatars WHERE user_id = ?", (g.user["id"],))
    db.execute("UPDATE users SET avatar_updated = NULL, photo_skipped = 1 WHERE id = ?", (g.user["id"],))
    db.commit()
    flash("Photo removed.", "info")
    return redirect(url_for("profile.view", user_id=g.user["id"]))


@bp.route("/profile/photo/skip", methods=("POST",))
@login_required
def photo_skip():
    """'Add later': the page already said "No problem" in a pop-up. Remembered, so they aren't asked again."""
    db = get_db()
    db.execute("UPDATE users SET photo_skipped = 1 WHERE id = ?", (g.user["id"],))
    # One reminder in the bell, instead of a banner on every page.
    notify(g.user["id"], "account", "Add a profile photo so people know who they're playing with.",
           url_for("profile.photo_upload"), key="tip:photo")
    db.commit()
    destination = session.pop("after_photo", None)
    return redirect(safe_next(destination) if destination else url_for("events.feed"))


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
        "SELECT id, full_name, email, grad_year, bio, pronouns, gender, instagram, snapchat, tiktok, x_handle,"
        " avatar_updated, suspended, created_at FROM users"
        " WHERE id = ? AND verified = 1",
        (user_id,),
    ).fetchone()
    if user is None or (user["suspended"] and user_id != g.user["id"] and not is_admin()):
        abort(404)
    hosting = query_events(["e.host_id = :uid", "e.cancelled = 0", "e.ends_at >= :now"],
                           {"uid": user_id, "now": to_db(now_local())}, limit=10)
    # Emails are private: only visible to yourself and people you share an event with.
    show_email = user_id == g.user["id"] or get_db().execute(
        """SELECT 1 FROM rsvps mine JOIN rsvps theirs ON mine.event_id = theirs.event_id
           WHERE mine.user_id = ? AND theirs.user_id = ?""",
        (g.user["id"], user_id),
    ).fetchone() is not None
    if user_id == g.user["id"]:
        celebrate_progress(user_id)
        mark_seen("badges")
    else:
        sync_badges(user_id)  # keep their showcase up to date
    relation = None
    if user_id != g.user["id"]:
        me = g.user["id"]
        relation = {"friend": friendship_status(me, user_id), "can_message": can_message(me, user_id),
                    "i_blocked": i_blocked(me, user_id), "blocked_me": is_blocked_between(me, user_id)
                    and not i_blocked(me, user_id)}
    return render_template("profile/view.html", user=user, sports=user_sports(user_id), hosting=hosting,
                           show_email=show_email, socials=person_socials(user), genders=GENDERS,
                           is_tester=TESTER.key in earned_badges(user_id),
                           showcase=showcase(user_id), earned=earned_badges(user_id), rarity=rarity(),
                           is_retired=is_retired, relation=relation)


@bp.route("/admin/users/<int:user_id>/tester/<action>", methods=("POST",))
@admin_required
def tester_badge(user_id, action):
    """Admins give the 🧪 Tester badge to the people who tested the app (or take it back)."""
    if action not in ("give", "take"):
        abort(404)
    user = get_db().execute("SELECT full_name FROM users WHERE id = ? AND verified = 1", (user_id,)).fetchone()
    if user is None:
        abort(404)
    give_badge(user_id, TESTER.key, give=action == "give")
    first = user["full_name"].split()[0]
    flash(f"{first} has the Tester badge now." if action == "give" else f"Took the Tester badge from {first}.",
          "success")
    return redirect(url_for("profile.view", user_id=user_id))


@bp.route("/profile/badges", methods=("GET", "POST"))
@login_required
def badge_locker():
    """Every badge you've earned; pick up to 3 to show on your profile."""
    me = g.user["id"]
    if request.method == "POST":
        error = set_showcase(me, request.form.getlist("show"))
        if error:
            flash(error, "error")
        else:
            flash("Saved.", "success")
            return redirect(url_for("profile.view", user_id=me))
    sync_badges(me)
    mark_seen("badges")
    return render_template("profile/badges.html", badges=catalog(), earned=earned_badges(me),
                           role_badges=ROLE_BADGES | GIVEN_BADGES,
                           shown=[badge.key for badge in showcase(me)], rarity=rarity(),
                           is_retired=is_retired, slots=SHOWCASE_SLOTS)


@bp.route("/profile/edit", methods=("GET", "POST"))
@login_required
def edit():
    me = g.user
    if request.method == "POST":
        form = request.form
        full_name = one_line(form.get("full_name"))
        grad_year = form.get("grad_year", "").strip()
        bio = form.get("bio", "").strip()
        sports = [s for s in form.getlist("sports") if s in SPORTS]
        pronouns = one_line(form.get("pronouns"))
        gender = form.get("gender", "")
        socials = {key: one_line(form.get(key)).lstrip("@") for key in PERSON_SOCIALS}
        bad_social = next((key for key, value in socials.items()
                           if value and not re.fullmatch(SOCIALS[key][2], value)), None)

        error = None
        if not full_name:
            error = "Full name cannot be empty."
        elif len(full_name) > MAX_NAME_LENGTH:
            error = f"Please keep your name under {MAX_NAME_LENGTH} characters."
        elif grad_year and (not grad_year.isdigit() or not 1950 <= int(grad_year) <= now_local().year + 8):
            error = "Please enter a valid graduation year."
        elif len(bio) > 300:
            error = "Bio is too long (300 characters max)."
        elif len(pronouns) > MAX_PRONOUNS:
            error = f"Keep pronouns under {MAX_PRONOUNS} characters."
        elif gender not in GENDERS:
            error = "Please pick an option for gender."
        elif bad_social:
            error = f"That {SOCIALS[bad_social][0]} username doesn't look right. Just the username, like @dubs."

        if error is None:
            db = get_db()
            db.execute("""UPDATE users SET full_name = :full_name, grad_year = :grad_year, bio = :bio,
                              pronouns = :pronouns, gender = :gender,
                              instagram = :instagram, snapchat = :snapchat, tiktok = :tiktok, x_handle = :x_handle
                          WHERE id = :id""",
                       {"full_name": full_name, "grad_year": int(grad_year) if grad_year else None, "bio": bio,
                        "pronouns": pronouns, "gender": gender, **socials,
                        "id": me["id"]})
            set_user_sports(me["id"], sports)
            db.commit()
            flash("Profile saved.", "success")
            return redirect(url_for("profile.view", user_id=me["id"]))
        flash(error, "error")
    else:
        form = MultiDict([("full_name", me["full_name"]), ("grad_year", me["grad_year"] or ""), ("bio", me["bio"]),
                          ("pronouns", me["pronouns"]), ("gender", me["gender"])]
                         + [(key, me[key]) for key in PERSON_SOCIALS]
                         + [("sports", s) for s in user_sports(me["id"])])
    return render_template("profile/edit.html", form=form, max_grad_year=now_local().year + 8, genders=GENDERS,
                           socials={key: SOCIALS[key][0] for key in PERSON_SOCIALS})


@bp.route("/profile/password", methods=("POST",))
@login_required
def change_password():
    form = request.form
    if not check_password_hash(g.user["password_hash"], form.get("current_password", "")):
        error = "Your current password isn't right."
    else:
        error = password_problem(form.get("password", ""), form.get("password2", ""))
    if error:
        flash(f"{error} Your password was not changed.", "error")
    else:
        db = get_db()
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(form["password"]), g.user["id"]))
        db.commit()
        flash("Password changed.", "success")
    return redirect(url_for("settings.password") if error else url_for("settings.home"))


CONFIRM_WORD = "DELETE"


def what_you_would_lose(user_id):
    db = get_db()
    now = to_db(now_local())
    one = lambda sql, *args: db.execute(sql, args).fetchone()[0]
    return {
        "badges": one("SELECT COUNT(*) FROM user_badges WHERE user_id = ?", user_id),
        "og_badges": sum(1 for badge in catalog() if badge.until and badge.key in earned_badges(user_id)),
        "games": one("SELECT COUNT(*) FROM rsvps r JOIN events e ON e.id = r.event_id"
                     " WHERE r.user_id = ? AND e.cancelled = 0 AND e.ends_at < ?", user_id, now),
        "hosting": one("SELECT COUNT(*) FROM events WHERE host_id = ? AND cancelled = 0 AND ends_at >= ?", user_id, now),
        "friends": one("SELECT COUNT(*) FROM friendships WHERE (requester_id = ? OR addressee_id = ?)"
                       " AND status = 'accepted'", user_id, user_id),
        "messages": one("SELECT COUNT(*) FROM direct_messages WHERE sender_id = ? OR recipient_id = ?", user_id, user_id),
    }


def clubs_only_i_lead(user_id):
    """Clubs where this person is the only officer (they'd be left without a leader)."""
    return get_db().execute(
        """SELECT c.id, c.name FROM clubs c JOIN club_members m ON m.club_id = c.id
           WHERE m.user_id = ? AND m.role = 'officer'
             AND (SELECT COUNT(*) FROM club_members o WHERE o.club_id = c.id AND o.role = 'officer') = 1""",
        (user_id,)).fetchall()


@bp.route("/profile/delete", methods=("GET", "POST"))
@login_required
def delete_account():
    """Step 1 (GET): an "Are you sure?" page showing what you'd lose.
    Step 2 (POST): delete, only with your password AND the word DELETE typed in."""
    sole_officer = clubs_only_i_lead(g.user["id"])
    if request.method == "GET":
        return render_template("profile/delete.html", lose=what_you_would_lose(g.user["id"]), word=CONFIRM_WORD,
                               sole_officer=sole_officer)
    if sole_officer:
        flash(f"You're the only officer of {sole_officer[0]['name']}. Make someone else an officer first.", "error")
        return redirect(url_for("profile.delete_account"))
    if request.form.get("confirm", "").strip().upper() != CONFIRM_WORD:
        flash(f"Type {CONFIRM_WORD} in the box to confirm. Your account was not deleted.", "error")
        return redirect(url_for("profile.delete_account"))
    if not check_password_hash(g.user["password_hash"], request.form.get("password", "")):
        flash("That password isn't right, so your account was not deleted.", "error")
        return redirect(url_for("profile.delete_account"))
    # Games they host disappear with the account, so warn everyone who joined (like canceling would).
    for event in query_events(["e.host_id = :me", "e.cancelled = 0", "e.ends_at >= :now"],
                              {"now": to_db(now_local())}):
        tell_players_it_was_cancelled(event)
    db = get_db()
    # ON DELETE CASCADE (schema.sql) also removes your sports, RSVPs and hosted events.
    db.execute("DELETE FROM users WHERE id = ?", (g.user["id"],))
    db.commit()
    session.clear()
    flash("Your account was deleted.", "info")
    return redirect(url_for("index"))
