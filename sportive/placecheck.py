"""What else is happening at a place: UW Rec reservations, and other Sportive Circle games at the same time.

Two different things, shown differently:
- **UW Rec reservations** (IM leagues, club practices, rentals) mean the courts or field aren't free: people
  usually can't play there then. UW Rec has no public feed of these, so admins copy them in from UW Rec's
  schedule (Admin -> UW Rec). If UW Rec ever shares a feed, it can fill the same table (source = 'feed').
- **Other games on Sportive Circle** aren't reservations: the place is busy, not taken, and there may be room
  for more people. Hosts can still post; it's only a heads-up.
"""
from datetime import timedelta

import logging

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from .auth import login_required
from .constants import LOCATIONS
from .db import get_db
from .moderation import admin_required
from .textutil import one_line
from .timeutil import fmt_clock, fmt_when, now_local, parse_form, same_day, to_db

log = logging.getLogger(__name__)

bp = Blueprint("placecheck", __name__)

# Places UW Recreation runs (and reserves). Their official schedule/reservations page:
UW_REC_SCHEDULE = "https://reg.recreation.uw.edu/Facility"
UW_REC_PLACES = {
    "IMA (Intramural Activities Building)", "IMA North Tennis Courts", "IMA South Tennis Courts",
    "Recreation Field 1 (by the IMA)", "Recreation Field 2 (by Husky Track)",
    "Recreation Field 3 (by the golf range)", "Recreation Field 4 (by the golf range)",
    "Denny Field", "Husky Track", "Fitness Center West (under Elm Hall)", "Waterfront Activities Center (WAC)",
    "IMA Mat Rooms (martial arts)", "IMA Pool", "IMA Archery Room", "IMA Squash & Racquetball Courts",
    "Sand Volleyball Courts (by the IMA)", "UW Golf Driving Range",
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
    'a private game' / 'a club game' (their details are for the people in them)."""
    from .events import can_see_inside, event_title, query_events  # events.py imports this module
    rows = query_events(["e.location = :loc", "e.cancelled = 0", "e.starts_at < :ends", "e.ends_at > :starts",
                         "e.id != :exclude"],
                        {"loc": location, "starts": starts, "ends": ends, "exclude": exclude or 0}, limit=10)
    games = []
    for e in rows:
        hidden = not can_see_inside(e)  # private, or members-only and I'm not in the club
        games.append({
            "title": ("A private game" if e["is_private"] else "A club game") if hidden else event_title(e),
            "when": time_range(e["starts_at"], e["ends_at"]),
            "going": None if hidden else e["going_count"] + e["extra_players"],
            "max": None if hidden else e["max_players"],
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
    now = to_db(now_local())
    upcoming = db.execute("SELECT * FROM rec_reservations WHERE ends_at >= ? AND source = 'admin' ORDER BY starts_at"
                          " LIMIT 300", (now,)).fetchall()
    copied = db.execute("SELECT COUNT(*) FROM rec_reservations WHERE ends_at >= ? AND source = 'feed'",
                        (now,)).fetchone()[0]
    from .uwrec import last_report, last_synced
    return render_template("placecheck/admin.html", places=[p for p in LOCATIONS if p in UW_REC_PLACES],
                           upcoming=upcoming, form=form, schedule=UW_REC_SCHEDULE, max_weeks=MAX_REPEAT_WEEKS,
                           max_label=MAX_LABEL, time_range=time_range, copied=copied, synced=last_synced(),
                           report=last_report())


@bp.route("/admin/uw-rec/sync", methods=("POST",))
@admin_required
def admin_rec_sync():
    """"Update now": copy UW Rec's schedule right away (it also happens by itself once a day)."""
    from .uwrec import last_report, sync
    try:
        saved = sync()
        report = last_report() or {}
        if report.get("status") == "kept":
            flash("Far fewer bookings came back than last time, so the last copy is kept. See below.", "error")
        else:
            flash(f"Updated: {saved} bookings from UW Rec's schedule.", "success")
    except Exception:
        log.exception("Couldn't copy UW Rec's schedule")
        flash("Couldn't reach UW Rec's schedule right now. The last copy is still used. Try again later.", "error")
    return redirect(url_for("placecheck.admin_rec"))


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
