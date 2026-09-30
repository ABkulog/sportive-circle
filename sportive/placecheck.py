"""What else is happening at a place: UW Rec reservations, and other Sportive Circle games at the same time.

Two different things, shown differently:
- **UW Rec reservations** (IM leagues, club practices, rentals) mean the courts or field aren't free: people
  usually can't play there then. UW Rec has no public feed of these, so admins copy them in from UW Rec's
  schedule (Admin -> UW Rec). If UW Rec ever shares a feed, it can fill the same table (source = 'feed').
- **Other games on Sportive Circle** aren't reservations: the place is busy, not taken, and there may be room
  for more people. Hosts can still post; it's only a heads-up.
"""
from datetime import timedelta

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from .auth import login_required
from .constants import LOCATIONS
from .db import get_db
from .moderation import admin_required
from .textutil import one_line
from .timeutil import fmt_clock, fmt_when, now_local, parse_form, same_day, to_db

bp = Blueprint("placecheck", __name__)

# Places UW Recreation runs (and reserves). Their official schedule/reservations page:
UW_REC_SCHEDULE = "https://reg.recreation.uw.edu/Facility"
UW_REC_PLACES = {
    "IMA (Intramural Activities Building)", "IMA North Tennis Courts", "IMA South Tennis Courts",
    "Recreation Field 1 (by the IMA)", "Recreation Field 2 (by Husky Track)",
    "Recreation Field 3 (by the golf range)", "Recreation Field 4 (by the golf range)",
    "Denny Field", "Husky Track", "Fitness Center West (under Elm Hall)", "Waterfront Activities Center (WAC)",
}
MAX_REPEAT_WEEKS = 20   # a quarter of weekly IM nights, with room to spare
MAX_LABEL = 80


def is_uw_rec(location):
    return location in UW_REC_PLACES


def time_range(starts, ends):
    """'6–10 PM' style text for a reservation or game (DB strings)."""
    if same_day(starts, ends):
        return f"{fmt_when(starts)}–{fmt_clock(ends)}"
    return f"{fmt_when(starts)} – {fmt_when(ends)}"


def rec_reservations(location, starts, ends):
    """UW Rec reservations at this place that overlap starts-ends (DB strings)."""
    return get_db().execute(
        """SELECT * FROM rec_reservations WHERE location = ? AND starts_at < ? AND ends_at > ?
           ORDER BY starts_at""", (location, ends, starts)).fetchall()


def games_at(location, starts, ends, exclude=None):
    """Other Sportive Circle games at this place overlapping starts-ends. Private games only show as
    'a private game' (their details are for the people in them)."""
    from .events import event_title, query_events  # events.py imports this module
    rows = query_events(["e.location = :loc", "e.cancelled = 0", "e.starts_at < :ends", "e.ends_at > :starts",
                         "e.id != :exclude"],
                        {"loc": location, "starts": starts, "ends": ends, "exclude": exclude or 0}, limit=10)
    games = []
    for e in rows:
        mine = e["host_id"] == g.user["id"] or e["i_am_going"] or e["i_am_invited"]
        hidden = e["is_private"] and not mine
        games.append({
            "title": "A private game" if hidden else event_title(e),
            "when": time_range(e["starts_at"], e["ends_at"]),
            "going": e["going_count"] + e["extra_players"], "max": e["max_players"],
            "url": None if hidden else url_for("events.detail", event_id=e["id"]),
        })
    return games


def whats_on(location, starts, ends, exclude=None):
    """Everything the host (or a player) should know about this place at this time."""
    return {
        "uw_rec": is_uw_rec(location),
        "schedule": UW_REC_SCHEDULE if is_uw_rec(location) else None,
        "reserved": [{"label": r["label"], "when": time_range(r["starts_at"], r["ends_at"])}
                     for r in rec_reservations(location, starts, ends)],
        "games": games_at(location, starts, ends, exclude),
    }


@bp.route("/events/place-check")
@login_required
def place_check():
    """For the create/edit form: what's on at the place and time picked so far (JSON)."""
    location = request.args.get("location", "")
    try:
        starts = parse_form(request.args.get("starts_at", ""))
        ends = parse_form(request.args.get("ends_at", ""))
    except ValueError:
        return jsonify(None)
    if location not in LOCATIONS or ends <= starts or ends - starts > timedelta(days=2):
        return jsonify(None)
    exclude = request.args.get("event", type=int)
    return jsonify(whats_on(location, to_db(starts), to_db(ends), exclude))


# ---------------------------------------------------------------- admin: copy in UW Rec's reservations

@bp.route("/admin/uw-rec", methods=("GET", "POST"))
@admin_required
def admin_rec():
    db = get_db()
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        location = form.get("location", "")
        label = one_line(form.get("label", ""))[:MAX_LABEL]
        weeks = request.form.get("weeks", type=int) or 1
        try:
            day = parse_form(form.get("date", "") + "T00:00")
            start_h, start_m = (int(x) for x in form.get("start", "").split(":"))
            end_h, end_m = (int(x) for x in form.get("end", "").split(":"))
            starts = day.replace(hour=start_h, minute=start_m)
            ends = day.replace(hour=end_h, minute=end_m)
        except (ValueError, TypeError):
            starts = ends = None
        if location not in UW_REC_PLACES:
            flash("Pick one of UW Rec's places.", "error")
        elif starts is None:
            flash("Pick a date and a start and end time.", "error")
        elif ends <= starts:
            flash("The end has to be after the start (split overnight reservations in two).", "error")
        elif not label:
            flash("Say what it's for, like “IM flag football”.", "error")
        elif not 1 <= weeks <= MAX_REPEAT_WEEKS:
            flash(f"Repeat for 1 to {MAX_REPEAT_WEEKS} weeks.", "error")
        else:
            now = to_db(now_local())
            db.executemany(
                """INSERT INTO rec_reservations (location, starts_at, ends_at, label, source, created_by, created_at)
                   VALUES (?, ?, ?, ?, 'admin', ?, ?)""",
                [(location, to_db(starts + timedelta(weeks=n)), to_db(ends + timedelta(weeks=n)), label,
                  g.user["id"], now) for n in range(weeks)])
            db.commit()
            flash(f"Added {weeks} reservation{'s' if weeks != 1 else ''}.", "success")
            return redirect(url_for("placecheck.admin_rec"))
    upcoming = db.execute("SELECT * FROM rec_reservations WHERE ends_at >= ? ORDER BY starts_at LIMIT 300",
                          (to_db(now_local()),)).fetchall()
    return render_template("placecheck/admin.html", places=[p for p in LOCATIONS if p in UW_REC_PLACES],
                           upcoming=upcoming, form=form, schedule=UW_REC_SCHEDULE, max_weeks=MAX_REPEAT_WEEKS,
                           max_label=MAX_LABEL, time_range=time_range)


@bp.route("/admin/uw-rec/<int:reservation_id>/delete", methods=("POST",))
@admin_required
def admin_rec_delete(reservation_id):
    db = get_db()
    row = db.execute("SELECT * FROM rec_reservations WHERE id = ?", (reservation_id,)).fetchone()
    if row is not None:
        if request.form.get("all"):  # the whole weekly series: same place, label and clock times
            db.execute("""DELETE FROM rec_reservations WHERE location = ? AND label = ? AND starts_at >= ?
                          AND time(starts_at) = time(?) AND time(ends_at) = time(?)
                          AND strftime('%w', starts_at) = strftime('%w', ?)""",
                       (row["location"], row["label"], to_db(now_local().replace(hour=0, minute=0)),
                        row["starts_at"], row["ends_at"], row["starts_at"]))
        else:
            db.execute("DELETE FROM rec_reservations WHERE id = ?", (reservation_id,))
        db.commit()
        flash("Removed.", "success")
    return redirect(url_for("placecheck.admin_rec"))
