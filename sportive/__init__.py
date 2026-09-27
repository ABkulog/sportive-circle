"""Sportive Circle @ UW: bring Huskies together through sports."""
import os
from datetime import timedelta

from flask import Flask, g, redirect, render_template, url_for

from . import auth, clubs, db, events, moderation, news, profile, ranks, reminders, social, stats
from .photos import MAX_UPLOAD_MB
from .constants import LOCATIONS, SKILL_LEVELS, SPORT_EMOJI, SPORT_LOCATIONS, SPORT_MAX_PLAYERS, SPORTS
from .timeutil import fmt_clock, fmt_relative, fmt_when, same_day


DEV_SECRET_KEY = "dev-only-change-me"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", DEV_SECRET_KEY),
        DATABASE=os.path.join(app.instance_path, "sportive_circle.db"),
        # UW email addresses: @uw.edu is standard; older accounts may still use @u.washington.edu.
        ALLOWED_EMAIL_DOMAINS=("uw.edu", "u.washington.edu"),
        CSRF_ENABLED=True,
        # PBKDF2 works on every Python build (scrypt is missing on macOS's system Python).
        PASSWORD_HASH_METHOD="pbkdf2:sha256:600000",
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024,  # biggest photo upload
        # Email (verification codes). Without MAIL_SERVER, dev mode shows the code on screen.
        MAIL_SERVER=os.environ.get("MAIL_SERVER"),
        MAIL_PORT=int(os.environ.get("MAIL_PORT", 587)),
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME"),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD"),
        # The site's public address, used for links in emails.
        PUBLIC_URL=os.environ.get("PUBLIC_URL", "http://localhost:5050"),
        # Who can see and handle reports (comma-separated emails), e.g. "you@uw.edu".
        ADMIN_EMAILS=os.environ.get("ADMIN_EMAILS", ""),
        MAIL_FROM=os.environ.get("MAIL_FROM"),  # defaults to MAIL_USERNAME (never a domain we don't own)
    )
    if test_config:
        app.config.update(test_config)
    if app.config["SECRET_KEY"] == DEV_SECRET_KEY and not (app.debug or app.testing):
        # Anyone who knows the key can forge a login cookie, so never run publicly with this one.
        raise RuntimeError("Set the SECRET_KEY environment variable before running in production.")
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(auth.bp)
    app.register_blueprint(events.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(social.bp)
    app.register_blueprint(news.bp)
    app.register_blueprint(clubs.bp)
    app.register_blueprint(moderation.bp)
    app.cli.add_command(reminders.send_reminders_command)
    app.cli.add_command(stats.sport_stats_command)
    app.add_url_rule("/", endpoint="index", view_func=events.feed)
    app.add_url_rule("/how-it-works", endpoint="how_it_works",
                     view_func=lambda: render_template("how_it_works.html"))
    app.add_url_rule("/create", endpoint="create_menu", view_func=auth.login_required(
        lambda: render_template("create.html", officer_clubs=clubs.officer_clubs(g.user["id"]))))
    # Browsers ask for /favicon.ico on their own; point them at the real icon.
    app.add_url_rule("/favicon.ico", endpoint="favicon",
                     view_func=lambda: redirect(url_for("static", filename="icon.svg")))
    # iPhones ask for these when someone adds the site to their home screen.
    for path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
        app.add_url_rule(path, endpoint=f"touch_icon_{path.strip('/').replace('-', '_').replace('.', '_')}",
                         view_func=lambda: redirect(url_for("static", filename="apple-touch-icon.png")))

    app.jinja_env.globals.update(
        csrf_field=auth.csrf_field, SPORTS=SPORTS, SPORT_EMOJI=SPORT_EMOJI,
        LOCATIONS=LOCATIONS, SKILL_LEVELS=SKILL_LEVELS,
        SPORT_RULES={key: {"label": label, "locations": SPORT_LOCATIONS[key], "max": SPORT_MAX_PLAYERS[key]}
                     for key, label in SPORTS.items()}, spots_left=events.spots_left, event_title=events.event_title, can_join_level=ranks.can_join_level, can_join_or_tryout=events.can_join_or_tryout, my_tier_map=ranks.my_tier_map, social_counts=social.counts, is_admin=moderation.is_admin, open_report_count=moderation.open_report_count, pending_club_count=clubs.pending_club_count, chat_unread=social.event_chat_unread,
        LEVEL_TIERS={level: ranks.TIERS.index(tier) for level, tier in ranks.LEVEL_REQUIREMENT.items()}, place_map=events.place_map, same_day=same_day,
    )
    for code, message in ERRORS.items():
        app.register_error_handler(code, _error_page(code, message))

    app.jinja_env.filters.update(when=fmt_when, clock=fmt_clock, relative=fmt_relative)
    return app


ERRORS = {
    400: "Something was wrong with that request. Go back, refresh the page and try again.",
    403: "That's not yours to change. Only the host can do that.",
    404: "This Dawg got lost. 🐾 The link might be broken, or the event was removed.",
    413: f"That photo is too big. Pick one under {MAX_UPLOAD_MB} MB.",
}


def _error_page(code, message):
    def handler(error):
        return render_template("error.html", code=code, message=message), code
    return handler
