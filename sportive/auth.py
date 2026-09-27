"""Sign up (UW emails only), email verification, log in / out, and CSRF protection."""
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
from .mail import send_email
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


# ---------------------------------------------------------------- helpers

def login_required(view):
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
    if request.method == "POST" and current_app.config["CSRF_ENABLED"]:
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
            "SELECT * FROM users WHERE id = ? AND verified = 1", (user_id,)
        ).fetchone()


def age_on(born, today):
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def safe_next(target):
    """Only allow redirects back into this site (blocks //evil.com tricks)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("index")


def log_in(user):
    after = session.get("after_login")  # e.g. a shared event link they opened before signing up
    session.clear()
    session.permanent = True  # stay logged in on your phone (see PERMANENT_SESSION_LIFETIME)
    session["user_id"] = user["id"]
    get_db().execute("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?", (user["id"],))
    get_db().commit()
    if user["birth_date"]:
        born = date.fromisoformat(user["birth_date"])
        today = now_local().date()
        if (born.month, born.day) == (today.month, today.day):
            # Kept from the original app :)
            flash("🎂 Happy 'escaped from your mom' anniversary — you won a coupon!", "birthday")
    return safe_next(after)


# ---------------------------------------------------------- verification

def send_verification_email(email, code):
    sent = send_email(
        email,
        f"Your Sportive Circle code: {code}",
        f"Your Sportive Circle verification code is {code}.\n"
        f"It expires in {CODE_TTL.seconds // 60} minutes.\n\n"
        "If you didn't sign up, you can ignore this email.",
    )
    if not sent:
        # Local development: no email server, so show the code instead.
        flash(f"Dev mode (no email server set up): your code is {code}", "info")


def start_verification(email):
    code = f"{secrets.randbelow(10**6):06d}"
    db = get_db()
    db.execute(
        "UPDATE users SET verify_code = ?, verify_expires = ?, verify_sent_at = ?, verify_attempts = 0"
        " WHERE email = ?",
        (code, to_db(now_local() + CODE_TTL), to_db(now_local()), email),
    )
    db.commit()
    session["pending_email"] = email
    send_verification_email(email, code)


# ----------------------------------------------------------------- sign up

def validate_signup(full_name, email, password, password2, grad_year, birth_date):
    domain = current_app.config["ALLOWED_EMAIL_DOMAIN"]
    if not full_name:
        return "Full name cannot be empty."
    if not email:
        return "Email cannot be empty."
    if email.count("@") != 1 or not email.endswith("@" + domain) or email.startswith("@"):
        return f"Please use your @{domain} email."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password != password2:
        return "Passwords do not match."
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
        full_name = form.get("full_name", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        password2 = form.get("password2", "")
        grad_year = form.get("grad_year", "").strip()
        birth_date = form.get("birth_date", "").strip()
        sports = [s for s in form.getlist("sports") if s in SPORTS]

        error = validate_signup(full_name, email, password, password2, grad_year, birth_date)
        if error is None:
            db = get_db()
            # An unverified account never proved it owns the email, so it can be replaced.
            db.execute("DELETE FROM users WHERE email = ? AND verified = 0", (email,))
            try:
                cur = db.execute(
                    "INSERT INTO users (email, password_hash, full_name, grad_year, birth_date)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (email, generate_password_hash(password, current_app.config["PASSWORD_HASH_METHOD"]), full_name,
                     int(grad_year) if grad_year else None, birth_date),
                )
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
                " verify_attempts = 0 WHERE id = ?",
                (user["id"],),
            )
            db.commit()
            destination = log_in(user)
            flash(f"Welcome to Sportive Circle, {user['full_name'].split()[0]}!", "success")
            return redirect(destination)
        flash(error, "error")
    return render_template("auth/verify.html", email=email)


@bp.route("/verify/resend", methods=("POST",))
def resend_code():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("auth.login"))
    user = get_db().execute("SELECT verify_sent_at FROM users WHERE email = ?", (email,)).fetchone()
    if user and user["verify_sent_at"] and now_local() < from_db(user["verify_sent_at"]) + RESEND_COOLDOWN:
        flash("We just sent you a code. Wait a minute before asking for another one.", "error")
        return redirect(url_for("auth.verify"))
    start_verification(email)
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
            flash("Wrong email or password!", "error")
        elif not user["verified"]:
            start_verification(email)
            flash("Please verify your email first. We sent you a new code.", "info")
            return redirect(url_for("auth.verify"))
        else:
            return redirect(log_in(user))
    return render_template("auth/login.html", next_url=next_url)


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    return redirect(url_for("index"))
