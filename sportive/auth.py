"""Sign up (UW emails only), email verification, log in / out, and CSRF protection."""
import calendar
import functools
import logging
import secrets
import sqlite3
from datetime import date, timedelta

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

from .constants import SPORTS
from .db import get_db, set_user_sports
from .mail import compose, failure_reason, send_email
from .textutil import one_line
from .timeutil import from_db, now_local, to_db

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=15)
MAX_CODE_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_FAILED_LOGINS = 10
LOCKOUT = timedelta(minutes=15)
MIN_AGE, MAX_AGE = 15, 123  # same age range as the original desktop app
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_NAME_LENGTH = 60
MAX_EMAIL_LENGTH = 254   # the longest an email address can be


# ---------------------------------------------------------------- helpers

def login_required(view):
    """Send logged-out visitors to the login page, then back here afterwards."""
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)
    return wrapped


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def csrf_field():
    """Hidden input every POST form includes (templates: {{ csrf_field() }})."""
    return Markup(f'<input type="hidden" name="csrf_token" value="{csrf_token()}">')


@bp.before_app_request
def check_csrf():
    # The scheduler's reminder call proves itself with its own secret token instead (reminders.py).
    if request.method == "POST" and current_app.config["CSRF_ENABLED"] and request.endpoint != "tasks.send_reminders_task":
        sent = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not sent or not expected or not secrets.compare_digest(sent, expected):
            abort(400, "Your form expired. Go back, refresh the page and try again.")


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ? AND verified = 1 AND suspended = 0", (user_id,)
        ).fetchone()


def age_on(born, today):
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def is_birthday(born, today):
    """Leap-day babies celebrate on Feb 28 in years without a Feb 29."""
    if (born.month, born.day) == (2, 29) and not calendar.isleap(today.year):
        return (today.month, today.day) == (2, 28)
    return (born.month, born.day) == (today.month, today.day)


def safe_next(target):
    """Only allow redirects back into this site (blocks //evil.com tricks)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("index")


def log_in(user):
    after = session.get("after_login")  # e.g. a shared event link they opened before signing up
    invite = session.get("invite_link")  # a friend's "you're in my game" link
    session.clear()
    session.permanent = True  # stay logged in on your phone (see PERMANENT_SESSION_LIFETIME)
    session["user_id"] = user["id"]
    get_db().execute("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?", (user["id"],))
    get_db().commit()
    if user["birth_date"]:
        born = date.fromisoformat(user["birth_date"])
        today = now_local().date()
        if is_birthday(born, today):
            flash(f"Happy birthday, {user['full_name'].split()[0]}! 🎂", "birthday")
    if invite:
        from .parties import accept_invite_link  # imported here: parties.py imports this module
        destination = accept_invite_link(user, invite)
        if destination:
            return destination
    return safe_next(after)


# ---------------------------------------------------------- verification

def send_verification_email(email, code, purpose="signup"):
    minutes = CODE_TTL.seconds // 60
    row = get_db().execute("SELECT full_name FROM users WHERE email = ?", (email,)).fetchone()
    first = row["full_name"].split()[0] if row and row["full_name"].strip() else "Husky"
    after = [f"Type it on the Sportive Circle page you just came from. It expires in {minutes} minutes."]
    if purpose == "reset":
        subject = f"{code} is your Sportive Circle password reset code"
        heading, lines = f"Reset your password, {first}", ["Here's the code to set a new password:"]
        reason = "Didn't ask for this? You can ignore this email. Your password hasn't changed."
    else:
        subject = f"{code} is your Sportive Circle code"
        heading = f"Welcome to the pack, {first}! 🐺"
        lines = ["You're one step away from finding people to play sports with. Here's your code:"]
        reason = "Didn't sign up? You can ignore this email. Nothing happens without the code."
    body, html = compose(subject, heading, lines, code=code, after=after, reason=reason,
                         preheader=f"Your code is {code}. It expires in {minutes} minutes.")
    try:
        sent = send_email(email, subject, body, html=html)
    except Exception as error:  # the email service refused or is down: say so instead of crashing
        log.exception("Couldn't send a code email to %s", email)
        # Let them ask for a new code right away (no 1-minute wait for an email that never went out).
        get_db().execute("UPDATE users SET verify_sent_at = NULL WHERE email = ?", (email,))
        get_db().commit()
        contact = current_app.config.get("CONTACT_EMAIL")
        flash("We couldn't send the email just now. Wait a minute, then ask for a new code."
              + (f" If it keeps happening, email {contact}." if contact else "")
              + f" (Reason: {failure_reason(error)}.)", "error")
        return False
    if not sent:
        # Local development: no email server, so show the code instead.
        flash(f"Dev mode (no email server set up): your code is {code}", "info")
    return True


def resend_wait(email):
    """Seconds until a new code can be sent to this address (0 = now). Stops email spam, and powers the
    "Resend code in 42s" countdown."""
    row = get_db().execute("SELECT verify_sent_at FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not row["verify_sent_at"]:
        return 0
    left = from_db(row["verify_sent_at"]) + RESEND_COOLDOWN - now_local()
    return max(0, int(left.total_seconds()) + 1) if left.total_seconds() > 0 else 0


def code_recently_sent(email):
    """True if we emailed this address a code less than a minute ago."""
    return resend_wait(email) > 0


def start_verification(email, session_key="pending_email"):
    code = f"{secrets.randbelow(10**6):06d}"
    db = get_db()
    db.execute(
        "UPDATE users SET verify_code = ?, verify_expires = ?, verify_sent_at = ?, verify_attempts = 0"
        " WHERE email = ?",
        (code, to_db(now_local() + CODE_TTL), to_db(now_local()), email),
    )
    db.commit()
    session[session_key] = email
    return send_verification_email(email, code, "reset" if session_key == "reset_email" else "signup")


# ----------------------------------------------------------------- sign up

def validate_signup(full_name, email, password, password2, grad_year, birth_date):
    domains = current_app.config["ALLOWED_EMAIL_DOMAINS"]
    if not full_name:
        return "Full name cannot be empty."
    if len(full_name) > MAX_NAME_LENGTH:
        return f"Please keep your name under {MAX_NAME_LENGTH} characters."
    if not email:
        return "Email cannot be empty."
    if len(email) > MAX_EMAIL_LENGTH:
        return "Please use your UW email address (ending in @uw.edu)."
    if email.count("@") != 1 or email.startswith("@") or email.split("@")[1] not in domains:
        return "Please use your UW email address (ending in @uw.edu)."
    problem = password_problem(password, password2)
    if problem:
        return problem
    if grad_year and (not grad_year.isdigit() or not 1950 <= int(grad_year) <= now_local().year + 8):
        return "Please enter a valid graduation year."
    if not birth_date:
        return "Date of birth cannot be empty."
    try:
        born = date.fromisoformat(birth_date)
    except ValueError:
        return "Please enter a valid date of birth."
    if not MIN_AGE <= age_on(born, now_local().date()) <= MAX_AGE:
        return "You are not within the age range required to use this app."
    existing = get_db().execute("SELECT verified FROM users WHERE email = ?", (email,)).fetchone()
    if existing and existing["verified"]:
        return "This email is already in use."
    return None


@bp.route("/signup", methods=("GET", "POST"))
def signup():
    form = request.form
    if request.args.get("next"):
        session["after_login"] = safe_next(request.args["next"])
    if request.method == "POST":
        full_name = one_line(form.get("full_name"))
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        password2 = form.get("password2", "")
        grad_year = form.get("grad_year", "").strip()
        birth_date = form.get("birth_date", "").strip()
        sports = [s for s in form.getlist("sports") if s in SPORTS]
        from .settings import THEMES  # imported here: settings.py imports this module
        theme = form.get("theme") if form.get("theme") in THEMES else "light"

        error = validate_signup(full_name, email, password, password2, grad_year, birth_date)
        if error is None and code_recently_sent(email):
            error = "We just sent a code to that email. Check your inbox, or wait a minute and try again."
        if error is None:
            db = get_db()
            # An unverified account never proved it owns the email, so it can be replaced.
            db.execute("DELETE FROM users WHERE email = ? AND verified = 0", (email,))
            try:
                cur = db.execute(
                    "INSERT INTO users (email, password_hash, full_name, grad_year, birth_date, theme)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (email, hash_password(password), full_name,
                     int(grad_year) if grad_year else None, birth_date, theme),
                )
                session["theme"] = theme  # the code page already looks the way they picked
                set_user_sports(cur.lastrowid, sports)
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                error = "This email is already in use."
            else:
                start_verification(email)
                return redirect(url_for("auth.verify"))
        flash(error, "error")
    today = now_local().date()
    try:
        latest_birth_date = today.replace(year=today.year - MIN_AGE)
    except ValueError:  # today is Feb 29
        latest_birth_date = today.replace(year=today.year - MIN_AGE, day=28)
    return render_template("auth/signup.html", form=form, current_year=today.year,
                           latest_birth_date=latest_birth_date.isoformat())


@bp.route("/verify", methods=("GET", "POST"))
def verify():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None:
            session.pop("pending_email", None)
            return redirect(url_for("auth.signup"))

        error = None
        if user["verify_attempts"] >= MAX_CODE_ATTEMPTS:
            error = "Too many wrong tries. Send yourself a new code."
        elif not user["verify_code"] or now_local() > from_db(user["verify_expires"]):
            error = "That code expired. Send yourself a new one."
        elif not secrets.compare_digest(code, user["verify_code"]):
            db.execute("UPDATE users SET verify_attempts = verify_attempts + 1 WHERE id = ?", (user["id"],))
            db.commit()
            error = "Wrong code, try again."

        if error is None:
            db.execute(
                "UPDATE users SET verified = 1, verify_code = NULL, verify_expires = NULL,"
                " verify_attempts = 0, verify_sent_at = NULL WHERE id = ?",
                (user["id"],),
            )
            from .notifications import start_markers  # imported here: notifications.py imports this module
            start_markers(user["id"])
            db.commit()
            destination = log_in(user)
            flash(f"Welcome, {user['full_name'].split()[0]}!", "celebrate")
            return redirect(destination)
        flash(error, "error")
    return render_template("auth/verify.html", email=email, wait=resend_wait(email))


@bp.route("/verify/resend", methods=("POST",))
def resend_code():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("auth.login"))
    if code_recently_sent(email):
        flash("We just sent a code. Give it a minute.", "error")
        return redirect(url_for("auth.verify"))
    if start_verification(email):  # on failure, send_verification_email already explained what happened
        flash("We sent you a new code.", "success")
    return redirect(url_for("auth.verify"))


# ------------------------------------------------------------ log in / out

@bp.route("/login", methods=("GET", "POST"))
def login():
    next_url = request.values.get("next", "")
    if next_url:
        session["after_login"] = safe_next(next_url)
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and user["locked_until"] and now_local() < from_db(user["locked_until"]):
            flash("Too many wrong passwords. Try again in 15 minutes.", "error")
        elif user is None or not check_password_hash(user["password_hash"], password):
            if user is not None:
                failed = user["failed_logins"] + 1
                locked = to_db(now_local() + LOCKOUT) if failed >= MAX_FAILED_LOGINS else None
                db.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                           (0 if locked else failed, locked, user["id"]))
                db.commit()
            flash("Wrong email or password.", "error")
        elif user["suspended"]:
            flash("This account is suspended for breaking the rules. Think it's a mistake? See the Terms page.",
                  "error")
        elif not user["verified"]:
            if code_recently_sent(email):
                session["pending_email"] = email
                flash("Check your email for the code we sent you.", "info")
            else:
                start_verification(email)
                flash("Check your email. We sent you a new code.", "info")
            return redirect(url_for("auth.verify"))
        else:
            return redirect(log_in(user))
    return render_template("auth/login.html", next_url=next_url)


# --------------------------------------------------------- forgot password

@bp.route("/forgot", methods=("GET", "POST"))
def forgot_password():
    """Step 1: email a 6-digit code. The answer is the same whether or not the account exists,
    so nobody can use this page to find out who has an account."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_db().execute("SELECT verified, suspended FROM users WHERE email = ?", (email,)).fetchone()
        if user and user["verified"] and not user["suspended"] and not code_recently_sent(email):
            start_verification(email, session_key="reset_email")
        session["reset_email"] = email
        flash("If that email has an account, we sent it a 6-digit code.", "info")
        return redirect(url_for("auth.reset_password"))
    return render_template("auth/forgot.html")


@bp.route("/reset", methods=("GET", "POST"))
def reset_password():
    """Step 2: the code plus a new password."""
    email = session.get("reset_email")
    if not email:
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ? AND verified = 1", (email,)).fetchone()
        error = None
        if user is None or not user["verify_code"]:
            error = "That code isn't right. Ask for a new one."
        elif user["verify_attempts"] >= MAX_CODE_ATTEMPTS:
            error = "Too many wrong tries. Ask for a new code."
        elif now_local() > from_db(user["verify_expires"]):
            error = "That code expired. Ask for a new one."
        elif not secrets.compare_digest(code, user["verify_code"]):
            db.execute("UPDATE users SET verify_attempts = verify_attempts + 1 WHERE id = ?", (user["id"],))
            db.commit()
            error = "Wrong code, try again."
        else:
            error = password_problem(password, request.form.get("password2", ""))
        if error is None:
            db.execute("UPDATE users SET password_hash = ?, verify_code = NULL, verify_expires = NULL,"
                       " verify_attempts = 0 WHERE id = ?", (hash_password(password), user["id"]))
            db.commit()
            destination = log_in(user)
            flash("Password changed. You're logged in.", "success")
            return redirect(destination)
        flash(error, "error")
    return render_template("auth/reset.html", email=email)


def hash_password(password):
    return generate_password_hash(password, current_app.config["PASSWORD_HASH_METHOD"])


def password_problem(password, password2):
    """The error message for a new password, or None if it's fine."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password can be at most {MAX_PASSWORD_LENGTH} characters."
    if password != password2:
        return "Passwords do not match."
    return None


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    return redirect(url_for("index"))
