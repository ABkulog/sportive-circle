"""Clubs: verified, active UW clubs only. Anyone can browse them; any Husky can join.

To keep out random or inactive clubs, officers *register* their club with proof (its
official HuskyLink or UW Recreation page) and an admin approves it before it goes public.
The registration form also captures what each club is actually like (tryouts? dues?
experience? gear?), so students know exactly what they're signing up for.
"""
import re

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.datastructures import MultiDict

from .auth import login_required
from .constants import LOCATIONS, SPORT_EMOJI, SPORTS
from .db import get_db
from .mail import send_email
from .timeutil import now_local, to_db

bp = Blueprint("clubs", __name__)

MAX_DESCRIPTION = 1000
MAX_POST = 1000
MIN_ACTIVE_MEMBERS = 5
MAX_PENDING_PER_PERSON = 3

# The choices on the registration form (and the "Quick facts" on a club's page).
CLUB_KINDS = {
    "rec_club": "UW Recreation Rec Club",
    "rso": "Registered Student Organization (HuskyLink)",
}
VERIFICATION_PREFIXES = (
    "https://huskylink.washington.edu/organization/",
    "https://www.washington.edu/ima/",
    "https://reg.recreation.uw.edu/",
)
FOCUS = {"competitive": "Competitive", "recreational": "Recreational", "instructional": "Instructional (learn the sport)",
         "mixed": "A mix"}
JOINING = {"open": "Open: just show up", "tryouts": "Tryouts", "application": "Application"}
EXPERIENCE = {"none": "No experience needed", "some": "Some experience helps", "experienced": "Experienced players"}
WHO_CAN_JOIN = {"everyone": "Everyone", "women": "Women", "men": "Men", "women_nb": "Women & nonbinary"}
CHOICES = {"club_kind": CLUB_KINDS, "focus": FOCUS, "joining": JOINING, "experience": EXPERIENCE,
           "who_can_join": WHO_CAN_JOIN}


def get_club(club_id):
    club = get_db().execute(
        """SELECT c.*, (SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id) AS member_count
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
    from .moderation import is_admin
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
        f"""SELECT c.*, (SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id) AS member_count
            FROM clubs c WHERE c.status = 'approved' AND c.sport IN ({marks})
              AND NOT EXISTS (SELECT 1 FROM club_members m WHERE m.club_id = c.id AND m.user_id = ?)
            ORDER BY member_count DESC LIMIT ?""", (*sports, user_id, limit)).fetchall()


def featured_clubs(limit=6):
    """Verified clubs for the landing page."""
    return get_db().execute(
        """SELECT c.*, (SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id) AS member_count
           FROM clubs c WHERE c.status = 'approved' ORDER BY member_count DESC, c.name LIMIT ?""", (limit,)).fetchall()


def read_club_form(form, club_id=None):
    """Validate the registration/edit form. Returns (data, error)."""
    get = lambda key: form.get(key, "").strip()
    data = {key: get(key) for key in ("name", "sport", "description", "meets", "location", "contact_url",
                                      "club_kind", "verification_url", "officer_role", "focus", "joining",
                                      "experience", "who_can_join", "dues", "gear", "how_to_join", "club_email")}
    data["instagram"] = get("instagram").lstrip("@")
    data["competes"] = 1 if form.get("competes") else 0
    members = get("member_estimate")

    if not 3 <= len(data["name"]) <= 60:
        return None, "Club name must be 3 to 60 characters."
    if data["sport"] not in SPORTS:
        return None, "Please choose the club's main sport (pick Other if it's a mix)."
    for key, options in CHOICES.items():
        if data[key] not in options:
            return None, "Please answer every question in the form."
    if not data["verification_url"].startswith(VERIFICATION_PREFIXES) or " " in data["verification_url"] \
            or len(data["verification_url"]) > 200:
        return None, ("Add your club's official page: its HuskyLink page (https://huskylink.washington.edu/organization/…) "
                      "or its UW Recreation page. This is how we verify it's a real UW club.")
    if not 2 <= len(data["officer_role"]) <= 40:
        return None, "What's your role in the club? (e.g. President, Captain, Treasurer)"
    if not members.isdigit() or int(members) < MIN_ACTIVE_MEMBERS:
        return None, f"Sportive Circle is for active clubs with at least {MIN_ACTIVE_MEMBERS} members."
    data["member_estimate"] = min(int(members), 5000)
    if not 20 <= len(data["description"]) <= MAX_DESCRIPTION:
        return None, f"Tell people about your club in 20 to {MAX_DESCRIPTION} characters."
    if len(data["meets"]) > 120 or len(data["location"]) > 120:
        return None, "Keep 'When you practice' and 'Where' under 120 characters."
    if len(data["dues"]) > 60 or len(data["gear"]) > 120 or len(data["how_to_join"]) > 500:
        return None, "Some answers are too long. Keep dues under 60, gear under 120 and how to join under 500 characters."
    if data["contact_url"] and (not data["contact_url"].startswith("https://") or " " in data["contact_url"]
                                or len(data["contact_url"]) > 200):
        return None, "The website must be a full https:// link."
    if data["club_email"] and not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,120}\.[a-z]{2,}", data["club_email"], re.I):
        return None, "Please enter a valid club email (or leave it empty)."
    if data["instagram"] and not re.fullmatch(r"[A-Za-z0-9._]{1,30}", data["instagram"]):
        return None, "Instagram handles only have letters, numbers, dots and underscores."
    if not form.get("attest"):
        return None, "Please confirm you're a current officer and the club is active this quarter."
    taken = get_db().execute("SELECT id FROM clubs WHERE name = ? COLLATE NOCASE AND id != ?",
                             (data["name"], club_id or 0)).fetchone()
    if taken:
        return None, "A club with that name is already on Sportive Circle. Ask its officers to add you instead!"
    return data, None


FIELDS = ("name", "sport", "description", "meets", "location", "contact_url", "club_kind", "verification_url",
          "officer_role", "member_estimate", "focus", "joining", "experience", "who_can_join", "dues", "gear",
          "competes", "how_to_join", "club_email", "instagram")


# ---------------------------------------------------------------- browse

@bp.route("/clubs")
def directory():
    """Open to everyone, even people without an account. Only verified clubs are listed."""
    q = request.args.get("q", "").strip()
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
        f"""SELECT c.*, (SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id) AS member_count,
                   EXISTS (SELECT 1 FROM club_members m WHERE m.club_id = c.id AND m.user_id = :me) AS i_am_in,
                   (SELECT COUNT(*) FROM events e WHERE e.club_id = c.id AND e.cancelled = 0
                                                   AND e.ends_at >= :now) AS upcoming
            FROM clubs c WHERE {" AND ".join(where)}
            ORDER BY i_am_in DESC, member_count DESC, c.name LIMIT 200""",
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
    members = []
    if g.get("user") is not None:
        members = db.execute(
            """SELECT u.id, u.full_name, u.avatar_updated, m.role FROM club_members m JOIN users u ON u.id = m.user_id
               WHERE m.club_id = ? ORDER BY m.role = 'officer' DESC, u.full_name""", (club_id,)).fetchall()
    events = db.execute(
        """SELECT e.id, e.title, e.sport, e.starts_at, e.location FROM events e
           WHERE e.club_id = ? AND e.cancelled = 0 AND e.ends_at >= ? ORDER BY e.starts_at LIMIT 10""",
        (club_id, to_db(now_local()))).fetchall()
    return render_template("clubs/view.html", club=club, posts=posts, members=members, events=events,
                           role=my_role(club_id), kinds=CLUB_KINDS, focus=FOCUS, joining=JOINING,
                           experience=EXPERIENCE, who=WHO_CAN_JOIN)


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
        data, error = read_club_form(form)
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
            flash("Thanks! 🏛️ Your club is being reviewed. We check that it's a real, active UW club, usually "
                  "within 2 days, and we'll email you when it's live.", "success")
            return redirect(url_for("clubs.view", club_id=cur.lastrowid))
        flash(error, "error")
    return render_template("clubs/form.html", form=form, club=None, locations=LOCATIONS, kinds=CLUB_KINDS,
                           focus=FOCUS, joining=JOINING, experience=EXPERIENCE, who=WHO_CAN_JOIN,
                           min_members=MIN_ACTIVE_MEMBERS)


@bp.route("/clubs/<int:club_id>/edit", methods=("GET", "POST"))
@login_required
def edit(club_id):
    club = get_club(club_id)
    if my_role(club_id) != "officer":
        abort(403)
    if request.method == "POST":
        form = request.form
        data, error = read_club_form(form, club_id)
        if error is None:
            # Changing who the club *is* (or fixing a rejected one) sends it back for review.
            identity_changed = any(data[key] != club[key] for key in ("name", "club_kind", "verification_url"))
            status = "pending" if identity_changed or club["status"] == "rejected" else club["status"]
            db = get_db()
            db.execute(f"UPDATE clubs SET {', '.join(f + ' = :' + f for f in FIELDS)}, status = :status WHERE id = :id",
                       {**data, "status": status, "id": club_id})
            db.commit()
            if status == "pending" and club["status"] != "pending":
                flash("Saved! Since the club's name or official page changed, it'll be quickly re-verified.", "info")
            else:
                flash("Club updated.", "success")
            return redirect(url_for("clubs.view", club_id=club_id))
        flash(error, "error")
    else:
        form = MultiDict({key: club[key] for key in FIELDS})
        form.setlist("competes", ["1"] if club["competes"] else [])
    return render_template("clubs/form.html", form=form, club=club, locations=LOCATIONS, kinds=CLUB_KINDS,
                           focus=FOCUS, joining=JOINING, experience=EXPERIENCE, who=WHO_CAN_JOIN,
                           min_members=MIN_ACTIVE_MEMBERS)


# ------------------------------------------------------------ membership

@bp.route("/clubs/<int:club_id>/join", methods=("POST",))
@login_required
def join(club_id):
    club = get_club(club_id)
    if club["status"] != "approved":
        abort(404)
    db = get_db()
    cur = db.execute("INSERT OR IGNORE INTO club_members (club_id, user_id, joined_at) VALUES (?, ?, ?)",
                     (club_id, g.user["id"], to_db(now_local())))
    db.commit()
    if cur.rowcount:
        next_step = " Check \"How to join\" for your first steps." if club["how_to_join"] else ""
        flash(f"Welcome to {club['name']}! {SPORT_EMOJI[club['sport']]}{next_step}", "celebrate")
    return redirect(url_for("clubs.view", club_id=club_id))


@bp.route("/clubs/<int:club_id>/leave", methods=("POST",))
@login_required
def leave(club_id):
    db = get_db()
    officers = db.execute("SELECT COUNT(*) FROM club_members WHERE club_id = ? AND role = 'officer'",
                          (club_id,)).fetchone()[0]
    if my_role(club_id) == "officer" and officers == 1:
        flash("You're the only officer. Make someone else an officer before you leave, so the club isn't left "
              "without a leader.", "error")
    else:
        db.execute("DELETE FROM club_members WHERE club_id = ? AND user_id = ?", (club_id, g.user["id"]))
        db.commit()
        flash("You left the club.", "info")
    return redirect(url_for("clubs.view", club_id=club_id))


@bp.route("/clubs/<int:club_id>/officers/<int:user_id>", methods=("POST",))
@login_required
def make_officer(club_id, user_id):
    if my_role(club_id) != "officer":
        abort(403)
    db = get_db()
    db.execute("UPDATE club_members SET role = 'officer' WHERE club_id = ? AND user_id = ?", (club_id, user_id))
    db.commit()
    flash("They're an officer now. 🎖️", "success")
    return redirect(url_for("clubs.view", club_id=club_id) + "#members")


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
        flash("Announcement posted! 📣", "success")
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
    from .moderation import is_admin
    if not is_admin():
        return 0
    return get_db().execute("SELECT COUNT(*) FROM clubs WHERE status = 'pending'").fetchone()[0]


def _notify_officers(club, subject, body):
    for row in get_db().execute(
            """SELECT u.email FROM club_members m JOIN users u ON u.id = m.user_id
               WHERE m.club_id = ? AND m.role = 'officer'""", (club["id"],)):
        try:
            send_email(row["email"], subject, body)
        except Exception:  # email trouble shouldn't block the review
            pass


@bp.route("/admin/clubs")
@login_required
def review_queue():
    from .moderation import is_admin
    if not is_admin():
        abort(404)
    status = request.args.get("status", "pending")
    if status not in ("pending", "approved", "rejected"):
        status = "pending"
    clubs = get_db().execute(
        """SELECT c.*, u.full_name AS applicant, u.email AS applicant_email,
                  (SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id) AS member_count
           FROM clubs c LEFT JOIN users u ON u.id = c.created_by WHERE c.status = ? ORDER BY c.id""",
        (status,)).fetchall()
    club_counts = {row["status"]: row["n"] for row in get_db().execute(
        "SELECT status, COUNT(*) AS n FROM clubs GROUP BY status")}
    return render_template("clubs/review.html", clubs=clubs, status=status, club_counts=club_counts,
                           kinds=CLUB_KINDS, focus=FOCUS, joining=JOINING, experience=EXPERIENCE, who=WHO_CAN_JOIN)


@bp.route("/admin/clubs/<int:club_id>/<decision>", methods=("POST",))
@login_required
def review(club_id, decision):
    from .moderation import is_admin
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
    from flask import current_app
    link = f"{current_app.config['PUBLIC_URL'].rstrip('/')}/clubs/{club_id}"
    if decision == "approve":
        _notify_officers(club, f"✅ {club['name']} is live on Sportive Circle!",
                         f"Your club is verified and now visible to every Husky: {link}\n\n"
                         "Next: post an announcement and add your next practice as a club event. Go Dawgs! 🐺")
        flash(f"Approved {club['name']}. The officers were emailed.", "success")
    else:
        _notify_officers(club, f"About your Sportive Circle club: {club['name']}",
                         f"We couldn't verify your club yet. Here's what to fix:\n\n{note}\n\n"
                         f"Update it here and it'll be reviewed again: {link}")
        flash(f"Sent {club['name']} back to the officers with your note.", "info")
    return redirect(url_for("clubs.review_queue"))
