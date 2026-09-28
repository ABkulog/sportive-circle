"""Sportive Circle @ UW: bring Huskies together through sports."""
import logging
import os
from datetime import timedelta

from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from . import (auth, clubs, db, events, feedback, mail, moderation, news, notifications, pages, profile, ranks,
               reminders, social, stats)
from .constants import (LOCATIONS, PLACE_TIPS, SKILL_LEVELS, SPORT_EMOJI, SPORT_LOCATIONS, SPORT_MAX_PLAYERS,
                        SPORTS)
from .photos import MAX_UPLOAD_MB
from .timeutil import fmt_clock, fmt_relative, fmt_when, same_day

DEV_SECRET_KEY = "dev-only-change-me"

# Where the browser may load things from. Scripts only come from our own files and the one map
# library on cdnjs, so even if someone sneaks HTML into a name or message, it can't run code.
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdnjs.cloudflare.com",
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https://tile.openstreetmap.org https://cdnjs.cloudflare.com",
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
    # PUBLIC_URL wins; on Render, RENDER_EXTERNAL_URL (e.g. https://sportive-circle.onrender.com) is set for us.
    public_url = os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "http://localhost:5050"
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", DEV_SECRET_KEY),
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
    )
    if test_config:
        app.config.update(test_config)
    if app.config["SECRET_KEY"] == DEV_SECRET_KEY and not (app.debug or app.testing):
        # Anyone who knows the key can forge a login cookie, so never run publicly with this one.
        raise RuntimeError("Set the SECRET_KEY environment variable before running in production.")
    if os.environ.get("BEHIND_PROXY") == "1":
        # Hosting services put a proxy in front of the app; trust its "real address / https" headers.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    os.makedirs(app.instance_path, exist_ok=True)
    logging.basicConfig(level=logging.INFO)

    db.init_app(app)
    for blueprint in (auth.bp, events.bp, profile.bp, social.bp, news.bp, clubs.bp, moderation.bp, notifications.bp,
                      reminders.bp, feedback.bp):
        app.register_blueprint(blueprint)
    pages.register(app)
    app.add_url_rule("/", endpoint="index", view_func=events.feed)
    app.cli.add_command(reminders.send_reminders_command)
    app.cli.add_command(stats.sport_stats_command)
    app.cli.add_command(mail.check_email_command)

    _add_template_helpers(app)
    for code, message in ERRORS.items():
        app.register_error_handler(code, _error_page(code, message))
    # A number too big for the database (e.g. /events/99999999999999999999) can't be a real page.
    app.register_error_handler(OverflowError, _error_page(404, ERRORS[404]))
    app.after_request(_security_headers)
    return app


def _add_template_helpers(app):
    app.jinja_env.globals.update(
        # forms and lists
        csrf_field=auth.csrf_field, SPORTS=SPORTS, SPORT_EMOJI=SPORT_EMOJI, LOCATIONS=LOCATIONS,
        SKILL_LEVELS=SKILL_LEVELS,
        SPORT_RULES={key: {"label": label, "locations": SPORT_LOCATIONS[key], "max": SPORT_MAX_PLAYERS[key],
                           "tips": {place: tip for (sport, place), tip in PLACE_TIPS.items() if sport == key}}
                     for key, label in SPORTS.items()},
        place_tip=lambda sport, place: PLACE_TIPS.get((sport, place)),
        LEVEL_TIERS={level: ranks.TIERS.index(tier) for level, tier in ranks.LEVEL_REQUIREMENT.items()},
        # events
        spots_left=events.spots_left, event_title=events.event_title, can_join_or_tryout=events.can_join_or_tryout,
        place_map=events.place_map, same_day=same_day,
        # ranks
        can_join_level=ranks.can_join_level, my_tier_map=ranks.my_tier_map,
        # menu counters
        tab_badges=notifications.tab_badges, badge_text=notifications.badge_text,
        chat_unread=social.event_chat_unread, is_admin=moderation.is_admin,
        open_report_count=moderation.open_report_count, pending_club_count=clubs.pending_club_count,
        is_team=moderation.is_team, new_suggestion_count=feedback.new_suggestion_count,
    )
    app.jinja_env.filters.update(when=fmt_when, clock=fmt_clock, relative=fmt_relative)


def _security_headers(response):
    headers = response.headers
    headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # Only our own pages may ask for your location ("Where am I?"); never the camera or microphone.
    headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
    if response.mimetype == "text/html":
        headers.setdefault("Cache-Control", "no-store")  # pages show private info; don't keep copies
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
        return render_template("error.html", code=code, message=message), code
    return handler
