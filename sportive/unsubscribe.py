"""One-click unsubscribe for the optional emails (the Monday email, "Maya posted a game", reminders).

Every such email carries a link (and the List-Unsubscribe headers Gmail and Yahoo ask bulk senders for) that turns
that one kind off without logging in: the link itself, signed with the app's secret, says whose and which.
Emails about your account or a game you're in that changed or was canceled aren't optional and have no link.
"""
from flask import Blueprint, abort, current_app, render_template, request
from itsdangerous import BadSignature, URLSafeSerializer

from .db import get_db

bp = Blueprint("unsubscribe", __name__)

# kind -> (users column, what it's called in Settings)
KINDS = {
    "digest": ("weekly_digest", "the Monday email of games (and news about Sportive Circle)"),
    "friend_games": ("email_friend_games", "emails when friends or your clubs post a game"),
    "reminders": ("email_reminders", "game reminder emails"),
}


def _signer():
    return URLSafeSerializer(current_app.secret_key, salt="unsubscribe")


def unsubscribe_url(email, kind):
    """The no-login link that turns off `kind` emails for this address."""
    # Built by hand, not with url_for: reminders are sent by the background loop, outside any request.
    return f"{current_app.config['PUBLIC_URL'].rstrip('/')}/unsubscribe/{_signer().dumps([email.lower(), kind])}"


def _read(token):
    try:
        email, kind = _signer().loads(token)
    except (BadSignature, ValueError, TypeError):
        abort(404)
    if kind not in KINDS:
        abort(404)
    return email, kind


@bp.route("/unsubscribe/<token>", methods=("GET", "POST"))
def one_click(token):
    """GET shows a button (a link preview or a mail scanner opening it changes nothing); POST turns it off.
    Mail apps' own "Unsubscribe" button POSTs here directly (List-Unsubscribe-Post), with no form token."""
    email, kind = _read(token)
    column, label = KINDS[kind]
    done = False
    if request.method == "POST":
        db = get_db()
        db.execute(f"UPDATE users SET {column} = 0 WHERE LOWER(email) = ?", (email,))  # column from KINDS only
        db.commit()
        done = True
    return render_template("settings/unsubscribe.html", label=label, done=done, token=token)
