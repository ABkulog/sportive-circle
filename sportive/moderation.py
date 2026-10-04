"""Reporting people and messages, and the admin page for reviewing reports.

Students can report a profile, a direct message sent to them, or a message in an event
chat they're part of. The reported person is never told who reported them. Admins (the
emails in the ADMIN_EMAILS setting) review reports on /admin/reports.
"""
import functools
from datetime import timedelta

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from markupsafe import Markup

from .auth import login_required
from .db import get_db
from .social import block_user
from .timeutil import now_local, to_db

bp = Blueprint("moderation", __name__)

REASONS = {
    "harassment": "Harassment or bullying",
    "spam": "Spam or scams",
    "hate": "Hate speech or discrimination",
    "threats": "Threats or violence",
    "sexual": "Sexual or inappropriate content",
    "fake": "Fake account or pretending to be someone",
    "other": "Something else",
}
MAX_DETAILS = 1000
MAX_REPORTS_PER_HOUR = 10  # stops people from spamming reports
REPORTS_PER_PAGE = 100
FLAG_THRESHOLD = 3         # reported by this many different people = flagged for admins


def admin_emails():
    """The emails in the ADMIN_EMAILS setting (lowercase)."""
    return {email.strip().lower() for email in current_app.config["ADMIN_EMAILS"].split(",") if email.strip()}


def is_admin(user=None):
    user = user if user is not None else g.get("user")
    if user is None:
        return False
    return user["email"].lower() in admin_emails()


def team_ids():
    """User ids of the people who run Sportive Circle (the admins), for the 🐾 Team label. Once per page."""
    if "team_ids" not in g:
        emails = sorted(admin_emails())
        g.team_ids = {row["id"] for row in get_db().execute(
            f"SELECT id FROM users WHERE LOWER(email) IN ({', '.join('?' for _ in emails)})", emails)} if emails else set()
    return g.team_ids


def is_team(user_id):
    return user_id in team_ids()



def _snapshot(message):
    """What admins see of a reported message: its words, and that it had a photo (a photo-only message
    would otherwise leave nothing to review)."""
    photo = "📷 [sent a photo]" if message["photo_id"] else ""
    return "\n".join(part for part in (message["body"], photo) if part)

def resolve_target(target_type, target_id):
    """Who's being reported, a copy of what they said, and where to go back to.

    Only things the reporter can actually see can be reported.
    """
    db = get_db()
    me = g.user["id"]
    if target_type == "user":
        user = db.execute("SELECT id, full_name FROM users WHERE id = ? AND verified = 1 AND suspended = 0",
                          (target_id,)).fetchone()
        if user is None or user["id"] == me:
            abort(404)
        return {"user_id": user["id"], "name": user["full_name"], "snapshot": "",
                "what": f"{user['full_name']}'s profile", "back": url_for("profile.view", user_id=user["id"])}
    if target_type == "dm":
        message = db.execute(
            """SELECT m.*, u.full_name FROM direct_messages m JOIN users u ON u.id = m.sender_id
               WHERE m.id = ? AND m.recipient_id = ?""", (target_id, me)).fetchone()  # only messages sent TO you
        if message is None:
            abort(404)
        return {"user_id": message["sender_id"], "name": message["full_name"], "snapshot": _snapshot(message),
                "what": f"a message from {message['full_name']}",
                "back": url_for("social.thread", user_id=message["sender_id"])}
    if target_type == "event_message":
        message = db.execute(
            """SELECT m.*, u.full_name FROM event_messages m JOIN users u ON u.id = m.sender_id
               WHERE m.id = ? AND m.sender_id != ?
                 AND EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = m.event_id AND r.user_id = ?)""",
            (target_id, me, me)).fetchone()  # only chats you're in, and not your own messages
        if message is None:
            abort(404)
        return {"user_id": message["sender_id"], "name": message["full_name"], "snapshot": _snapshot(message),
                "what": f"a group chat message from {message['full_name']}",
                "back": url_for("social.event_chat", event_id=message["event_id"])}
    abort(404)


@bp.route("/report/<target_type>/<int:target_id>", methods=("GET", "POST"))
@login_required
def report(target_type, target_id):
    target = resolve_target(target_type, target_id)
    if request.method == "POST":
        reason = request.form.get("reason", "")
        details = request.form.get("details", "").strip()
        db = get_db()
        me = g.user["id"]
        recent = db.execute("SELECT COUNT(*) FROM reports WHERE reporter_id = ? AND created_at >= ?",
                            (me, to_db(now_local() - timedelta(hours=1)))).fetchone()[0]
        if reason not in REASONS:
            flash("Please choose what's wrong.", "error")
        elif len(details) > MAX_DETAILS:
            flash(f"Please keep the details under {MAX_DETAILS} characters.", "error")
        elif recent >= MAX_REPORTS_PER_HOUR:
            flash("You've sent a lot of reports in the last hour. Please try again later.", "error")
        else:
            already = db.execute(
                "SELECT 1 FROM reports WHERE reporter_id = ? AND target_type = ? AND target_id = ? AND status = 'open'",
                (me, target_type, target_id)).fetchone()
            if not already:
                db.execute(
                    """INSERT INTO reports (reporter_id, reported_user_id, target_type, target_id, reason, details,
                                            snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (me, target["user_id"], target_type, target_id, reason, details, target["snapshot"],
                     to_db(now_local())))
            if request.form.get("block"):
                block_user(me, target["user_id"])
            db.commit()
            flash("Thanks. We'll look into it, and they won't know it was you."
                  + (" You've also blocked them." if request.form.get("block") else ""), "info")
            return redirect(target["back"])
    return render_template("moderation/report.html", target=target, target_type=target_type,
                           target_id=target_id, reasons=REASONS)


# ------------------------------------------------------------------- admins

def admin_required(view):
    @functools.wraps(view)
    @login_required
    def wrapped(**kwargs):
        if not is_admin():
            abort(404)  # pretend the page doesn't exist
        return view(**kwargs)
    return wrapped


@bp.route("/admin")
@admin_required
def admin_home():
    """One place for everything admins look after (the Admin tab and the shield icon open it)."""
    from .timeutil import now_local, to_db
    upcoming = get_db().execute("SELECT COUNT(*) FROM rec_reservations WHERE ends_at >= ?",
                                (to_db(now_local()),)).fetchone()[0]
    return render_template("moderation/home.html", upcoming_rec=upcoming)


@bp.route("/admin/reports")
@admin_required
def admin_reports():
    status = request.args.get("status", "open")
    if status not in ("open", "reviewed", "dismissed", "suspended"):
        status = "open"
    db = get_db()
    suspended = db.execute("SELECT id, full_name, email FROM users WHERE suspended = 1 ORDER BY fold(full_name)").fetchall()
    page = min(max(1, request.args.get("page", 1, type=int) or 1), 10000)  # a huge number would overflow SQLite
    total = db.execute("SELECT COUNT(*) FROM reports WHERE status = ?", (status,)).fetchone()[0]
    page = min(page, max(1, -(-total // REPORTS_PER_PAGE)))  # past the end (the last one there was handled): last page
    reports = db.execute(
        """SELECT r.*, reporter.full_name AS reporter_name, reported.full_name AS reported_name,
                  reported.email AS reported_email, reported.suspended AS reported_suspended
           FROM reports r
           LEFT JOIN users reporter ON reporter.id = r.reporter_id
           LEFT JOIN users reported ON reported.id = r.reported_user_id
           WHERE r.status = ? ORDER BY CASE WHEN r.status = 'open' THEN r.id ELSE -r.id END LIMIT ? OFFSET ?""",
        (status, REPORTS_PER_PAGE, (page - 1) * REPORTS_PER_PAGE)).fetchall()  # open: oldest first; done: newest first
    flagged = db.execute(
        """SELECT u.id, u.full_name, u.email, u.suspended, COUNT(DISTINCT r.reporter_id) AS reporters
           FROM reports r JOIN users u ON u.id = r.reported_user_id
           WHERE r.status = 'open' GROUP BY u.id HAVING reporters >= ? ORDER BY reporters DESC""",
        (FLAG_THRESHOLD,)).fetchall()
    report_counts = {row["status"]: row["n"] for row in db.execute(
        "SELECT status, COUNT(*) AS n FROM reports GROUP BY status")}
    return render_template("moderation/admin.html", reports=reports, flagged=flagged, status=status,
                           report_counts=report_counts, reasons=REASONS, suspended=suspended,
                           page=page, per_page=REPORTS_PER_PAGE)


@bp.route("/admin/reports/<int:report_id>/<action>", methods=("POST",))
@admin_required
def resolve(report_id, action):
    if action not in ("reviewed", "dismissed", "open"):
        abort(404)
    db = get_db()
    seen = request.args.get("from", "open")  # the tab the admin was looking at: only if nobody changed it since
    if not db.execute("UPDATE reports SET status = ?, reviewed_at = ? WHERE id = ? AND status = ?",
                      (action, to_db(now_local()) if action != "open" else None, report_id, seen)).rowcount:
        flash("Another admin already handled that report.", "info")
    db.commit()
    page = min(max(1, request.args.get("page", 1, type=int) or 1), 10000)
    return redirect(url_for("moderation.admin_reports", status=seen, page=page if page > 1 else None))


@bp.route("/admin/users/<int:user_id>/<action>", methods=("POST",))
@admin_required
def suspend(user_id, action):
    """Suspend (or restore) an account. Suspended people can't log in, and games they host are canceled
    so nobody shows up for nothing. Their reports stay for the record."""
    if action not in ("suspend", "restore"):
        abort(404)
    db = get_db()
    user = db.execute("SELECT id, full_name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    if action == "suspend" and (user_id == g.user["id"] or is_admin(user)):
        flash("Admins can't be suspended here. Remove them from ADMIN_EMAILS first.", "error")
    elif action == "suspend":
        from .events import query_events, tell_players_it_was_cancelled
        now = to_db(now_local())
        db.commit()
        db.execute("BEGIN IMMEDIATE")  # read their games and cancel them in one go: an officer canceling one of
        # them at the same moment can't make its players hear about it twice
        db.execute("UPDATE users SET suspended = 1 WHERE id = ?", (user_id,))
        from .clubs import hand_club_games_to_the_club
        hand_club_games_to_the_club(user_id)  # their clubs' games go on with another officer, not canceled
        hosted = query_events(["e.host_id = :host", "e.cancelled = 0", "e.ends_at >= :now"],
                              {"host": user_id, "now": now}, on_hold=True, limit=100000)  # club games on hold too
        # Clubs where they're the only officer left: someone has to take over (an admin can add one).
        stranded = db.execute(
            """SELECT c.id, c.name FROM clubs c JOIN club_members m ON m.club_id = c.id
               WHERE m.user_id = ? AND m.role = 'officer' AND NOT EXISTS (
                 SELECT 1 FROM club_members o JOIN users u ON u.id = o.user_id
                 WHERE o.club_id = c.id AND o.role = 'officer' AND o.user_id != ? AND u.suspended = 0)
               ORDER BY c.name""", (user_id, user_id)).fetchall()
        db.execute("UPDATE events SET cancelled = 1, revision = revision + 1 WHERE host_id = ? AND cancelled = 0 AND ends_at >= ?",
                   (user_id, now))
        # Free the spots they held in other people's upcoming games.
        db.execute("""DELETE FROM rsvps WHERE user_id = ? AND event_id IN
                      (SELECT id FROM events WHERE host_id != ? AND ends_at >= ?)""", (user_id, user_id, now))
        # Their invites in other people's games end, with the "You down?" notices they caused. (Invites to their
        # own games are closed, with an "invite is off" notice, by tell_players_it_was_cancelled below.)
        others = """(guest_id = :u OR inviter_id = :u) AND status IN ('pending', 'requested')
                    AND event_id IN (SELECT id FROM events WHERE ends_at >= :now AND host_id != :u)"""
        db.execute("""DELETE FROM notices WHERE EXISTS (
                        SELECT 1 FROM invites i JOIN events e ON e.id = i.event_id
                        WHERE i.inviter_id = :u AND i.status IN ('pending', 'requested') AND e.ends_at >= :now
                          AND e.host_id != :u AND i.guest_id = notices.user_id AND notices.key = 'invite:' || i.event_id)""",
                   {"u": user_id, "now": now})
        db.execute(f"UPDATE invites SET status = 'canceled' WHERE {others}", {"u": user_id, "now": now})
        db.commit()
        for event in hosted:
            tell_players_it_was_cancelled(event, by_host=False)
        flash(f"{user['full_name']} is suspended. Their upcoming games were canceled and players were told.", "info")
        if stranded:
            links = Markup(", ").join(Markup('<a href="{}">{}</a>').format(url_for("clubs.officers", club_id=c["id"]),
                                                                          c["name"]) for c in stranded)
            flash(Markup("They were the only officer of {}. Add a new officer there so join requests get answered.")
                  .format(links), "error")
    else:
        db.execute("UPDATE users SET suspended = 0 WHERE id = ?", (user_id,))
        flash(f"{user['full_name']} can log in again.", "success")
    db.commit()
    return redirect(url_for("moderation.admin_reports", status=request.args.get("from", "open")))


def open_report_count():
    """For the admin link in the menu."""
    if not is_admin():
        return 0
    return get_db().execute("SELECT COUNT(*) FROM reports WHERE status = 'open'").fetchone()[0]
