"""Clubs: verified, active UW clubs only. Anyone can browse them; any Husky can join.

To keep out random or inactive clubs, officers *register* their club with proof (at least one of
its social accounts, like its Instagram) and an admin approves it before it goes public.
The registration form also captures what each club is actually like (tryouts? dues?
experience? gear?), so students know exactly what they're signing up for.
"""
import io
import logging
import re
import secrets

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.datastructures import MultiDict

from .auth import login_required
from .constants import LOCATIONS, SPORT_EMOJI, SPORTS
from .db import get_db
from .links import public_url
from .mail import compose, send_email
from .moderation import is_admin
from .notifications import mark_seen
from .photos import make_avatar
from .textutil import one_line
from .timeutil import now_local, to_db

bp = Blueprint("clubs", __name__)
log = logging.getLogger(__name__)

MAX_DESCRIPTION = 1000
MAX_POST = 1000
MIN_ACTIVE_MEMBERS = 5
MAX_PENDING_PER_PERSON = 3

# The choices on the registration form (and the "Quick facts" on a club's page).
CLUB_KINDS = {
    "rec_club": "UW Recreation Rec Club",
    "rso": "Registered Student Organization",
}
FOCUS = {"competitive": "Competitive", "recreational": "Recreational", "instructional": "Instructional (learn the sport)",
         "mixed": "A mix"}
JOINING = {"open": "Open: just show up", "tryouts": "Tryouts", "application": "Application"}
EXPERIENCE = {"none": "No experience needed", "some": "Some experience helps", "experienced": "Experienced players"}
WHO_CAN_JOIN = {"everyone": "Everyone", "women": "Women", "men": "Men", "nonbinary": "Nonbinary"}  # in the form
WHO_CAN_JOIN_LABELS = {**WHO_CAN_JOIN, "women_nb": "Women & nonbinary"}  # older clubs may still say this
# Optional social accounts: (label, emoji, rule to check it, how to turn it into a link)
SOCIALS = {
    "instagram": ("Instagram", "📸", r"[A-Za-z0-9._]{1,30}", "https://instagram.com/{}"),
    "tiktok": ("TikTok", "🎵", r"[A-Za-z0-9._]{2,24}", "https://www.tiktok.com/@{}"),
    "snapchat": ("Snapchat", "👻", r"[A-Za-z][A-Za-z0-9._-]{2,14}", "https://www.snapchat.com/add/{}"),
    "x_handle": ("X / Twitter", "𝕏", r"[A-Za-z0-9_]{1,15}", "https://x.com/{}"),
    "facebook": ("Facebook", "📘", r"https://(www\.|m\.)?(facebook|fb)\.com/\S{1,150}", "{}"),
    "youtube": ("YouTube", "▶️", r"https://(www\.|m\.)?(youtube\.com|youtu\.be)/\S{1,150}", "{}"),
}


def social_links(club):
    """[(label, emoji, url, shown text)] for the socials a club filled in."""
    links = []
    for key, (label, emoji, _, link) in SOCIALS.items():
        value = club[key]
        if value:
            shown = value.replace("https://", "").replace("www.", "") if value.startswith("https://") else f"@{value}"
            links.append((label, emoji, link.format(value), shown))
    return links


# SQL for "how many confirmed members" (members + officers; followers and people waiting don't count).
MEMBER_COUNT = ("(SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id"
                " AND m.role IN ('member', 'officer')) AS member_count")

CHOICES = {"club_kind": CLUB_KINDS, "focus": FOCUS, "joining": JOINING, "experience": EXPERIENCE,
           "who_can_join": WHO_CAN_JOIN_LABELS}


def get_club(club_id):
    club = get_db().execute(
        f"""SELECT c.*, {MEMBER_COUNT}
           FROM clubs c WHERE c.id = ?""", (club_id,)).fetchone()
    if club is None:
        abort(404)
    return club


def my_role(club_id):
    """'officer', 'member', or None (not in the club / logged out)."""
    if g.get("user") is None:
        return None
    row = get_db().execute("SELECT role FROM club_members WHERE club_id = ? AND user_id = ?",
                           (club_id, g.user["id"])).fetchone()
    return row["role"] if row else None


def can_see(club):
    """Approved clubs are public. Pending/rejected ones: only their officers and admins."""
    return club["status"] == "approved" or my_role(club["id"]) == "officer" or is_admin()


def officer_clubs(user_id):
    """Approved clubs this person can create events for."""
    return get_db().execute(
        """SELECT c.id, c.name, c.sport FROM clubs c JOIN club_members m ON m.club_id = c.id
           WHERE m.user_id = ? AND m.role = 'officer' AND c.status = 'approved' ORDER BY c.name""",
        (user_id,)).fetchall()


def suggested_clubs(user_id, sports, limit=3):
    """Verified clubs for your sports that you haven't joined yet (for Home)."""
    if not sports:
        return []
    marks = ", ".join("?" for _ in sports)
    return get_db().execute(
        f"""SELECT c.*, {MEMBER_COUNT}
            FROM clubs c WHERE c.status = 'approved' AND c.sport IN ({marks})
              AND NOT EXISTS (SELECT 1 FROM club_members m WHERE m.club_id = c.id AND m.user_id = ?)
            ORDER BY member_count DESC LIMIT ?""", (*sports, user_id, limit)).fetchall()


def featured_clubs(limit=6):
    """Verified clubs for the landing page."""
    return get_db().execute(
        f"""SELECT c.*, {MEMBER_COUNT}
           FROM clubs c WHERE c.status = 'approved' ORDER BY member_count DESC, c.name LIMIT ?""", (limit,)).fetchall()


def read_club_form(form, club_id=None):
    """Validate the registration/edit form. Returns (data, error, field): `field` is the input
    with the problem, so the step-by-step form can open right on it."""
    get = lambda key: form.get(key, "").strip()
    single = lambda key: one_line(form.get(key))  # names, emails, links: no line breaks
    data = {key: single(key) for key in ("name", "sport", "meets", "location", "contact_url", "club_kind",
                                         "officer_role", "focus", "joining", "experience",
                                         "who_can_join", "dues", "gear", "club_email", "join_question")}
    data.update({key: get(key) for key in ("description", "how_to_join")})
    for key in SOCIALS:
        value = get(key)
        data[key] = value if value.startswith("https://") else value.lstrip("@")
    data["competes"] = 1 if form.get("competes") else 0
    members = get("member_estimate")

    def problem(field, message):
        return None, message, field

    if not 3 <= len(data["name"]) <= 60:
        return problem("name", "Club name must be 3 to 60 characters.")
    if data["sport"] not in SPORTS:
        return problem("sport", "Please choose the club's main sport (pick Other if it's a mix).")
    for key, options in CHOICES.items():
        if data[key] not in options:
            return problem(key, "Please answer every question in the form.")
    # The HuskyLink / UW Recreation page isn't asked anymore (people put their website there and got stuck):
    # clubs are checked through their social accounts. Clubs that gave one earlier keep it.
    old = get_db().execute("SELECT verification_url FROM clubs WHERE id = ?", (club_id or 0,)).fetchone()
    data["verification_url"] = old["verification_url"] if old else ""
    if not 20 <= len(data["description"]) <= MAX_DESCRIPTION:
        return problem("description", f"Tell people about your club in 20 to {MAX_DESCRIPTION} characters.")
    # Everything is required: people deciding whether to join need the full picture, and a way to reach you.
    required = {
        "join_question": "a question for people who want to join",
        "meets": "when you practice", "location": "where you practice",
        "dues": "your dues (type Free if there are none)", "gear": "what gear people need (or None needed)",
        "how_to_join": "how new members get started",
        "club_email": "a club email (so students and our team can reach you)",
    }
    for key, label in required.items():
        if not data[key]:
            return problem(key, f"Please add {label}. Every answer helps people decide to join and reach you.")
    if len(data["join_question"]) > 150:
        return problem("join_question", "Keep your question for new members under 150 characters.")
    for key, limit, label in (("meets", 120, "When you practice"), ("location", 120, "Where"), ("dues", 60, "Dues"),
                              ("gear", 120, "Gear"), ("how_to_join", 500, "How to join")):
        if len(data[key]) > limit:
            return problem(key, f"Keep '{label}' under {limit} characters.")
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,120}\.[a-z]{2,}", data["club_email"], re.I):
        return problem("club_email", "Please enter a valid club email.")
    for key, (label, _, rule, _) in SOCIALS.items():
        if data[key] and not re.fullmatch(rule, data[key]):
            example = "a link like https://facebook.com/yourclub" if key == "facebook" else (
                "a link like https://youtube.com/@yourclub" if key == "youtube" else "just the username, like @uwyourclub")
            return problem(key, f"That {label} doesn't look right. Use {example}.")
    # Almost every real club has a social account (few have a website): at least one is how we check it's real.
    if not any(data[key] for key in SOCIALS):
        return problem("instagram", "Add at least one of your club's social media accounts, like its Instagram. "
                       "That's how we check the club is real.")
    if data["contact_url"] and (not data["contact_url"].startswith("https://") or " " in data["contact_url"]
                                or len(data["contact_url"]) > 200):
        return problem("contact_url", "The website / Discord / GroupMe link must be a full https:// link.")
    if not 2 <= len(data["officer_role"]) <= 40:
        return problem("officer_role", "What's your role in the club? (e.g. President, Captain, Treasurer)")
    if not members.isdigit() or int(members) < MIN_ACTIVE_MEMBERS:
        return problem("member_estimate", f"Sportive Circle is for active clubs with at least {MIN_ACTIVE_MEMBERS} members.")
    data["member_estimate"] = min(int(members), 5000)
    if not form.get("attest"):
        return problem("attest", "Please confirm you're a current officer and the club is active this quarter.")
    taken = get_db().execute("SELECT id FROM clubs WHERE name = ? COLLATE NOCASE AND id != ?",
                             (data["name"], club_id or 0)).fetchone()
    if taken:
        return problem("name", "A club with that name is already on Sportive Circle. Ask its officers to add you instead!")
    return data, None, None


FIELDS = ("name", "sport", "description", "meets", "location", "contact_url", "club_kind", "verification_url",
          "officer_role", "member_estimate", "focus", "joining", "experience", "who_can_join", "dues", "gear",
          "competes", "how_to_join", "club_email", "instagram", "join_question", "tiktok", "snapchat", "x_handle",
          "facebook", "youtube")


# ---------------------------------------------------------------- browse

@bp.route("/clubs")
def directory():
    """Open to everyone, even people without an account. Only verified clubs are listed."""
    q = request.args.get("q", "").strip()[:100]
    sport = request.args.get("sport", "")
    mine = request.args.get("mine") == "1" and g.get("user") is not None
    easy = request.args.getlist("easy")  # quick filters: beginner / free / no_tryouts
    where, params = [], {"me": g.user["id"] if g.get("user") else 0}
    if mine:  # my clubs, including ones still being reviewed
        where.append("EXISTS (SELECT 1 FROM club_members m WHERE m.club_id = c.id AND m.user_id = :me)")
    else:
        where.append("c.status = 'approved'")
    if q:
        where.append("(c.name LIKE :q OR c.description LIKE :q)")
        params["q"] = f"%{q}%"
    if sport in SPORTS:
        where.append("c.sport = :sport")
        params["sport"] = sport
    if "beginner" in easy:
        where.append("c.experience = 'none'")
    if "free" in easy:
        where.append("(c.dues = '' OR LOWER(c.dues) = 'free')")
    if "no_tryouts" in easy:
        where.append("c.joining = 'open'")
    clubs = get_db().execute(
        f"""SELECT c.*, {MEMBER_COUNT},
                   (SELECT m.role FROM club_members m WHERE m.club_id = c.id AND m.user_id = :me) AS my_status,
                   (SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id
                                                        AND m.role IN ('requested', 'tryout')) AS waiting,
                   (SELECT COUNT(*) FROM events e WHERE e.club_id = c.id AND e.cancelled = 0
                                                   AND e.ends_at >= :now) AS upcoming
            FROM clubs c WHERE {" AND ".join(where)}
            ORDER BY my_status IS NOT NULL DESC, member_count DESC, c.name LIMIT 200""",
        {**params, "now": to_db(now_local())}).fetchall()
    return render_template("clubs/directory.html", clubs=clubs, q=q, sport=sport, mine=mine, easy=easy)


@bp.route("/clubs/<int:club_id>")
def view(club_id):
    """Open to everyone (once verified). Member names and event details need an account."""
    club = get_club(club_id)
    if not can_see(club):
        abort(404)
    db = get_db()
    posts = db.execute(
        """SELECT p.*, u.full_name FROM club_posts p LEFT JOIN users u ON u.id = p.author_id
           WHERE p.club_id = ? ORDER BY p.id DESC LIMIT 20""", (club_id,)).fetchall()
    members, requests = [], []
    role = my_role(club_id)
    if g.get("user") is not None:
        members = roster(club_id)
    if role == "officer":
        requests = db.execute(
            """SELECT u.id, u.full_name, u.avatar_updated, m.role, m.message, m.joined_at
               FROM club_members m JOIN users u ON u.id = m.user_id
               WHERE m.club_id = ? AND m.role IN ('requested', 'tryout') ORDER BY m.joined_at""", (club_id,)).fetchall()
    followers = db.execute("SELECT COUNT(*) FROM club_members WHERE club_id = ? AND role = 'follower'",
                           (club_id,)).fetchone()[0]
    from .events import SHOWN_UNLESS_FULL  # imported here: events.py imports this module
    events = db.execute(
        f"""SELECT e.id, e.title, e.sport, e.starts_at, e.location, e.members_only FROM events e
            WHERE e.club_id = :club AND e.cancelled = 0 AND e.ends_at >= :now AND {SHOWN_UNLESS_FULL}
            ORDER BY e.starts_at LIMIT 10""",
        {"club": club_id, "now": to_db(now_local()), "me": g.user["id"] if g.get("user") else 0,
         "hold_now": to_db(now_local())}).fetchall()
    return render_template("clubs/view.html", club=club, posts=posts, members=members, events=events,
                           role=role, requests=requests, followers=followers, kinds=CLUB_KINDS, focus=FOCUS,
                           socials=social_links(club),
                           joining=JOINING,
                           experience=EXPERIENCE, who=WHO_CAN_JOIN_LABELS)


# ---------------------------------------------------- roster (officers)

def roster(club_id):
    """Members and officers, officers first. Emails are only shown to the club's officers (see the template)."""
    return get_db().execute(
        """SELECT u.id, u.full_name, u.email, u.grad_year, u.avatar_updated, m.role, m.joined_at
           FROM club_members m JOIN users u ON u.id = m.user_id
           WHERE m.club_id = ? AND m.role IN ('member', 'officer')
           ORDER BY m.role = 'officer' DESC, u.full_name""", (club_id,)).fetchall()


@bp.route("/clubs/<int:club_id>/roster.csv")
@login_required
def roster_csv(club_id):
    """For officers: the member list as a spreadsheet (dues, waivers, the club's own group chat)."""
    import csv  # only needed here
    club = require_officer(club_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "UW email", "Class of", "Role", "Joined"])
    for person in roster(club_id):
        writer.writerow([person["full_name"], person["email"], person["grad_year"] or "", person["role"].title(),
                         person["joined_at"][:10]])
    filename = re.sub(r"[^A-Za-z0-9]+", "-", club["name"]).strip("-").lower() or "club"
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}-roster.csv"})


# ---------------------------------------------------- logo

def require_officer(club_id):
    club = get_club(club_id)
    if my_role(club_id) != "officer":
        abort(403)
    return club


@bp.route("/clubs/<int:club_id>/logo")
def logo(club_id):
    club = get_club(club_id)
    row = get_db().execute("SELECT image FROM club_logos WHERE club_id = ?", (club_id,)).fetchone()
    if row is None or not can_see(club):
        abort(404)
    response = Response(row["image"], mimetype="image/jpeg")
    # The URL changes whenever the logo does (?v=...), so browsers can keep it.
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@bp.route("/clubs/<int:club_id>/logo/edit", methods=("GET", "POST"))
@login_required
def edit_logo(club_id):
    """Officers add the club's real logo, so it looks like their club (not just a sport emoji)."""
    club = require_officer(club_id)
    if request.method == "POST":
        db = get_db()
        if request.form.get("remove"):
            db.execute("DELETE FROM club_logos WHERE club_id = ?", (club_id,))
            db.execute("UPDATE clubs SET logo_updated = NULL WHERE id = ?", (club_id,))
            db.commit()
            flash("Logo removed.", "info")
            return redirect(url_for("clubs.view", club_id=club_id))
        upload = request.files.get("logo")
        if upload is None or not upload.filename:
            flash("Choose an image first.", "error")
        else:
            try:
                image = make_avatar(upload.read())
            except ValueError as error:
                flash(str(error), "error")
            else:
                db.execute("INSERT OR REPLACE INTO club_logos (club_id, image) VALUES (?, ?)", (club_id, image))
                db.execute("UPDATE clubs SET logo_updated = ? WHERE id = ?",
                           (f"{now_local().strftime('%Y%m%d%H%M')}-{secrets.token_hex(3)}", club_id))
                db.commit()
                flash("Logo saved.", "success")
                return redirect(url_for("clubs.view", club_id=club_id))
    return render_template("clubs/logo.html", club=club)


# ---------------------------------------------------- share (link + QR code for flyers and the involvement fair)

@bp.route("/clubs/<int:club_id>/share")
def share(club_id):
    club = get_club(club_id)
    if club["status"] != "approved":
        abort(404)
    return render_template("clubs/share.html", club=club, link=public_url("clubs.view", club_id=club_id))


@bp.route("/clubs/<int:club_id>/qr.svg")
def qr_code(club_id):
    """A QR code that opens the club's page: purple on white, ready to print on a flyer."""
    import segno  # only needed here
    club = get_club(club_id)
    if club["status"] != "approved":
        abort(404)
    code = segno.make(public_url("clubs.view", club_id=club_id), error="m")
    output = io.BytesIO()
    code.save(output, kind="svg", scale=8, dark="#4b2e83", light="#ffffff", border=2, xmldecl=False)
    response = Response(output.getvalue(), mimetype="image/svg+xml")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


# ---------------------------------------------------- register / edit

@bp.route("/clubs/new", methods=("GET", "POST"))
@login_required
def create():
    """Register an existing, active UW club. It goes public once an admin approves it."""
    form = request.form if request.method == "POST" else MultiDict(
        {"sport": request.args.get("sport", ""), "joining": "open", "experience": "none", "who_can_join": "everyone"})
    if request.method == "POST":
        pending = get_db().execute(
            """SELECT COUNT(*) FROM clubs c JOIN club_members m ON m.club_id = c.id
               WHERE m.user_id = ? AND m.role = 'officer' AND c.status = 'pending'""", (g.user["id"],)).fetchone()[0]
        data, error, error_field = read_club_form(form)
        if error is None and pending >= MAX_PENDING_PER_PERSON:
            error = "You already have clubs waiting for review. We'll get to them soon!"
        if error is None:
            db = get_db()
            now = to_db(now_local())
            cur = db.execute(
                f"INSERT INTO clubs ({', '.join(FIELDS)}, status, created_by, created_at) "
                f"VALUES ({', '.join(':' + f for f in FIELDS)}, 'pending', :me, :now)",
                {**data, "me": g.user["id"], "now": now})
            db.execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'officer', ?)",
                       (cur.lastrowid, g.user["id"], now))
            db.commit()
            flash("Thanks! We'll check it's a real UW club (usually within 2 days) and email you when it's live.",
                  "success")
            return redirect(url_for("clubs.view", club_id=cur.lastrowid))
        flash(error, "error")
    return _club_form_page(form, None, error_field if request.method == "POST" else None)


def _club_form_page(form, club, error_field):
    return render_template("clubs/form.html", form=form, club=club, locations=LOCATIONS, kinds=CLUB_KINDS,
                           focus=FOCUS, joining=JOINING, experience=EXPERIENCE, who=WHO_CAN_JOIN,
                           min_members=MIN_ACTIVE_MEMBERS, error_field=error_field)


@bp.route("/clubs/<int:club_id>/edit", methods=("GET", "POST"))
@login_required
def edit(club_id):
    club = get_club(club_id)
    if my_role(club_id) != "officer":
        abort(403)
    error_field = None
    if request.method == "POST":
        form = request.form
        data, error, error_field = read_club_form(form, club_id)
        if error is None:
            # Changing who the club *is* (or fixing a rejected one) sends it back for review.
            identity_changed = any(data[key] != club[key] for key in ("name", "club_kind"))
            status = "pending" if identity_changed or club["status"] == "rejected" else club["status"]
            db = get_db()
            db.execute(f"UPDATE clubs SET {', '.join(f + ' = :' + f for f in FIELDS)}, status = :status WHERE id = :id",
                       {**data, "status": status, "id": club_id})
            db.commit()
            if status == "pending" and club["status"] != "pending":
                flash("Saved. The club's name or type changed, so we'll quickly check it again.", "info")
            else:
                flash("Club updated.", "success")
            return redirect(url_for("clubs.view", club_id=club_id))
        flash(error, "error")
    else:
        form = MultiDict({key: club[key] for key in FIELDS})
        form.setlist("competes", ["1"] if club["competes"] else [])
    return _club_form_page(form, club, error_field)


# ------------------------------------------------------------ membership

MEMBER_ROLES = ("member", "officer")
WAITING_ROLES = ("requested", "tryout")


def _dm(sender_id, recipient_id, body):
    """A direct message about club membership (officers and applicants can always talk)."""
    db = get_db()
    db.execute("INSERT INTO direct_messages (sender_id, recipient_id, body, created_at) VALUES (?, ?, ?, ?)",
               (sender_id, recipient_id, body, to_db(now_local())))


def _club_link(club_id):
    return public_url("clubs.view", club_id=club_id)


@bp.route("/clubs/<int:club_id>/follow", methods=("POST",))
@login_required
def follow(club_id):
    """⭐ Follow: see announcements and events without being a member."""
    club = get_club(club_id)
    if club["status"] != "approved":
        abort(404)
    db = get_db()
    cur = db.execute("INSERT OR IGNORE INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'follower', ?)",
                     (club_id, g.user["id"], to_db(now_local())))
    db.commit()
    if cur.rowcount:
        flash(f"Following {club['name']}. Their updates show up in Clubs.", "success")
    return redirect(url_for("clubs.view", club_id=club_id))


@bp.route("/clubs/<int:club_id>/join", methods=("POST",))
@login_required
def join(club_id):
    """Ask to become a member. What happens depends on the club: tryouts, an application, or open.
    Either way, you're only a member once an officer confirms it."""
    club = get_club(club_id)
    if club["status"] != "approved":
        abort(404)
    role = my_role(club_id)
    if role in MEMBER_ROLES or role in WAITING_ROLES:
        return redirect(url_for("clubs.view", club_id=club_id))
    message = request.form.get("message", "").strip()
    if len(message) > 500:
        flash("Please keep your answer under 500 characters.", "error")
        return redirect(url_for("clubs.view", club_id=club_id) + "#join")
    if club["join_question"] and club["joining"] == "application" and not message:
        flash("Answer the club's question first.", "error")
        return redirect(url_for("clubs.view", club_id=club_id) + "#join")
    new_role = "tryout" if club["joining"] == "tryouts" else "requested"
    db = get_db()
    db.execute("""INSERT INTO club_members (club_id, user_id, role, message, joined_at) VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT(club_id, user_id) DO UPDATE SET role = excluded.role, message = excluded.message,
                                                          joined_at = excluded.joined_at""",
               (club_id, g.user["id"], new_role, message, to_db(now_local())))
    db.commit()
    # Let the officers know there's someone new.
    what = "signed up for tryouts" if new_role == "tryout" else "wants to join"
    for officer in db.execute("""SELECT u.email FROM club_members m JOIN users u ON u.id = m.user_id
                                 WHERE m.club_id = ? AND m.role = 'officer'""", (club_id,)):
        try:
            subject = f"{g.user['full_name']} {what} {club['name']}"
            answer = [f"Their answer to “{club['join_question']}”:", message] if message and club["join_question"] \
                else ([f"Their message: {message}"] if message else [])
            body, html = compose(subject, f"{g.user['full_name']} {what} {club['name']} 🙋", answer,
                                 after=["Confirm or decline them from your club's Members tab."],
                                 button=("Review requests", f"{_club_link(club_id)}#requests"),
                                 reason=f"You're getting this because you're an officer of {club['name']}.")
            send_email(officer["email"], subject, body, html=html)
        except Exception:  # email trouble shouldn't stop the request
            log.exception("Couldn't email officer %s about a join request", officer["email"])
    if new_role == "tryout":
        flash(f"You're signed up for {club['name']} tryouts. Next steps are below.", "celebrate")
    else:
        flash("Request sent. An officer will confirm you. Next steps are below.", "celebrate")
    return redirect(url_for("clubs.view", club_id=club_id) + ("#how-to-join" if club["how_to_join"] else ""))


@bp.route("/clubs/<int:club_id>/members/<int:user_id>/<decision>", methods=("POST",))
@login_required
def decide(club_id, user_id, decision):
    """Officers confirm or decline people waiting to join (and can remove members)."""
    club = get_club(club_id)
    if my_role(club_id) != "officer" or decision not in ("approve", "decline", "remove"):
        abort(403)
    db = get_db()
    row = db.execute("SELECT role FROM club_members WHERE club_id = ? AND user_id = ?", (club_id, user_id)).fetchone()
    if row is None:
        abort(404)
    me = g.user["id"]
    if decision == "approve" and row["role"] in WAITING_ROLES:
        db.execute("UPDATE club_members SET role = 'member' WHERE club_id = ? AND user_id = ?", (club_id, user_id))
        made_it = "You made the team! " if row["role"] == "tryout" else ""
        _dm(me, user_id, f"✅ {made_it}You're officially a member of {club['name']}. Welcome! "
                         f"{SPORT_EMOJI[club['sport']]} {_club_link(club_id)}")
        flash("Confirmed. They're a member now.", "success")
    elif decision == "decline" and row["role"] in WAITING_ROLES:
        # They stay a follower, so they still see what the club is up to.
        db.execute("UPDATE club_members SET role = 'follower', message = '' WHERE club_id = ? AND user_id = ?",
                   (club_id, user_id))
        if row["role"] == "tryout":
            body = (f"Thanks so much for trying out for {club['name']}! We couldn't offer you a spot this time, "
                    "but we'd love to see you again next season. You're still following the club. 💜")
        else:
            body = (f"Thanks for your interest in {club['name']}! We can't add you as a member right now, "
                    "but you're still following the club and we hope to see you around. 💜")
        _dm(me, user_id, body)
        flash("Declined. They still follow the club.", "info")
    elif decision == "remove" and row["role"] == "member":
        db.execute("DELETE FROM club_members WHERE club_id = ? AND user_id = ?", (club_id, user_id))
        flash("Removed from the club.", "info")
    db.commit()
    return redirect(url_for("clubs.view", club_id=club_id) + ("#requests" if decision != "remove" else "#members"))


@bp.route("/clubs/<int:club_id>/leave", methods=("POST",))
@login_required
def leave(club_id):
    """Leave the club, cancel a request, or unfollow."""
    db = get_db()
    role = my_role(club_id)
    officers = db.execute("SELECT COUNT(*) FROM club_members WHERE club_id = ? AND role = 'officer'",
                          (club_id,)).fetchone()[0]
    if role == "officer" and officers == 1:
        flash("You're the only officer. Make someone else an officer before you leave.", "error")
    elif role is not None:
        db.execute("DELETE FROM club_members WHERE club_id = ? AND user_id = ?", (club_id, g.user["id"]))
        db.commit()
        flash({"follower": "Unfollowed.", "requested": "Request canceled.", "tryout": "Tryout sign-up canceled."}
              .get(role, "You left the club."), "info")
    return redirect(url_for("clubs.view", club_id=club_id))


@bp.route("/clubs/<int:club_id>/officers/<int:user_id>", methods=("POST",))
@login_required
def make_officer(club_id, user_id):
    if my_role(club_id) != "officer":
        abort(403)
    db = get_db()
    db.execute("UPDATE club_members SET role = 'officer' WHERE club_id = ? AND user_id = ? AND role = 'member'",
               (club_id, user_id))
    db.commit()
    flash("They're an officer now.", "success")
    return redirect(url_for("clubs.view", club_id=club_id) + "#members")


# --------------------------------------------------------- updates feed

@bp.route("/clubs/updates", methods=("GET", "POST"))
@login_required
def updates():
    """Posts from every club you follow, asked to join, or are in. Officers can post here too."""
    me = g.user["id"]
    db = get_db()
    my_officer_clubs = officer_clubs(me)
    if request.method == "POST":
        club_id = request.form.get("club", type=int)
        body = request.form.get("body", "").strip()
        if club_id not in {club["id"] for club in my_officer_clubs}:
            abort(403)
        if not body or len(body) > MAX_POST:
            flash(f"Updates must be 1 to {MAX_POST} characters.", "error")
        else:
            db.execute("INSERT INTO club_posts (club_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
                       (club_id, me, body, to_db(now_local())))
            db.commit()
            flash("Posted. Your followers will see it.", "success")
        return redirect(url_for("clubs.updates"))
    posts = db.execute(
        """SELECT p.*, c.name AS club_name, c.sport, c.logo_updated AS club_logo, u.full_name, u.avatar_updated,
                  (SELECT m2.role FROM club_members m2 WHERE m2.club_id = c.id AND m2.user_id = u.id) AS author_role
           FROM club_posts p JOIN clubs c ON c.id = p.club_id LEFT JOIN users u ON u.id = p.author_id
           WHERE c.status = 'approved'
             AND EXISTS (SELECT 1 FROM club_members m WHERE m.club_id = c.id AND m.user_id = ?)
           ORDER BY p.id DESC LIMIT 100""", (me,)).fetchall()
    following = db.execute("SELECT COUNT(*) FROM club_members WHERE user_id = ?", (me,)).fetchone()[0]
    mark_seen("club_updates")
    return render_template("clubs/updates.html", posts=posts, my_officer_clubs=my_officer_clubs,
                           following=following)


# --------------------------------------------------------- announcements

@bp.route("/clubs/<int:club_id>/posts", methods=("POST",))
@login_required
def post(club_id):
    club = get_club(club_id)
    if my_role(club_id) != "officer" or club["status"] != "approved":
        abort(403)
    body = request.form.get("body", "").strip()
    if not body or len(body) > MAX_POST:
        flash(f"Announcements must be 1 to {MAX_POST} characters.", "error")
    else:
        db = get_db()
        db.execute("INSERT INTO club_posts (club_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
                   (club_id, g.user["id"], body, to_db(now_local())))
        db.commit()
        flash("Posted.", "success")
    return redirect(url_for("clubs.view", club_id=club_id) + "#announcements")


@bp.route("/clubs/<int:club_id>/posts/<int:post_id>/delete", methods=("POST",))
@login_required
def delete_post(club_id, post_id):
    if my_role(club_id) != "officer":
        abort(403)
    db = get_db()
    db.execute("DELETE FROM club_posts WHERE id = ? AND club_id = ?", (post_id, club_id))
    db.commit()
    return redirect(url_for("clubs.view", club_id=club_id) + "#announcements")


# --------------------------------------------------------- admin review

def pending_club_count():
    if not is_admin():
        return 0
    return get_db().execute("SELECT COUNT(*) FROM clubs WHERE status = 'pending'").fetchone()[0]


def _notify_officers(club, subject, heading, lines, button):
    body, html = compose(subject, heading, lines, button=button,
                         reason=f"You're getting this because you're an officer of {club['name']}.")
    for row in get_db().execute(
            """SELECT u.email FROM club_members m JOIN users u ON u.id = m.user_id
               WHERE m.club_id = ? AND m.role = 'officer'""", (club["id"],)):
        try:
            send_email(row["email"], subject, body, html=html)
        except Exception:  # email trouble shouldn't block the review
            log.exception("Couldn't email officer %s", row["email"])


@bp.route("/admin/clubs")
@login_required
def review_queue():
    if not is_admin():
        abort(404)
    status = request.args.get("status", "pending")
    if status not in ("pending", "approved", "rejected"):
        status = "pending"
    clubs = get_db().execute(
        f"""SELECT c.*, u.full_name AS applicant, u.email AS applicant_email,
                  {MEMBER_COUNT}
           FROM clubs c LEFT JOIN users u ON u.id = c.created_by WHERE c.status = ? ORDER BY c.id""",
        (status,)).fetchall()
    club_counts = {row["status"]: row["n"] for row in get_db().execute(
        "SELECT status, COUNT(*) AS n FROM clubs GROUP BY status")}
    return render_template("clubs/review.html", clubs=clubs, status=status, club_counts=club_counts, social_links=social_links,
                           kinds=CLUB_KINDS, focus=FOCUS, joining=JOINING, experience=EXPERIENCE,
                           who=WHO_CAN_JOIN_LABELS)


@bp.route("/admin/clubs/<int:club_id>/<decision>", methods=("POST",))
@login_required
def review(club_id, decision):
    if not is_admin() or decision not in ("approve", "reject"):
        abort(404)
    club = get_club(club_id)
    note = request.form.get("note", "").strip()[:500]
    if decision == "reject" and not note:
        flash("Add a short note so the officers know what to fix.", "error")
        return redirect(url_for("clubs.review_queue"))
    db = get_db()
    db.execute("UPDATE clubs SET status = ?, review_note = ?, reviewed_at = ? WHERE id = ?",
               ("approved" if decision == "approve" else "rejected", note, to_db(now_local()), club_id))
    db.commit()
    link = _club_link(club_id)
    if decision == "approve":
        _notify_officers(club, f"✅ {club['name']} is live on Sportive Circle!", f"{club['name']} is live! 🎉",
                         ["Your club is verified and now visible to every Husky.",
                          "Next: post an update and add your next practice as a club event."],
                         ("Open your club", link))
        flash(f"Approved {club['name']}. The officers were emailed.", "success")
    else:
        _notify_officers(club, f"About your Sportive Circle club: {club['name']}", "One quick fix needed",
                         [f"We couldn't verify {club['name']} yet. Here's what to fix:", note,
                          "Update it and it'll be reviewed again."],
                         ("Update your club", link))
        flash(f"Sent {club['name']} back to the officers with your note.", "info")
    return redirect(url_for("clubs.review_queue"))
