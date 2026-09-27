"""Clubs: an open directory anyone can browse, and any Husky can join. No ranks here.

Whoever creates a club becomes its officer. Officers can edit the club, post
announcements, add other officers and create club events (always "All levels").
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.datastructures import MultiDict

from .auth import login_required
from .constants import LOCATIONS, SPORT_EMOJI, SPORTS
from .db import get_db
from .timeutil import now_local, to_db

bp = Blueprint("clubs", __name__)

MAX_DESCRIPTION = 1000
MAX_POST = 1000


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


def officer_clubs(user_id):
    """Clubs this person can create events for."""
    return get_db().execute(
        """SELECT c.id, c.name, c.sport FROM clubs c JOIN club_members m ON m.club_id = c.id
           WHERE m.user_id = ? AND m.role = 'officer' ORDER BY c.name""", (user_id,)).fetchall()


def read_club_form(form, club_id=None):
    """Validate the create/edit form. Returns (data, error)."""
    name = form.get("name", "").strip()
    sport = form.get("sport", "")
    description = form.get("description", "").strip()
    meets = form.get("meets", "").strip()
    location = form.get("location", "").strip()
    contact_url = form.get("contact_url", "").strip()
    if not 3 <= len(name) <= 60:
        return None, "Club name must be 3 to 60 characters."
    if sport not in SPORTS:
        return None, "Please choose the club's main sport (pick Other if it's a mix)."
    if not 10 <= len(description) <= MAX_DESCRIPTION:
        return None, f"Tell people about your club in 10 to {MAX_DESCRIPTION} characters."
    if len(meets) > 120 or len(location) > 120:
        return None, "Keep 'When you meet' and 'Where' under 120 characters."
    if contact_url and (not contact_url.startswith("https://") or len(contact_url) > 200 or " " in contact_url):
        return None, "The contact link must be a full https:// link (like your Instagram or website)."
    taken = get_db().execute("SELECT id FROM clubs WHERE name = ? COLLATE NOCASE AND id != ?",
                             (name, club_id or 0)).fetchone()
    if taken:
        return None, "A club with that name already exists. Maybe join it instead?"
    return {"name": name, "sport": sport, "description": description, "meets": meets,
            "location": location, "contact_url": contact_url}, None


# ---------------------------------------------------------------- browse

@bp.route("/clubs")
def directory():
    """Open to everyone, even people without an account."""
    q = request.args.get("q", "").strip()
    sport = request.args.get("sport", "")
    mine = request.args.get("mine") == "1" and g.get("user") is not None
    where, params = ["1 = 1"], {"me": g.user["id"] if g.get("user") else 0}
    if q:
        where.append("(c.name LIKE :q OR c.description LIKE :q)")
        params["q"] = f"%{q}%"
    if sport in SPORTS:
        where.append("c.sport = :sport")
        params["sport"] = sport
    if mine:
        where.append("EXISTS (SELECT 1 FROM club_members m WHERE m.club_id = c.id AND m.user_id = :me)")
    clubs = get_db().execute(
        f"""SELECT c.*, (SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id) AS member_count,
                   EXISTS (SELECT 1 FROM club_members m WHERE m.club_id = c.id AND m.user_id = :me) AS i_am_in,
                   (SELECT COUNT(*) FROM events e WHERE e.club_id = c.id AND e.cancelled = 0
                                                   AND e.ends_at >= :now) AS upcoming
            FROM clubs c WHERE {" AND ".join(where)}
            ORDER BY i_am_in DESC, member_count DESC, c.name LIMIT 200""",
        {**params, "now": to_db(now_local())}).fetchall()
    return render_template("clubs/directory.html", clubs=clubs, q=q, sport=sport, mine=mine)


@bp.route("/clubs/<int:club_id>")
def view(club_id):
    """Open to everyone. Member names and event details need an account."""
    club = get_club(club_id)
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
                           role=my_role(club_id))


# ---------------------------------------------------------- create / edit

@bp.route("/clubs/new", methods=("GET", "POST"))
@login_required
def create():
    form = request.form if request.method == "POST" else MultiDict({"sport": request.args.get("sport", "")})
    if request.method == "POST":
        data, error = read_club_form(form)
        if error is None:
            db = get_db()
            now = to_db(now_local())
            cur = db.execute(
                """INSERT INTO clubs (name, sport, description, meets, location, contact_url, created_by, created_at)
                   VALUES (:name, :sport, :description, :meets, :location, :contact_url, :me, :now)""",
                {**data, "me": g.user["id"], "now": now})
            db.execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'officer', ?)",
                       (cur.lastrowid, g.user["id"], now))
            db.commit()
            flash(f"{data['name']} is live! 🏛️ Share it so people can join.", "celebrate")
            return redirect(url_for("clubs.view", club_id=cur.lastrowid))
        flash(error, "error")
    return render_template("clubs/form.html", form=form, club=None, locations=LOCATIONS)


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
            db = get_db()
            db.execute("""UPDATE clubs SET name = :name, sport = :sport, description = :description, meets = :meets,
                          location = :location, contact_url = :contact_url WHERE id = :id""", {**data, "id": club_id})
            db.commit()
            flash("Club updated.", "success")
            return redirect(url_for("clubs.view", club_id=club_id))
        flash(error, "error")
    else:
        form = MultiDict({key: club[key] for key in ("name", "sport", "description", "meets", "location", "contact_url")})
    return render_template("clubs/form.html", form=form, club=club, locations=LOCATIONS)


# ------------------------------------------------------------ membership

@bp.route("/clubs/<int:club_id>/join", methods=("POST",))
@login_required
def join(club_id):
    club = get_club(club_id)
    db = get_db()
    cur = db.execute("INSERT OR IGNORE INTO club_members (club_id, user_id, joined_at) VALUES (?, ?, ?)",
                     (club_id, g.user["id"], to_db(now_local())))
    db.commit()
    if cur.rowcount:
        flash(f"Welcome to {club['name']}! {SPORT_EMOJI[club['sport']]} Check the announcements and club events.",
              "celebrate")
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
    get_club(club_id)
    if my_role(club_id) != "officer":
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
