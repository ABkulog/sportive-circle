"""Sportive Circle @ UW: bring Huskies together through sports."""
import logging
import os
import secrets
from datetime import timedelta

from flask import Flask, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from . import (auth, backups, digest, textutil, uwrec, clubs, db, events, feedback, mail, moderation, notifications, pages, parties, placecheck, placehours, profile,
               phones, reminders, settings, sms, social, stats, unsubscribe)
from .constants import (SPORT_SPACE, DEFAULT_PLAYERS, LOCATIONS, OPEN_TO, OPEN_TO_BADGE, OPEN_TO_LABELS, PLACE_TIPS, SKILL_LEVELS, CLUB_LEVELS, SPORT_EMOJI, SPORT_LOCATIONS,
                        MAX_PLAYERS, SPORT_TEAM_SIZES, SPORTS)
from .photos import MAX_UPLOAD_MB
from .timeutil import fmt_ago, fmt_clock, fmt_full, fmt_relative, fmt_when, now_local, same_day, to_db

DEV_SECRET_KEY = "dev-only-change-me"  # the old shared default: refused everywhere now
MIN_SECRET_KEY_LENGTH = 32
HSTS_MAX_AGE_SECONDS = 365 * 24 * 60 * 60
SITE_URL = "https://sportivecircle.com"  # the real address (Render also answers at *.onrender.com)

# Where the browser may load things from. Scripts only come from our own files and the one map
# library on cdnjs, so even if someone sneaks HTML into a name or message, it can't run code.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/",  # only the map library's folder
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/ https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https://tile.openstreetmap.org https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
])


def _setting(name):
    """An environment setting without stray spaces or line breaks (easy to paste by accident into a
    hosting dashboard, and enough to make an email login fail). Empty means not set."""
    return (os.environ.get(name) or "").strip() or None


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    # PUBLIC_URL wins; on Render (which sets RENDER_EXTERNAL_URL) it's our own domain, never the onrender.com one.
    public_url = (_setting("PUBLIC_URL") or (SITE_URL if os.environ.get("RENDER_EXTERNAL_URL") else None)
                  or "http://localhost:5050")
    app.config.from_mapping(
        SECRET_KEY=_setting("SECRET_KEY"),
        DATABASE=os.environ.get("DATABASE", os.path.join(app.instance_path, "sportive_circle.db")),
        # UW email addresses: @uw.edu is standard; older accounts may still use @u.washington.edu.
        ALLOWED_EMAIL_DOMAINS=("uw.edu", "u.washington.edu"),
        CSRF_ENABLED=True,
        # PBKDF2 works on every Python build (scrypt is missing on macOS's system Python).
        PASSWORD_HASH_METHOD="pbkdf2:sha256:600000",
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=public_url.startswith("https://"),  # login cookie only travels over HTTPS
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024,  # biggest photo upload
        # Email (codes, reminders). Without MAIL_SERVER, dev mode shows the code on screen.
        MAIL_SERVER=_setting("MAIL_SERVER"),
        MAIL_PORT=int(os.environ.get("MAIL_PORT", 587)),
        MAIL_USERNAME=_setting("MAIL_USERNAME"),
        MAIL_PASSWORD=_setting("MAIL_PASSWORD"),
        MAIL_FROM=_setting("MAIL_FROM"),  # defaults to MAIL_USERNAME (never a domain we don't own)
        # The site's public address, used for links in emails, calendar files and share buttons.
        PUBLIC_URL=public_url,
        # Who can review reports and club registrations (comma-separated emails), e.g. "you@uw.edu".
        ADMIN_EMAILS=os.environ.get("ADMIN_EMAILS", ""),
        # Where people send privacy questions and appeals (shown on the Privacy and Terms pages).
        CONTACT_EMAIL=os.environ.get("CONTACT_EMAIL", ""),
        # Secret the scheduler sends to /tasks/send-reminders (unset = that page doesn't exist).
        TASK_TOKEN=os.environ.get("TASK_TOKEN"),
        # Texts (optional, see sms.py). Without these, the text option is hidden on the live site.
        TWILIO_ACCOUNT_SID=_setting("TWILIO_ACCOUNT_SID"),
        TWILIO_AUTH_TOKEN=_setting("TWILIO_AUTH_TOKEN"),
        TWILIO_FROM=_setting("TWILIO_FROM"),
        # Send game reminders from inside the app (on by default on Render; REMINDER_LOOP=0 turns it off).
        REMINDER_LOOP=(_setting("REMINDER_LOOP") or ("1" if os.environ.get("RENDER_EXTERNAL_URL") else "0")) == "1",
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)
    _check_secret_key(app)
    if os.environ.get("BEHIND_PROXY") == "1":
        # Hosting services put a proxy in front of the app; trust its "real address / https" headers.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    logging.basicConfig(level=logging.INFO)

    db.init_app(app)
    sms.init_app(app)
    for blueprint in (auth.bp, events.bp, parties.bp, profile.bp, settings.bp, social.bp, clubs.bp, moderation.bp,
                      notifications.bp, reminders.bp, feedback.bp, placecheck.bp, unsubscribe.bp):
        app.register_blueprint(blueprint)
    pages.register(app)
    app.add_url_rule("/", endpoint="index", view_func=events.feed)
    app.cli.add_command(reminders.send_reminders_command)
    app.cli.add_command(backups.backup_command)
    app.cli.add_command(uwrec.sync_uw_rec_command)
    app.cli.add_command(digest.send_weekly_command)
    app.cli.add_command(stats.sport_stats_command)
    app.cli.add_command(mail.check_email_command)

    _add_template_helpers(app)
    _version_static_files(app)
    for code, message in ERRORS.items():
        app.register_error_handler(code, _error_page(code, message))
    # A number too big for the database (e.g. /events/99999999999999999999) can't be a real page.
    app.register_error_handler(OverflowError, _error_page(404, ERRORS[404]))
    app.after_request(_security_headers)
    if app.config["REMINDER_LOOP"] and not app.testing:
        reminders.start_reminder_loop(app)
    return app


def _check_secret_key(app):
    """Anyone who knows the key can forge a login cookie for any account. Production needs a long random
    SECRET_KEY; local development gets its own random key, kept in instance/ so logins survive restarts."""
    key = app.config.get("SECRET_KEY")
    if app.testing:
        app.config["SECRET_KEY"] = key or secrets.token_urlsafe(48)
        return
    if not key and app.debug:
        path = os.path.join(app.instance_path, "dev_secret_key")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as file:
                file.write(secrets.token_urlsafe(48))
        with open(path, encoding="utf-8") as file:
            app.config["SECRET_KEY"] = file.read().strip()
        return
    if not key or key == DEV_SECRET_KEY:
        raise RuntimeError("Set the SECRET_KEY environment variable before running in production.")
    if len(key) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(f"SECRET_KEY is too short: use at least {MIN_SECRET_KEY_LENGTH} random characters "
                           "(e.g. python -c \"import secrets; print(secrets.token_urlsafe(48))\").")


def _add_template_helpers(app):
    app.jinja_env.globals.update(
        # forms and lists
        csrf_field=auth.csrf_field, SPORTS=SPORTS, SPORT_EMOJI=SPORT_EMOJI, SPORT_SPACE=SPORT_SPACE, LOCATIONS=LOCATIONS,
        SKILL_LEVELS=SKILL_LEVELS, CLUB_LEVELS=CLUB_LEVELS,
        SPORT_TEAM_SIZES=SPORT_TEAM_SIZES, MAX_PLAYERS=MAX_PLAYERS, DEFAULT_PLAYERS=DEFAULT_PLAYERS,
        SPORT_RULES={key: {"label": label, "locations": SPORT_LOCATIONS[key],
                           "teams": SPORT_TEAM_SIZES.get(key, []), "default": DEFAULT_PLAYERS.get(key, 10),
                           "space": SPORT_SPACE.get(key, "place"),
                           "tips": {place: tip for (sport, place), tip in PLACE_TIPS.items() if sport == key}}
                     for key, label in SPORTS.items()},
        place_tip=lambda sport, place: PLACE_TIPS.get((sport, place)),
        place_hours=placehours.hours_for_page,
        whats_on=placecheck.whats_on,
        # events
        spots_left=events.spots_left, event_title=events.event_title, place_map=events.place_map, same_day=same_day,
        can_quick_join=events.can_quick_join, can_party_up=parties.can_party_up,
        can_send_to_friends=parties.can_send_to_friends, join_confirm=events.join_confirm,
        invite_link=parties.invite_link,
        OPEN_TO=OPEN_TO, OPEN_TO_LABELS=OPEN_TO_LABELS, OPEN_TO_BADGE=OPEN_TO_BADGE,
        OPEN_SPOT_CHOICES=events.OPEN_SPOT_CHOICES, now_db=lambda: to_db(now_local()),
        # menu counters
        tab_badges=notifications.tab_badges, notice_counts=notifications.counts, badge_text=notifications.badge_text, bell_count=notifications.bell_count,
        chat_unread=social.event_chat_unread, is_admin=moderation.is_admin,
        open_report_count=moderation.open_report_count, pending_club_count=clubs.pending_club_count,
        is_team=moderation.is_team, current_theme=settings.current_theme, sms_available=lambda: sms.sms_available(),
        pretty_phone=sms.pretty_phone, masked_phone=sms.masked_phone, SMS_CONSENT=sms.CONSENT,
        PHONE_COUNTRIES=phones.COUNTRIES, split_phone=phones.split_phone, phone_for_admins=phones.pretty_phone,
    )
    app.jinja_env.filters.update(when=fmt_when, clock=fmt_clock, relative=fmt_relative, ago=fmt_ago, full=fmt_full,
                                 initial=textutil.initial)


def _version_static_files(app):
    """Links to our CSS and JS end in ?v=<when the file changed>, so phones (Safari keeps old copies
    for a long time) load the new version right after an update instead of showing yesterday's look."""
    versions = {}

    @app.url_defaults
    def add_version(endpoint, values):
        if endpoint == "static" and "filename" in values and "v" not in values:
            name = values["filename"]
            if name not in versions:
                path = os.path.join(app.static_folder, name)
                versions[name] = int(os.path.getmtime(path)) if os.path.isfile(path) else None
            if versions[name]:
                values["v"] = versions[name]


def _security_headers(response):
    headers = response.headers
    headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # Only our own pages may ask for your location ("Where am I?"); never the camera or microphone.
    headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
    if request.is_secure:
        # Browsers only honor this over HTTPS; after that they refuse plain http:// for a year.
        headers.setdefault("Strict-Transport-Security", f"max-age={HSTS_MAX_AGE_SECONDS}; includeSubDomains")
    if request.endpoint not in ("static", "favicon", "touch_icon", "touch_icon_precomposed"):
        # Pages, chat updates, rosters and calendar files show private info; don't keep copies.
        headers.setdefault("Cache-Control", "no-store")
    elif request.endpoint == "static" and request.args.get("v") and response.status_code == 200:
        # ?v= changes whenever the file does (_version_static_files), so phones can keep it for a year.
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


ERRORS = {
    400: "Something was wrong with that request. Go back, refresh the page and try again.",
    403: "You don't have permission to do that.",
    404: "This Dawg got lost. 🐾 The link might be broken, or the page was removed.",
    405: "That page can't be opened that way. Go back and use the buttons on the page.",
    413: f"That photo is too big. Pick one under {MAX_UPLOAD_MB} MB.",
    500: "Something broke on our side. It's not you. Try again in a minute.",
}


def _error_page(code, message):
    def handler(error):
        # abort(400, "Your form expired...") explains itself; Werkzeug's stock English text doesn't.
        custom = getattr(error, "description", None)
        if code < 500 and custom and custom != getattr(type(error), "description", None):
            return render_template("error.html", code=code, message=custom), code
        return render_template("error.html", code=code, message=message), code
    return handler
