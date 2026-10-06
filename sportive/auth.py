"""Sign up (UW emails only), email verification, log in / out, and CSRF protection."""
import calendar
import functools
import logging
import secrets
import sqlite3
from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from markupsafe import Markup
from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash, generate_password_hash

from .constants import SPORTS
from .db import get_db, set_user_sports
from .mail import compose, failure_reason, send_email
from .textutil import has_a_letter, is_number, person_name, same_secret, typed_code
from .timeutil import SEATTLE, from_db, now_local, to_db

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=15)
MAX_CODE_ATTEMPTS = 5
MAX_CODES_PER_DAY = 5  # email codes per inbox per day: with 5 tries each, 25 guesses a day at most
TOO_MANY_CODES = "That's a lot of codes for one day. Try again tomorrow."
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_FAILED_LOGINS = 10
MAX_FAILED_LOGINS_PER_IP = 30  # wrong passwords from one address, across all accounts, per LOCKOUT window
LOCKOUT = timedelta(minutes=15)
MIN_AGE, MAX_AGE = 18, 123  # adults only: the feed has photos, and people message people they don't know
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
            # A form sent after the login ended (e.g. Follow on a phone tab left open) can't be repeated by
            # opening its address, so after logging in they go back to the page the form was on instead.
            back = request.path if request.method == "GET" else _page_it_came_from()
            return redirect(url_for("auth.login", next=back))
        return view(**kwargs)
    return wrapped


def _page_it_came_from():
    """The page on this site a form was sent from (or Home)."""
    from urllib.parse import urlsplit
    came_from = urlsplit(request.referrer or "")
    if came_from.netloc != request.host:
        return url_for("index")
    return safe_next(came_from.path + (f"?{came_from.query}" if came_from.query else ""))


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
    # So does an unsubscribe link (the signed link is the proof; mail apps' one-click button sends no form token).
    if (request.method == "POST" and current_app.config["CSRF_ENABLED"]
            and request.endpoint not in ("tasks.send_reminders_task", "unsubscribe.one_click")):
        sent = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not sent or not expected or not same_secret(sent, expected):
            abort(400, "Your form expired. Go back, refresh the page and try again.")


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ? AND verified = 1 AND suspended = 0", (user_id,)
        ).fetchone()
        if g.user is not None and session.get("session_version", 0) != g.user["session_version"]:
            session.clear()  # logged out everywhere since this cookie was made (e.g. the password changed)
            g.user = None
        elif g.user is not None and session.get("sid") and get_db().execute(
                "SELECT 1 FROM ended_sessions WHERE sid = ?", (session["sid"],)).fetchone():
            session.clear()  # this login was logged out; someone kept a copy of the cookie
            g.user = None


def end_other_sessions(user_id):
    """Log this account out on every other device (their cookies stop working); this one stays logged in."""
    db = get_db()
    db.execute("UPDATE users SET session_version = session_version + 1 WHERE id = ?", (user_id,))
    if session.get("user_id") == user_id:
        session["session_version"] = db.execute("SELECT session_version FROM users WHERE id = ?",
                                                (user_id,)).fetchone()[0]


def age_on(born, today):
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def is_birthday(born, today):
    """Leap-day babies celebrate on Feb 28 in years without a Feb 29."""
    if (born.month, born.day) == (2, 29) and not calendar.isleap(today.year):
        return (today.month, today.day) == (2, 28)
    return (born.month, born.day) == (today.month, today.day)


def safe_next(target):
    """Only allow redirects back into this site. Browsers drop tabs/newlines and treat "\\" as "/", so
    "/\\tevil.com" or "/\\evil.com" would become //evil.com; any whitespace, control character or
    backslash is refused."""
    if (target and target.startswith("/") and not target.startswith("//")
            and not any(ch == "\\" or ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in target)):
        return target
    return url_for("index")


def log_in(user, remember=True, just_signed_up=False):
    """remember=False ("Remember me" unticked): the login ends when the browser closes.
    just_signed_up: they just confirmed a new account (a friend's invite link then makes them friends)."""
    after = session.get("after_login")  # e.g. a shared event link they opened before signing up
    invite = session.get("invite_link")  # a friend's "you're in my game" link
    session.clear()
    session.permanent = remember  # stay logged in on your phone (see PERMANENT_SESSION_LIFETIME)
    session["user_id"] = user["id"]
    session["sid"] = secrets.token_urlsafe(16)  # this login's id, so "Log out" can end it for good
    session["session_version"] = get_db().execute("SELECT session_version FROM users WHERE id = ?",
                                                  (user["id"],)).fetchone()[0]
    get_db().execute("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?", (user["id"],))
    get_db().commit()
    if user["birth_date"]:
        born = date.fromisoformat(user["birth_date"])
        today = now_local().date()
        if is_birthday(born, today):
            flash(f"Happy birthday, {user['full_name'].split()[0]}! 🎂", "birthday")
    if invite:
        from .parties import accept_invite_link  # imported here: parties.py imports this module
        destination = accept_invite_link(user, invite, just_signed_up=just_signed_up)
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


SENT_AT_FORMAT = "%Y-%m-%d %H:%M:%S"  # to the second: the cooldown is only a minute long


def now_to_the_second():
    return datetime.now(SEATTLE).replace(tzinfo=None, microsecond=0)


def resend_wait(email):
    """Seconds until a new code can be sent to this address (0 = now). Stops email spam, and powers the
    "Resend code in 42s" countdown."""
    row = get_db().execute("SELECT verify_sent_at FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not row["verify_sent_at"]:
        return 0
    sent = row["verify_sent_at"]
    sent_at = datetime.strptime(sent, SENT_AT_FORMAT) if sent.count(":") == 2 else from_db(sent)
    left = sent_at + RESEND_COOLDOWN - now_to_the_second()
    return max(0, int(left.total_seconds()) + 1) if left.total_seconds() > 0 else 0


def code_recently_sent(email):
    """True if we emailed this address a code less than a minute ago."""
    return resend_wait(email) > 0


def codes_left_today(email):
    """How many more email codes this inbox can get today (MAX_CODES_PER_DAY in a rolling day)."""
    since = to_db(now_local() - timedelta(days=1))
    sent = get_db().execute("SELECT COUNT(*) FROM email_codes WHERE inbox = ? AND sent_at >= ?",
                            (email.split("@")[0], since)).fetchone()[0]
    return max(0, MAX_CODES_PER_DAY - sent)


def start_verification(email, session_key="pending_email"):
    """Email a new 6-digit code. Returns False (and sends nothing) once the day's codes are used up."""
    session[session_key] = email
    if not codes_left_today(email):
        return False
    code = f"{secrets.randbelow(10**6):06d}"
    db = get_db()
    db.execute("INSERT INTO email_codes (inbox, sent_at) VALUES (?, ?)", (email.split("@")[0], to_db(now_local())))
    db.execute(
        "UPDATE users SET verify_code = ?, verify_expires = ?, verify_sent_at = ?, verify_attempts = 0"
        " WHERE email = ?",
        (code, to_db(now_local() + CODE_TTL), now_to_the_second().strftime(SENT_AT_FORMAT), email),
    )
    db.commit()
    return send_verification_email(email, code, "reset" if session_key == "reset_email" else "signup")


# ----------------------------------------------------------------- sign up

def validate_signup(full_name, email, password, password2, grad_year, birth_date):
    domains = current_app.config["ALLOWED_EMAIL_DOMAINS"]
    if not full_name:
        return "Full name cannot be empty."
    if not has_a_letter(full_name):
        return "Please use your real name, so teammates know who you are."
    if len(full_name) > MAX_NAME_LENGTH:
        return f"Please keep your name under {MAX_NAME_LENGTH} characters."
    if not email:
        return "Email cannot be empty."
    if len(email) > MAX_EMAIL_LENGTH:
        return "Please use your UW email address (ending in @uw.edu)."
    if email.count("@") != 1 or email.startswith("@") or email.split("@")[1] not in domains:
        return "Please use your UW email address (ending in @uw.edu)."
    local = email.split("@")[0]
    if "+" in local:  # netid+2@uw.edu reaches the same inbox, so it would allow a second account
        return "Please use your plain UW email (netid@uw.edu), without a +tag."
    problem = password_problem(password, password2)
    if problem:
        return problem
    if grad_year and (not is_number(grad_year) or not 1950 <= int(grad_year) <= now_local().year + 8):
        return "Please enter a valid graduation year."
    if not birth_date:
        return "Date of birth cannot be empty."
    try:
        born = date.fromisoformat(birth_date)
    except ValueError:
        return "Please enter a valid date of birth."
    age = age_on(born, now_local().date())
    if age < MIN_AGE:
        return f"You need to be {MIN_AGE} or older to use Sportive Circle."
    if age > MAX_AGE:
        return "Please check your date of birth."
    # netid@uw.edu and netid@u.washington.edu are the same UW mailbox: one account per person.
    same_inbox = [f"{local}@{domain}" for domain in domains]
    existing = get_db().execute(
        f"SELECT email FROM users WHERE verified = 1 AND email IN ({', '.join('?' for _ in same_inbox)})",
        same_inbox).fetchone()
    if existing:
        return ("This email is already in use." if existing["email"] == email
                else f"You already have an account as {existing['email']}. Log in with that email.")
    return None


def _same_person_signing_up(email, password):
    """The unverified account for this email is this browser's (it's the one waiting for a code here) or was
    started with this same password (a double tap, or Back from another tab)."""
    if session.get("pending_email") == email:
        return True
    row = get_db().execute("SELECT password_hash FROM users WHERE email = ? AND verified = 0", (email,)).fetchone()
    return row is not None and check_password_hash(row["password_hash"], password)


def claim_code_try(user_id):
    """Use up one of the 5 tries on an email code, in a single statement: guesses sent at the same moment from
    many tabs can't all slip past the limit. True if there was a try left. (A right code resets the count.)"""
    db = get_db()
    claimed = db.execute("UPDATE users SET verify_attempts = verify_attempts + 1 WHERE id = ? AND verify_attempts < ?",
                         (user_id, MAX_CODE_ATTEMPTS)).rowcount
    db.commit()
    return bool(claimed)


@bp.route("/signup", methods=("GET", "POST"))
def signup():
    if g.user is not None:  # already logged in: a second account from here would log this one out
        return redirect(url_for("clubs.create") if request.args.get("club") else safe_next(request.args.get("next", "")))
    form = request.form
    if request.args.get("next"):
        session["after_login"] = safe_next(request.args["next"])
    if request.args.get("club"):  # "Club officer?": an account, the email code, then straight to their club
        session["club_signup"] = True
        session["after_login"] = url_for("clubs.create")
    elif request.method == "GET" and not request.args.get("fix"):
        session.pop("club_signup", None)
    # Officers skip the sports and texts steps: they're here to register their club (the profile can wait).
    next_step = url_for("auth.verify") if session.get("club_signup") else url_for("auth.signup_sports")
    if request.method == "POST":
        full_name = person_name(form.get("full_name"))
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        password2 = form.get("password2", "")
        grad_year = form.get("grad_year", "").strip()
        birth_date = form.get("birth_date", "").strip()
        error = validate_signup(full_name, email, password, password2, grad_year, birth_date)
        db = get_db()
        if error is None:
            # One sign-up for this email at a time, until its code is saved: a double tap waits here, then finds
            # the code just sent (below) instead of sending a second one that makes the first one wrong.
            db.commit()
            db.execute("BEGIN IMMEDIATE")
        if error is None and code_recently_sent(email) and _same_person_signing_up(email, password):
            # Came back to fix something (Back, "Wrong email?", or a double tap): keep the code already sent.
            db.execute("UPDATE users SET password_hash = ?, full_name = ?, grad_year = ?, birth_date = ?"
                       " WHERE email = ? AND verified = 0",
                       (hash_password(password), full_name, int(grad_year) if grad_year else None, birth_date, email))
            db.commit()
            session["pending_email"] = email
            session.pop("signup_form", None)
            return redirect(next_step)
        if error is None and code_recently_sent(email):
            error = "We just sent a code to that email. Check your inbox, or wait a minute and try again."
        if error is None and not codes_left_today(email):
            error = TOO_MANY_CODES
        if error is None:
            # An unverified account never proved it owns the email, so it can be replaced (also one started with
            # the other UW address for the same inbox: one account per person).
            local = email.split("@")[0]
            same_inbox = [f"{local}@{domain}" for domain in current_app.config["ALLOWED_EMAIL_DOMAINS"]]
            db.execute(f"DELETE FROM users WHERE verified = 0 AND email IN ({', '.join('?' for _ in same_inbox)})",
                       same_inbox)
            if session.get("pending_email") and session["pending_email"] != email:  # "Wrong email? Fix it"
                db.execute("DELETE FROM users WHERE verified = 0 AND email = ?", (session["pending_email"],))
            try:
                cur = db.execute(
                    "INSERT INTO users (email, password_hash, full_name, grad_year, birth_date)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (email, hash_password(password), full_name, int(grad_year) if grad_year else None, birth_date),
                )
                set_user_sports(cur.lastrowid, [s for s in form.getlist("sports") if s in SPORTS])
            except sqlite3.IntegrityError:
                db.rollback()
                error = "This email is already in use."
            else:
                session.pop("signup_form", None)
                start_verification(email)  # saves the code (ending the one-at-a-time hold), then emails it
                db.commit()  # (and the account, even if no code could be sent today)
                return redirect(next_step)
        db.rollback()  # let go of the hold, if taken
        flash(error, "error")
        # Back to a normal page (not the answer to a form post), so the phone's Back button works on the next
        # step. What they typed comes back, except the passwords.
        session["signup_form"] = {key: form.get(key, "") for key in ("full_name", "email", "grad_year", "birth_date")}
        return redirect(url_for("auth.signup"))
    form = session.pop("signup_form", None) or {}
    pending = session.get("pending_email")
    if not form and request.args.get("fix") and pending:  # "Wrong email?" on the code page: start from what they typed
        row = get_db().execute("SELECT full_name, email, grad_year, birth_date FROM users WHERE email = ? AND verified = 0",
                               (pending,)).fetchone()
        if row:
            form = {key: "" if row[key] is None else str(row[key]) for key in row.keys()}
    today = now_local().date()
    try:
        latest_birth_date = today.replace(year=today.year - MIN_AGE)
    except ValueError:  # today is Feb 29
        latest_birth_date = today.replace(year=today.year - MIN_AGE, day=28)
    return render_template("auth/signup.html", form=form, current_year=today.year,
                           latest_birth_date=latest_birth_date.isoformat(), club_signup=session.get("club_signup"))


@bp.route("/signup/sports", methods=("GET", "POST"))
def signup_sports():
    """Sign-up step 2: which sports they play (optional) and the look, then on to the code."""
    email = session.get("pending_email")
    user = email and get_db().execute("SELECT id FROM users WHERE email = ? AND verified = 0",
                                      (email,)).fetchone()
    if not user:
        return redirect(url_for("auth.signup"))
    from .settings import THEMES  # imported here: settings.py imports this module
    if request.method == "POST":
        theme = request.form.get("theme") if request.form.get("theme") in THEMES else "light"
        set_user_sports(user["id"], [s for s in request.form.getlist("sports") if s in SPORTS])
        get_db().execute("UPDATE users SET theme = ? WHERE id = ?", (theme, user["id"]))
        get_db().commit()
        session["theme"] = theme  # the code page already looks the way they picked
        from .sms import sms_available  # imported here: sms.py is small, but keep auth.py's imports light
        return redirect(url_for("auth.signup_texts" if sms_available() else "auth.verify"))
    chosen = [row[0] for row in get_db().execute("SELECT sport FROM user_sports WHERE user_id = ?", (user["id"],))]
    return render_template("auth/signup_sports.html", form=MultiDict([("sports", s) for s in chosen]),
                           theme=session.get("theme", "light"))


@bp.route("/signup/texts", methods=("GET", "POST"))
def signup_texts():
    """Sign-up step 3 (optional): get codes and game updates by text too. Asks for permission first.
    The number is only saved here: its code is texted once the UW email is confirmed, so texts (which cost
    money) can't be sent from made-up accounts."""
    from .phones import phone_from_form
    from .sms import sms_available
    email = session.get("pending_email")
    user = email and get_db().execute("SELECT id, phone FROM users WHERE email = ? AND verified = 0",
                                      (email,)).fetchone()
    if not user:
        return redirect(url_for("auth.signup"))
    if not sms_available():
        return redirect(url_for("auth.verify"))
    if request.method == "POST":
        raw = request.form.get("phone", "")
        # They answered here, so the "New: texts" card on Home doesn't ask again.
        get_db().execute("UPDATE users SET texts_card_done = 1 WHERE id = ?", (user["id"],))
        if not raw.strip():
            get_db().execute("UPDATE users SET phone = '' WHERE id = ?", (user["id"],))
            get_db().commit()
            return redirect(url_for("auth.verify"))  # skipped: texts stay off
        phone = phone_from_form(request.form.get("phone_country"), raw)
        if phone is None:
            flash("That doesn't look like a phone number. Try (206) 555-0142.", "error")
        elif not request.form.get("consent"):
            flash("Tick the box to say it's OK to text you (or skip this step).", "error")
        else:
            get_db().execute("UPDATE users SET phone = ?, phone_verified = 0, sms_code = NULL WHERE id = ?",
                             (phone, user["id"]))
            get_db().commit()
            return redirect(url_for("auth.verify"))
    return render_template("auth/signup_texts.html", phone=request.form.get("phone", ""),
                           country=request.form.get("phone_country"))


@bp.route("/signup/number", methods=("GET", "POST"))
@login_required
def signup_number():
    """Right after the email code: confirm the number they gave in step 3 with the code we just texted."""
    from .sms import check_phone_code
    user = g.user
    if not user["phone"] or user["phone_verified"]:
        return redirect(session.pop("after_number", None) or url_for("index"))
    if request.method == "POST":
        if request.form.get("skip"):
            flash("No problem. You can confirm your number later in Settings → Texts.", "info")
            return redirect(session.pop("after_number", None) or url_for("index"))
        problem = check_phone_code(user["id"], request.form.get("code", "").strip())
        if problem is None:
            flash("Your number is confirmed. We'll text you reminders and updates.", "success")
            return redirect(session.pop("after_number", None) or url_for("index"))
        flash(problem, "error")
    return render_template("auth/signup_number.html", phone=user["phone"])


@bp.route("/verify", methods=("GET", "POST"))
def verify():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        code = typed_code(request.form.get("code"))
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None:
            session.pop("pending_email", None)
            return redirect(url_for("auth.signup"))

        error = None
        local = email.split("@")[0]
        same_inbox = [f"{local}@{domain}" for domain in current_app.config["ALLOWED_EMAIL_DOMAINS"]]
        other = db.execute(f"SELECT email FROM users WHERE verified = 1 AND id != ? AND email IN "
                           f"({', '.join('?' for _ in same_inbox)})", (user["id"], *same_inbox)).fetchone()
        if other:  # the same inbox got verified under its other UW address meanwhile
            session.pop("pending_email", None)
            flash(f"You already have an account as {other['email']}. Log in with that email.", "error")
            return redirect(url_for("auth.login"))
        if not claim_code_try(user["id"]):
            error = "Too many wrong tries. Send yourself a new code."
        elif not user["verify_code"] or now_local() > from_db(user["verify_expires"]):
            error = "That code expired. Send yourself a new one."
        elif not same_secret(code, user["verify_code"]):
            error = "Wrong code, try again."

        if error is None:
            db.execute(
                "UPDATE users SET verified = 1, verify_code = NULL, verify_expires = NULL,"
                " verify_attempts = 0, verify_sent_at = NULL WHERE id = ?",
                (user["id"],),
            )
            from .notifications import start_markers  # imported here: notifications.py imports this module
            start_markers(user["id"])
            club_signup = session.get("club_signup")  # (log_in starts a new session)
            if club_signup:
                # No photo step and no sports: the bell reminds them, and their club comes first.
                from .notifications import notify  # imported here: notifications.py imports this module
                db.execute("UPDATE users SET photo_skipped = 1 WHERE id = ?", (user["id"],))
                notify(user["id"], "account", "Your profile can wait: add a photo and your sports when you have a minute.",
                       url_for("profile.edit"), key="tip:photo")
            db.commit()
            destination = log_in(user, just_signed_up=True)
            if club_signup:
                flash(f"You're in, {user['full_name'].split()[0]}! Now your club. Your profile can wait: "
                      "fill it in later from Profile.", "celebrate")
                return redirect(url_for("clubs.create"))
            flash(f"Welcome, {user['full_name'].split()[0]}!", "celebrate")
            if user["phone"] and not user["phone_verified"]:
                # The email is real now, so the number from step 3 gets its code.
                from .sms import sms_available, start_phone_check
                problem = start_phone_check(user["id"], user["phone"]) if sms_available() else "skip"
                if problem is None:
                    session["after_number"] = destination
                    return redirect(url_for("auth.signup_number"))
                if problem != "skip":
                    flash(f"{problem} You can add your number in Settings → Texts.", "info")
            return redirect(destination)
        flash(error, "error")
    return render_template("auth/verify.html", email=email, wait=resend_wait(email),
                           club_signup=session.get("club_signup"))


@bp.route("/verify/resend", methods=("POST",))
def resend_code():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("auth.login"))
    if code_recently_sent(email):
        flash("We just sent a code. Give it a minute.", "error")
        return redirect(url_for("auth.verify"))
    if not codes_left_today(email):
        flash(TOO_MANY_CODES, "error")
        return redirect(url_for("auth.verify"))
    if start_verification(email):  # on failure, send_verification_email already explained what happened
        flash("We sent you a new code.", "success")
    return redirect(url_for("auth.verify"))


# ------------------------------------------------------------ log in / out

def account_email(email):
    """netid@uw.edu and netid@u.washington.edu are one inbox: log in (or reset) with either, find the account."""
    db = get_db()
    if "@" not in email or db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        return email
    local = email.split("@")[0]
    other = db.execute(
        f"SELECT email FROM users WHERE verified = 1 AND email IN "
        f"({', '.join('?' for _ in current_app.config['ALLOWED_EMAIL_DOMAINS'])})",
        [f"{local}@{domain}" for domain in current_app.config["ALLOWED_EMAIL_DOMAINS"]]).fetchone()
    return other["email"] if other else email


@bp.route("/login", methods=("GET", "POST"))
def login():
    next_url = request.values.get("next", "")
    if g.user is not None:
        return redirect(safe_next(next_url))
    if next_url:
        session["after_login"] = safe_next(next_url)
    if request.method == "POST":
        email = account_email(request.form.get("email", "").strip().lower())
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        ip = request.remote_addr or ""
        if login_locked(ip, email):  # same answer whether or not the account exists
            flash("Too many wrong passwords. Try again in 15 minutes.", "error")
        elif not check_password_hash(user["password_hash"] if user else dummy_hash(), password) or user is None:
            db.execute("DELETE FROM login_failures WHERE failed_at < ?", (to_db(now_local() - LOCKOUT),))
            db.execute("INSERT INTO login_failures (ip, email, failed_at) VALUES (?, ?, ?)",
                       (ip, email[:254], to_db(now_local())))
            db.commit()
            flash("Wrong email or password.", "error")
        elif user["suspended"]:
            # They can't log in to message anyone, so give them an address that works from outside the app.
            config = current_app.config
            contact = config.get("CONTACT_EMAIL") or config.get("MAIL_FROM") or config.get("MAIL_USERNAME")
            flash("This account is suspended for breaking the rules. Think it's a mistake? "
                  + (f"Email {contact} from this address and we'll take another look." if contact
                     else "Reply to any email we've sent you and we'll take another look."), "error")
        elif not user["verified"]:
            if code_recently_sent(email):
                session["pending_email"] = email
                flash("Check your email for the code we sent you.", "info")
            elif start_verification(email):
                flash("Check your email. We sent you a new code.", "info")
            elif not codes_left_today(email):
                flash(TOO_MANY_CODES, "error")
            return redirect(url_for("auth.verify"))
        else:
            db.execute("DELETE FROM login_failures WHERE ip = ? AND email = ?", (ip, email))
            return redirect(log_in(user, remember=request.form.get("remember") == "1"))
    return render_template("auth/login.html", next_url=next_url,
                           email=request.form.get("email", "").strip()[:254])


def login_locked(ip, email):
    """Too many wrong passwords from this device address: for this account, or for any accounts at all.
    Only that address waits; the account owner can still log in from their own phone."""
    since = to_db(now_local() - LOCKOUT)
    db = get_db()
    for_account = db.execute("SELECT COUNT(*) FROM login_failures WHERE ip = ? AND email = ? AND failed_at >= ?",
                             (ip, email, since)).fetchone()[0]
    overall = db.execute("SELECT COUNT(*) FROM login_failures WHERE ip = ? AND failed_at >= ?",
                         (ip, since)).fetchone()[0]
    return for_account >= MAX_FAILED_LOGINS or overall >= MAX_FAILED_LOGINS_PER_IP


# --------------------------------------------------------- forgot password

@bp.route("/forgot", methods=("GET", "POST"))
def forgot_password():
    """Step 1: email a 6-digit code. The answer is the same whether or not the account exists,
    so nobody can use this page to find out who has an account."""
    if g.user is not None:  # a reset logs in as that account: logged in, change it in Settings instead
        return redirect(url_for("settings.password"))
    if request.method == "POST":
        email = account_email(request.form.get("email", "").strip().lower())
        user = get_db().execute("SELECT verified, suspended FROM users WHERE email = ?", (email,)).fetchone()
        if user and user["verified"] and not user["suspended"] and not code_recently_sent(email) \
                and codes_left_today(email):  # (same answer either way: the page never says which)
            start_verification(email, session_key="reset_email")
            from .sms import text_code
            row = get_db().execute("SELECT id, verify_code FROM users WHERE email = ?", (email,)).fetchone()
            text_code(row["id"], row["verify_code"], "password reset")
        session["reset_email"] = email
        session.pop("reset_tries", None)
        flash("If that email has an account, we sent it a 6-digit code (and texted it, if you added a phone).",
              "info")
        return redirect(url_for("auth.reset_password"))
    return render_template("auth/forgot.html")


@bp.route("/reset", methods=("GET", "POST"))
def reset_password():
    """Step 2: the code plus a new password."""
    email = session.get("reset_email")
    if not email:
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        code = typed_code(request.form.get("code"))
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ? AND verified = 1", (email,)).fetchone()
        error = None
        # Every answer here must look the same whether or not the email has an account (see forgot_password):
        # no account = a code that is always wrong, with the same limit on tries.
        if user is not None and user["suspended"]:
            user = None  # same answer as no account: a suspended account can't reset its way back in
        if user is None or not user["verify_code"]:
            session["reset_tries"] = session.get("reset_tries", 0) + 1
            error = ("Too many wrong tries. Ask for a new code." if session["reset_tries"] > MAX_CODE_ATTEMPTS
                     else "Wrong code, try again.")
        elif not claim_code_try(user["id"]):
            error = "Too many wrong tries. Ask for a new code."
        elif not same_secret(code, user["verify_code"]):
            error = "Wrong code, try again."
        elif now_local() > from_db(user["verify_expires"]):  # only said to someone who knows the code
            error = "That code expired. Ask for a new one."
        else:
            error = password_problem(password, request.form.get("password2", ""))
        if error is None:
            db.execute("UPDATE users SET password_hash = ?, verify_code = NULL, verify_expires = NULL,"
                       " verify_attempts = 0 WHERE id = ?", (hash_password(password), user["id"]))
            end_other_sessions(user["id"])  # whoever knew the old password is logged out too
            db.commit()
            destination = log_in(user)
            flash("Password changed. You're logged in.", "success")
            return redirect(destination)
        flash(error, "error")
    return render_template("auth/reset.html", email=email)


def hash_password(password):
    return generate_password_hash(password, current_app.config["PASSWORD_HASH_METHOD"])


def check_current_password(user, password):
    """For pages that ask for your password again (change password, delete account). Wrong guesses count
    toward the same lock as the login page, so a borrowed logged-in phone can't be used to guess it.
    Returns None if the password is right, "" if it's wrong, or a message if there were too many tries."""
    db = get_db()
    row = db.execute("SELECT password_hash, failed_logins, locked_until FROM users WHERE id = ?",
                     (user["id"],)).fetchone()
    if row["locked_until"] and now_local() < from_db(row["locked_until"]):
        return "Too many wrong passwords. Try again in 15 minutes."
    if check_password_hash(row["password_hash"], password):
        if row["failed_logins"]:
            db.execute("UPDATE users SET failed_logins = 0 WHERE id = ?", (user["id"],))
            db.commit()
        return None
    failed = row["failed_logins"] + 1
    locked = to_db(now_local() + LOCKOUT) if failed >= MAX_FAILED_LOGINS else None
    db.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
               (0 if locked else failed, locked, user["id"]))
    db.commit()
    return ""


def dummy_hash():
    """A hash to check wrong logins against when the email has no account, so the answer takes as long as
    for a real account (otherwise the response time tells who has one)."""
    method = current_app.config["PASSWORD_HASH_METHOD"]
    if _dummy_hashes.get(method) is None:
        _dummy_hashes[method] = generate_password_hash(secrets.token_urlsafe(16), method)
    return _dummy_hashes[method]


_dummy_hashes = {}


def password_problem(password, password2):
    """The error message for a new password, or None if it's fine."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password can be at most {MAX_PASSWORD_LENGTH} characters."
    if not password.strip():
        return "Password can't be only spaces."
    if password != password2:
        return "Passwords do not match."
    return None


@bp.route("/logout", methods=("POST",))
def logout():
    if session.get("sid"):
        db = get_db()
        db.execute("DELETE FROM ended_sessions WHERE ended_at < ?",  # older ones have expired anyway
                   (to_db(now_local() - current_app.permanent_session_lifetime),))
        db.execute("INSERT OR IGNORE INTO ended_sessions (sid, ended_at) VALUES (?, ?)",
                   (session["sid"], to_db(now_local())))
        db.commit()
    session.clear()
    return redirect(url_for("index"))
