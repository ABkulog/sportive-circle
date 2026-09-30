"""Public profiles, editing your own, and profile pictures."""
import re
import secrets

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template, request, session,
                   url_for)
from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash

from .auth import MAX_NAME_LENGTH, check_current_password, end_other_sessions, hash_password, login_required, password_problem, safe_next
from .constants import SPORTS
from .db import get_db, set_user_sports, user_sports
from .events import INSIDE_VISIBLE, SHOWN_UNLESS_FULL, celebrate_progress, query_events, tell_players_it_was_cancelled
from .photos import THUMB_SIZES, make_avatar, thumbnail
from .badges import (GIVEN_BADGES, ROLE_BADGES, SHOWCASE_SLOTS, TESTER, catalog, earned_badges, is_retired,
                     give_badge, rarity, set_showcase, showcase, sync_badges)
from .clubs import SOCIALS
from .moderation import admin_required, is_admin
from .notifications import mark_seen, notify
from .textutil import has_a_letter, multi_line, one_line, person_name, social_handle
from .social import can_message, friendship_status, i_blocked, is_blocked_between
from .timeutil import now_local, to_db

bp = Blueprint("profile", __name__)

# Optional profile details. Gender is shown only if someone picks one.
GENDERS = {"": "Prefer not to say", "woman": "Woman", "man": "Man", "nonbinary": "Nonbinary", "other": "Other"}
MAX_PRONOUNS = 20
# (label, what a valid value looks like, link, how it's shown). Same checks as club socials (clubs.SOCIALS),
# plus LinkedIn for people.
PERSON_SOCIAL_RULES = {
    **{key: (SOCIALS[key][0], SOCIALS[key][2], SOCIALS[key][3], "@{}") for key in ("instagram", "snapchat", "tiktok",
                                                                                 "x_handle")},
    "linkedin": ("LinkedIn", r"[A-Za-z0-9\-_%]{3,100}", "https://www.linkedin.com/in/{}", "in/{}"),
}
PERSON_SOCIALS = tuple(PERSON_SOCIAL_RULES)


def person_socials(user):
    """[(label, url, "@handle")] for the socials someone added, so people can DM them where they already are."""
    return [(PERSON_SOCIAL_RULES[key][0], PERSON_SOCIAL_RULES[key][2].format(user[key]),
             PERSON_SOCIAL_RULES[key][3].format(user[key])) for key in PERSON_SOCIALS if user[key]]


def clean_social(key, value):
    """What people type or paste -> just the username. A pasted profile link works too."""
    value = one_line(value).strip()
    if key == "linkedin":
        value = re.sub(r"^(https?://)?([a-z]{2,3}\.)?linkedin\.com/in/", "", value, flags=re.I).strip("/")
        return value.split("?")[0].split("/")[0]
    return social_handle(key, value)

# Pages you can still open before adding a profile picture.
ALLOWED_WITHOUT_PHOTO = {"auth.signup_number", "profile.photo_upload", "profile.photo_skip", "profile.photo", "profile.delete_account",
                         "auth.logout", "how_it_works", "faq", "robots", "sitemap", "parties.open_invite_link", "privacy", "terms", "flyer", "flyer_qr", "static", "favicon", "touch_icon",
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
                    return redirect(after_sign_up())
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
    if g.user["avatar_updated"] or g.user["photo_skipped"]:  # not the sign-up step any more (an old tab)
        return redirect(url_for("profile.view", user_id=g.user["id"]))
    db = get_db()
    db.execute("UPDATE users SET photo_skipped = 1 WHERE id = ?", (g.user["id"],))
    # One reminder in the bell, instead of a banner on every page.
    notify(g.user["id"], "account", "Add a profile photo so people know who they're playing with.",
           url_for("profile.photo_upload"), key="tip:photo")
    db.commit()
    return redirect(after_sign_up())


def after_sign_up():
    """The last sign-up step is done: the one-time "You're in!" screen (home screen), then where they were going."""
    destination = session.pop("after_photo", None)
    return url_for("profile.welcome", next=safe_next(destination.rstrip("?")) if destination else url_for("events.feed"))


@bp.route("/welcome")
@login_required
def welcome():
    """"You're in!": how to put the app on the home screen (iPhone: the two taps; Android: one button). app.js
    skips straight on where that isn't possible (laptops, in-app browsers, already installed)."""
    return render_template("profile/welcome.html", next=safe_next(request.args.get("next", "")))


@bp.route("/u/<int:user_id>/photo")
@login_required
def photo(user_id):
    """The profile picture: 640px for the big view, or ?s=96 / ?s=160 for the small circles in lists (a
    32px circle doesn't need a 640px photo: that's most of what a feed would download on a phone)."""
    row = get_db().execute("SELECT image FROM avatars WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        abort(404)
    image = row["image"]
    size = request.args.get("s", type=int)
    if size in THUMB_SIZES:
        image = thumbnail(image, size)
    response = Response(image, mimetype="image/jpeg")
    # The URL changes whenever the picture does (?v=...), so it can be cached for a long time.
    response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
    return response


@bp.route("/u/<int:user_id>")
@login_required
def view(user_id):
    user = get_db().execute(
        "SELECT id, full_name, email, grad_year, bio, pronouns, gender, instagram, snapchat, tiktok, x_handle, linkedin,"
        " avatar_updated, suspended, created_at FROM users"
        " WHERE id = ? AND verified = 1",
        (user_id,),
    ).fetchone()
    if user is None or (user["suspended"] and user_id != g.user["id"] and not is_admin()):
        abort(404)
    hosting = query_events(["e.host_id = :uid", "e.cancelled = 0", "e.ends_at >= :now", INSIDE_VISIBLE, SHOWN_UNLESS_FULL],
                           {"uid": user_id, "now": to_db(now_local())}, limit=10)
    # Emails are private: only visible to yourself and people you actually played with (a game you were both
    # in has ended). Joining a stranger's game just to read their email doesn't work.
    show_email = user_id == g.user["id"] or get_db().execute(
        """SELECT 1 FROM rsvps mine JOIN rsvps theirs ON mine.event_id = theirs.event_id
           JOIN events e ON e.id = mine.event_id
           WHERE mine.user_id = ? AND theirs.user_id = ? AND e.cancelled = 0 AND e.ends_at < ?""",
        (g.user["id"], user_id, to_db(now_local())),
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
    """Edit profile, screen 1: about you. "Next" saves it and goes on to socials and sports."""
    me = g.user
    if request.method == "POST":
        form = request.form
        full_name = person_name(form.get("full_name"))
        grad_year = form.get("grad_year", "").strip()
        bio = multi_line(form.get("bio"))
        pronouns = one_line(form.get("pronouns"))
        gender = form.get("gender", "")

        error = None
        if not full_name:
            error = "Full name cannot be empty."
        elif not has_a_letter(full_name):
            error = "Please use your real name, so teammates know who you are."
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

        if error is None:
            db = get_db()
            db.execute("""UPDATE users SET full_name = :full_name, grad_year = :grad_year, bio = :bio,
                              pronouns = :pronouns, gender = :gender WHERE id = :id""",
                       {"full_name": full_name, "grad_year": int(grad_year) if grad_year else None, "bio": bio,
                        "pronouns": pronouns, "gender": gender, "id": me["id"]})
            db.commit()
            return redirect(url_for("profile.edit_sports"))  # screen 2: socials and sports
        flash(error, "error")
    else:
        form = MultiDict([("full_name", me["full_name"]), ("grad_year", me["grad_year"] or ""), ("bio", me["bio"]),
                          ("pronouns", me["pronouns"]), ("gender", me["gender"])])
    return render_template("profile/edit.html", form=form, max_grad_year=now_local().year + 8, genders=GENDERS)


@bp.route("/profile/edit/sports", methods=("GET", "POST"))
@login_required
def edit_sports():
    """Edit profile, screen 2: your socials and the sports you play (also where "Pick your sports" links go)."""
    me = g.user
    if request.method == "POST":
        form = request.form
        socials = {key: clean_social(key, form.get(key)) for key in PERSON_SOCIALS}
        bad_social = next((key for key, value in socials.items()
                           if value and not re.fullmatch(PERSON_SOCIAL_RULES[key][1], value)), None)
        if bad_social == "linkedin":
            flash("That LinkedIn doesn't look right. Paste your profile link, like linkedin.com/in/dubs-husky.", "error")
        elif bad_social:
            flash(f"That {PERSON_SOCIAL_RULES[bad_social][0]} username doesn't look right. Just the username, like @dubs.",
                  "error")
        else:
            db = get_db()
            db.execute("UPDATE users SET instagram = :instagram, snapchat = :snapchat, tiktok = :tiktok,"
                       " x_handle = :x_handle, linkedin = :linkedin WHERE id = :id", {**socials, "id": me["id"]})
            set_user_sports(me["id"], [s for s in form.getlist("sports") if s in SPORTS])
            db.commit()
            flash("Profile saved.", "success")
            return redirect(url_for("profile.view", user_id=me["id"]))
    else:
        form = MultiDict([(key, me[key]) for key in PERSON_SOCIALS] + [("sports", s) for s in user_sports(me["id"])])
    return render_template("profile/edit_sports.html", form=form,
                           socials={key: PERSON_SOCIAL_RULES[key][0] for key in PERSON_SOCIALS})


@bp.route("/profile/password", methods=("POST",))
@login_required
def change_password():
    form = request.form
    problem = check_current_password(g.user, form.get("current_password", ""))
    if problem is not None:
        error = problem or "Your current password isn't right."
    else:
        error = password_problem(form.get("password", ""), form.get("password2", ""))
        if error is None and check_password_hash(g.user["password_hash"], form["password"]):
            error = "That's the password you have now. Pick a new one."
    if error:
        flash(f"{error} Your password was not changed.", "error")
    else:
        db = get_db()
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(form["password"]), g.user["id"]))
        end_other_sessions(g.user["id"])
        db.commit()
        flash("Password changed. You're logged out on your other devices.", "success")
    return redirect(url_for("settings.password") if error else url_for("settings.home"))


CONFIRM_WORD = "DELETE"
FORMER_MEMBER_EMAIL = "former-member@sportive.invalid"  # not @uw.edu, so nobody can sign up as it


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


SOLE_OFFICER = """SELECT c.id, c.name FROM clubs c JOIN club_members m ON m.club_id = c.id
           WHERE m.user_id = ? AND m.role = 'officer'
             AND (SELECT COUNT(*) FROM club_members o WHERE o.club_id = c.id AND o.role = 'officer') = 1
             AND {} (c.status = 'approved' AND EXISTS (SELECT 1 FROM club_members o WHERE o.club_id = c.id
                                                        AND o.role = 'member'))"""


def clubs_only_i_lead(user_id):
    """Live clubs with members where this person is the only officer (they'd be left without a leader)."""
    return get_db().execute(SOLE_OFFICER.format(""), (user_id,)).fetchall()


def clubs_that_go_with_me(user_id):
    """Clubs only this person runs that nobody else is in yet (still pending, rejected, or no members).
    There's no one to hand them to, so they're deleted with the account instead of blocking it."""
    return get_db().execute(SOLE_OFFICER.format("NOT"), (user_id,)).fetchall()


def keep_games_other_people_played(user_id):
    """Finished games this person hosted are part of everyone else's history (Past games, badges,
    Top Dawgs), so they're handed to a hidden "Former member" account instead of being deleted.
    That account is unverified with no usable password, so it can't log in or show up anywhere."""
    db = get_db()
    played = """host_id = :me AND cancelled = 0 AND ends_at < :now
                AND EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = events.id AND r.user_id != :me)"""
    params = {"me": user_id, "now": to_db(now_local())}
    if not db.execute(f"SELECT 1 FROM events WHERE {played}", params).fetchone():
        return
    row = db.execute("SELECT id FROM users WHERE email = ?", (FORMER_MEMBER_EMAIL,)).fetchone()
    params["former"] = row["id"] if row else db.execute(
        "INSERT INTO users (email, password_hash, full_name, verified) VALUES (?, '!', 'Former member', 0)",
        (FORMER_MEMBER_EMAIL,)).lastrowid
    db.execute(f"UPDATE events SET host_id = :former WHERE {played}", params)


@bp.route("/profile/delete", methods=("GET", "POST"))
@login_required
def delete_account():
    """Step 1 (GET): an "Are you sure?" page showing what you'd lose.
    Step 2 (POST): delete, only with your password AND the word DELETE typed in."""
    sole_officer = clubs_only_i_lead(g.user["id"])
    if request.method == "GET":
        return render_template("profile/delete.html", lose=what_you_would_lose(g.user["id"]), word=CONFIRM_WORD,
                               sole_officer=sole_officer, lone_clubs=clubs_that_go_with_me(g.user["id"]))
    if sole_officer:
        flash(f"You're the only officer of {sole_officer[0]['name']}. Make someone else an officer first.", "error")
        return redirect(url_for("profile.delete_account"))
    if request.form.get("confirm", "").strip().upper() != CONFIRM_WORD:
        flash(f"Type {CONFIRM_WORD} in the box to confirm. Your account was not deleted.", "error")
        return redirect(url_for("profile.delete_account"))
    problem = check_current_password(g.user, request.form.get("password", ""))
    if problem is not None:
        flash(f"{problem or 'That password isn’t right.'} Your account was not deleted.", "error")
        return redirect(url_for("profile.delete_account"))
    # Games they host disappear with the account, so warn everyone who joined (like canceling would).
    for event in query_events(["e.host_id = :me", "e.cancelled = 0", "e.ends_at >= :now"],
                              {"now": to_db(now_local())}):
        tell_players_it_was_cancelled(event, page_stays=False)
    db = get_db()
    for club in clubs_that_go_with_me(g.user["id"]):
        db.execute("DELETE FROM clubs WHERE id = ?", (club["id"],))
    keep_games_other_people_played(g.user["id"])
    # ON DELETE CASCADE (schema.sql) also removes your sports, RSVPs and the rest of your hosted events.
    # These two are kept by email address, not account, so they go by hand.
    db.execute("DELETE FROM login_failures WHERE email = ?", (g.user["email"],))
    db.execute("DELETE FROM email_codes WHERE inbox = ?", (g.user["email"].split("@")[0],))
    db.execute("DELETE FROM users WHERE id = ?", (g.user["id"],))
    db.commit()
    session.clear()
    flash("Your account was deleted.", "info")
    return redirect(url_for("index"))
