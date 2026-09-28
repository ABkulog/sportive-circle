"""Feed, event create/edit/cancel, RSVPs, 'Need players' quick posts, and My events."""
import logging
from datetime import datetime, time, timedelta, timezone
from urllib.parse import quote

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.datastructures import MultiDict

from .auth import login_required, safe_next
from .badges import sync_badges
from .clubs import featured_clubs, suggested_clubs
from .constants import (LOCATION_COORDS, LOCATIONS, QUICK_DURATIONS, QUICK_START_OPTIONS, SKILL_LEVELS,
                        SPORT_LOCATIONS, SPORT_MAX_PLAYERS, SPORTS)
from .db import get_db, user_sports
from .links import public_url
from .notifications import mark_seen, notify
from .mail import compose, send_email
from .social import is_blocked_between
from .spirit import greeting, top_dawgs
from .textutil import one_line
from .timeutil import fmt_clock, fmt_when, from_db, now_local, parse_form, to_db, to_form

bp = Blueprint("events", __name__)
log = logging.getLogger(__name__)

MAX_EVENT_LENGTH = timedelta(days=3)   # long enough for a ski or hiking trip
MAX_DAYS_AHEAD = 365
QUICK_WINDOW = timedelta(hours=3)      # quick posts starting this soon go to the top of the feed
UP_NEXT_WINDOW = timedelta(hours=2)    # your own events starting this soon get a banner on the feed


# ---------------------------------------------------------------- queries

def query_events(where, params=None, order="e.starts_at", limit=100):
    """Events + host name + how many are going + whether *I* am going.

    `where` is a list of SQL conditions written in this file (never user input);
    user values always go through `params`.
    """
    params = {"me": g.user["id"], **(params or {})}
    sql = f"""
        SELECT e.*, u.full_name AS host_name, u.avatar_updated AS host_avatar, cl.name AS club_name,
               (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id) AS going_count,
               EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me) AS i_am_going
        FROM events e JOIN users u ON u.id = e.host_id LEFT JOIN clubs cl ON cl.id = e.club_id
        WHERE {" AND ".join(where)}
        ORDER BY {order}
        LIMIT {int(limit)}"""
    return get_db().execute(sql, params).fetchall()


def get_event(event_id, host_only=False):
    rows = query_events(["e.id = :id"], {"id": event_id}, limit=1)
    if not rows:
        abort(404)
    event = rows[0]
    if host_only and event["host_id"] != g.user["id"]:
        abort(403)
    return event


def spots_left(event):
    """None = unlimited."""
    if event["max_players"] is None:
        return None
    return max(event["max_players"] - event["going_count"] - event["extra_players"], 0)


def event_title(event):
    """Need-players posts show a live count ("Need 2 more for Soccer") instead of the saved title."""
    if not event["is_quick"]:
        return event["title"]
    sport = SPORTS[event["sport"]]
    if event["cancelled"] or from_db(event["ends_at"]) < now_local():
        return f"{sport} pickup game"
    left = spots_left(event)
    return f"{sport}: full" if left == 0 else f"Need {left} more for {sport}"


def place_map(location):
    """Map pin + walking-directions links for a place, or None (Off campus, Online)."""
    if location not in LOCATION_COORDS:
        return None
    coords = LOCATION_COORDS[location]
    if coords:
        destination = f"{coords[0]},{coords[1]}"
    else:  # no single pin: let the maps app search for it by name
        destination = quote(f"{location}, University of Washington, Seattle")
    return {
        "name": location,
        "lat": coords[0] if coords else None,
        "lng": coords[1] if coords else None,
        # Both links start from wherever the person is right now.
        "google": f"https://www.google.com/maps/dir/?api=1&destination={destination}&travelmode=walking",
        "apple": f"https://maps.apple.com/?daddr={destination}&dirflg=w",
    }


def round_up_5(dt):
    return dt + timedelta(minutes=-dt.minute % 5)


def insert_event(data):
    db = get_db()
    cur = db.execute(
        """INSERT INTO events (host_id, title, sport, location, starts_at, ends_at, skill_level,
                               max_players, extra_players, note, is_quick, club_id)
           VALUES (:host_id, :title, :sport, :location, :starts_at, :ends_at, :skill_level,
                   :max_players, :extra_players, :note, :is_quick, :club_id)""",
        {"host_id": g.user["id"], "extra_players": 0, "is_quick": 0, "club_id": None, **data},
    )
    # The host is automatically going to their own event.
    db.execute("INSERT INTO rsvps (event_id, user_id, created_at) VALUES (?, ?, ?)",
               (cur.lastrowid, g.user["id"], to_db(now_local())))
    db.commit()
    return cur.lastrowid


# -------------------------------------------------------------------- feed

# Games from someone I blocked (or who blocked me) never show up in my feed.
NOT_BLOCKED = """NOT EXISTS (SELECT 1 FROM blocks b WHERE (b.blocker_id = :me AND b.blocked_id = e.host_id)
                                              OR (b.blocker_id = e.host_id AND b.blocked_id = :me))"""

def celebrate_progress(user_id):
    """Unlock new badges (with confetti)."""
    new = sync_badges(user_id)
    if len(new) == 1:
        flash(f"New badge: {new[0].emoji} {new[0].name}", "celebrate")
    elif new:
        flash(f"{len(new)} new badges: {' '.join(badge.emoji for badge in new)}", "celebrate")


@bp.route("/")
def feed():
    if g.user is None:
        return render_template("landing.html", clubs=featured_clubs())

    my_sports = user_sports(g.user["id"])
    filters = {key: request.args.get(key, "") for key in ("scope", "sport", "location", "skill", "when")}
    if filters["scope"] not in ("interests", "all"):
        filters["scope"] = "interests" if my_sports else "all"

    now = now_local()
    where = ["e.cancelled = 0", "e.ends_at >= :now", NOT_BLOCKED]
    params = {"now": to_db(now)}

    if filters["sport"] in SPORTS:
        where.append("e.sport = :sport")
        params["sport"] = filters["sport"]
    elif filters["scope"] == "interests" and my_sports:
        names = [f":s{i}" for i in range(len(my_sports))]
        where.append(f"e.sport IN ({', '.join(names)})")
        params.update({f"s{i}": sport for i, sport in enumerate(my_sports)})
    if filters["location"] in LOCATIONS:
        where.append("e.location = :location")
        params["location"] = filters["location"]
    if filters["skill"] in SKILL_LEVELS:
        where.append("e.skill_level = :skill")
        params["skill"] = filters["skill"]
    if filters["when"] == "today":
        where.append("e.starts_at < :until")
        params["until"] = to_db(datetime.combine(now.date() + timedelta(days=1), time()))
    elif filters["when"] == "week":
        where.append("e.starts_at < :until")
        params["until"] = to_db(now + timedelta(days=7))
    elif filters["when"] == "month":  # until the end of this calendar month
        where.append("e.starts_at < :until")
        next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
        params["until"] = to_db(datetime.combine(next_month.date(), time()))

    events = query_events(where, params)

    # "Need players" posts starting soon (any sport) go in their own strip at the top.
    need_players = [
        e for e in query_events(
            ["e.cancelled = 0", "e.is_quick = 1", "e.ends_at >= :now", "e.starts_at <= :soon", NOT_BLOCKED],
            {"now": to_db(now), "soon": to_db(now + QUICK_WINDOW)},
            limit=10,
        )
        if spots_left(e) != 0 or e["i_am_going"]
    ]
    shown = {e["id"] for e in need_players}
    events = [e for e in events if e["id"] not in shown]

    up_next = query_events(
        ["e.cancelled = 0", "e.ends_at >= :now", "e.starts_at <= :soon",
         "EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me)"],
        {"now": to_db(now), "soon": to_db(now + UP_NEXT_WINDOW)}, limit=1)

    celebrate_progress(g.user["id"])
    hello, spirit_line = greeting(g.user["full_name"].split()[0], now)
    mark_seen("need_players")
    return render_template("events/feed.html", events=events, need_players=need_players,
                           filters=filters, my_sports=my_sports, up_next=up_next[0] if up_next else None,
                           hello=hello, spirit_line=spirit_line, top_dawgs=top_dawgs(now=now),
                           club_picks=suggested_clubs(g.user["id"], my_sports))


# ---------------------------------------------------------- create / edit

def read_event_form(form, event=None):
    """Validate the create/edit form. Returns (data, error)."""
    title = one_line(form.get("title"))
    sport = form.get("sport", "")
    location = form.get("location", "")
    skill_level = form.get("skill_level", "")
    note = form.get("note", "").strip()
    max_raw = form.get("max_players", "").strip()
    now = now_local()

    if not title:
        return None, "Event name cannot be empty."
    if len(title) > 80:
        return None, "Event name is too long (80 characters max)."
    if sport not in SPORTS:
        return None, "Please choose a sport."
    if location not in LOCATIONS:
        return None, "Please choose a location."
    if location not in SPORT_LOCATIONS[sport]:
        return None, f"{SPORTS[sport]} can't be played at {location}. Choose another place."
    if skill_level not in SKILL_LEVELS:
        return None, "Please choose a skill level."
    try:
        starts = parse_form(form.get("starts_at", ""))
    except ValueError:
        return None, "Event start time cannot be empty."
    try:
        ends = parse_form(form.get("ends_at", ""))
    except ValueError:
        return None, "Event end time cannot be empty."
    if ends <= starts:
        return None, "The event has to end after it starts."
    if ends - starts > MAX_EVENT_LENGTH:
        return None, "Events can be at most 3 days long."
    if ends <= now:
        return None, "The end time has already passed."
    start_changed = event is None or to_db(starts) != event["starts_at"]
    if start_changed and starts < now:
        return None, "Event date can't be before now."
    if starts > now + timedelta(days=MAX_DAYS_AHEAD):
        return None, "Event date can't be more than a year away."

    cap = SPORT_MAX_PLAYERS[sport]
    max_players = cap  # left blank = the most this sport allows
    if max_raw:
        if not max_raw.isdigit() or int(max_raw) < 2:
            return None, "Max players must be at least 2."
        max_players = int(max_raw)
        if max_players > cap:
            return None, f"{SPORTS[sport]} events can have at most {cap} players."
    if event is not None:
        taken = event["going_count"] + event["extra_players"]
        if max_players < taken:
            return None, f"{taken} people are already in, so max players can't be lower than that."
    if len(note) > 500:
        return None, "Note is too long (500 characters max)."

    return {
        "title": title, "sport": sport, "location": location, "skill_level": skill_level,
        "starts_at": to_db(starts), "ends_at": to_db(ends), "max_players": max_players, "note": note,
    }, None


def default_times():
    start = (now_local() + timedelta(hours=1)).replace(minute=0)
    return start.strftime("%Y-%m-%dT%H:%M"), (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")


@bp.route("/events/new", methods=("GET", "POST"))
@login_required
def create():
    club = club_for_new_event(request.values.get("club", type=int))
    if request.method == "POST":
        form = request.form
        data, error = read_event_form(form)
        if error is None and club is not None:
            data.update(club_id=club["id"], skill_level="All levels")  # club events are for everyone
        if error is None:
            duplicate = get_db().execute(
                "SELECT 1 FROM events WHERE host_id = ? AND title = ? AND starts_at = ? AND cancelled = 0",
                (g.user["id"], data["title"], data["starts_at"]),
            ).fetchone()
            if duplicate:
                error = "This event has already been created."
        if error is None:
            event_id = insert_event(data)
            flash("Your event is live! Go Dawgs 💜💛", "celebrate")
            return redirect(url_for("events.detail", event_id=event_id))
        flash(error, "error")
    else:
        starts, ends = default_times()
        form = MultiDict({"starts_at": starts, "ends_at": ends, "skill_level": "All levels",
                          "sport": request.args.get("sport", "") or (club["sport"] if club else "")})
    return render_template("events/form.html", form=form, event=None, club=club,
                           min_start=now_local().strftime("%Y-%m-%dT%H:%M"))


def club_for_new_event(club_id):
    """The club an officer is creating an event for (None for a normal event)."""
    if not club_id:
        return None
    club = get_db().execute(
        """SELECT c.* FROM clubs c JOIN club_members m ON m.club_id = c.id
           WHERE c.id = ? AND m.user_id = ? AND m.role = 'officer' AND c.status = 'approved'""",
        (club_id, g.user["id"])).fetchone()
    if club is None:
        abort(403)
    return club


@bp.route("/events/<int:event_id>/edit", methods=("GET", "POST"))
@login_required
def edit(event_id):
    event = get_event(event_id, host_only=True)
    if event["cancelled"]:
        flash("This event was canceled, so it can't be edited.", "error")
        return redirect(url_for("events.detail", event_id=event_id))
    if request.method == "POST":
        form = request.form
        data, error = read_event_form(form, event)
        if error is None and event["club_id"]:
            data.update(skill_level="All levels")
        if error is None:
            db = get_db()
            db.execute(
                """UPDATE events SET title = :title, sport = :sport, location = :location,
                       starts_at = :starts_at, ends_at = :ends_at, skill_level = :skill_level,
                       max_players = :max_players, note = :note
                   WHERE id = :id""",
                {**data, "id": event_id},
            )
            told = tell_players_it_changed(event, data)
            db.commit()
            flash("Saved. Everyone going got a heads-up." if told else "Saved.", "success")
            return redirect(url_for("events.detail", event_id=event_id))
        flash(error, "error")
    else:
        form = MultiDict({
            "title": event["title"], "sport": event["sport"], "location": event["location"],
            "skill_level": event["skill_level"], "starts_at": to_form(event["starts_at"]),
            "ends_at": to_form(event["ends_at"]), "note": event["note"],
            "max_players": event["max_players"] or "",
        })
    return render_template("events/form.html", form=form, event=event, min_start="")


@bp.route("/events/<int:event_id>/cancel", methods=("POST",))
@login_required
def cancel(event_id):
    event = get_event(event_id, host_only=True)
    if event["cancelled"] or from_db(event["ends_at"]) < now_local():
        return redirect(url_for("events.detail", event_id=event_id))
    db = get_db()
    db.execute("UPDATE events SET cancelled = 1 WHERE id = ?", (event_id,))
    db.commit()
    tell_players_it_was_cancelled(event)
    flash("Event canceled. We let everyone who joined know.", "info")
    return redirect(url_for("events.my_events"))


def players_except_host(event):
    return get_db().execute(
        """SELECT u.id, u.email, u.full_name FROM rsvps r JOIN users u ON u.id = r.user_id
           WHERE r.event_id = ? AND r.user_id != ?""", (event["id"], event["host_id"])).fetchall()


def what_changed(event, data):
    """Plain words for what the host changed that players need to know ("new time: Sat, Oct 3 · 3:00 PM")."""
    changes = []
    if (data["starts_at"], data["ends_at"]) != (event["starts_at"], event["ends_at"]):
        changes.append(f"new time: {fmt_when(data['starts_at'])}")
    if data["location"] != event["location"]:
        changes.append(f"new place: {data['location']}")
    if data["sport"] != event["sport"]:
        changes.append(f"now {SPORTS[data['sport']]}")
    if data["note"] != event["note"]:
        changes.append("new note")
    return changes


def tell_players_it_changed(event, data):
    """The host changed something important: a notice in everyone's bell, plus an email when the time or
    place changed (so nobody shows up at the old one). Returns True if anyone was told. Caller commits."""
    changes = what_changed(event, data)
    players = players_except_host(event)
    if not changes or not players:
        return False
    title, host = data["title"] if not event["is_quick"] else event_title(event), event["host_name"].split()[0]
    link = url_for("events.detail", event_id=event["id"])
    for player in players:
        notify(player["id"], "game_updates", f"{host} changed {title}: {', '.join(changes)}", link)
    if any(change.startswith(("new time", "new place")) for change in changes):
        for player in players:
            try:
                subject = f"Changed: {title}"
                body, html = compose(
                    subject, f"{title} changed",
                    [f"Hey {player['full_name'].split()[0]}, {host} changed this game.",
                     f"🕐 {fmt_when(data['starts_at'])}", f"📍 {data['location']}"],
                    button=("See the game", public_url("events.detail", event_id=event["id"])),
                    reason="You're getting this because you joined this game.",
                    preheader=f"{host} changed {title}.")
                send_email(player["email"], subject, body, html=html)
            except Exception:  # one bad address shouldn't stop the others
                log.exception("Couldn't email %s about a changed event", player["email"])
    return True


def tell_players_it_was_cancelled(event):
    """Tell everyone who joined (except the host), so nobody shows up to an empty field."""
    players = players_except_host(event)
    title, when = event_title(event), fmt_when(event["starts_at"])
    for player in players:
        # Links to the feed: if the host deleted their account, the game's page is gone too.
        notify(player["id"], "game_updates", f"{event['host_name'].split()[0]} canceled {title} ({when})",
               url_for("events.feed"))
    get_db().commit()
    for player in players:
        try:
            subject = f"Canceled: {title} ({when})"
            body, html = compose(
                subject, f"{title} was canceled",
                [f"Hey {player['full_name'].split()[0]}, heads up: {event['host_name']} canceled this game.",
                 f"🕐 {when}", f"📍 {event['location']}", "No worries, there are more games waiting for you."],
                button=("Find another game", public_url("events.feed")),
                reason="You're getting this because you joined this game.",
                preheader=f"{event['host_name']} canceled {title}.")
            send_email(player["email"], subject, body, html=html)
        except Exception:  # one bad address shouldn't stop the others
            log.exception("Couldn't email %s about a canceled event", player["email"])


# ------------------------------------------------------ "Need players" post

@bp.route("/need-players", methods=("GET", "POST"))
@login_required
def quick():
    form = request.form if request.method == "POST" else MultiDict(
        {"starts_in": "30", "duration": "60", "needed": "2", "have": "1", "skill_level": "All levels"})
    if request.method == "POST":
        error = None
        sport = form.get("sport", "")
        location = form.get("location", "")
        skill_level = form.get("skill_level", "")
        note = form.get("note", "").strip()
        starts_in = dict(QUICK_START_OPTIONS).get(_int(form.get("starts_in")))
        duration = dict(QUICK_DURATIONS).get(_int(form.get("duration")))
        needed = _int(form.get("needed"))
        have = _int(form.get("have"))

        if sport not in SPORTS:
            error = "Please choose a sport."
        elif location not in LOCATIONS:
            error = "Please choose a location."
        elif location not in SPORT_LOCATIONS[sport]:
            error = f"{SPORTS[sport]} can't be played at {location}. Choose another place."
        elif skill_level not in SKILL_LEVELS:
            error = "Please choose a skill level."
        elif starts_in is None or duration is None:
            error = "Please choose when you're playing."
        elif needed is None or not 1 <= needed <= 30:
            error = "How many more players do you need? (1 to 30)"
        elif have is None or not 1 <= have <= 50:
            error = "How many are already playing, including you? (1 to 50)"
        elif have + needed > SPORT_MAX_PLAYERS[sport]:
            error = (f"{SPORTS[sport]} games max out at {SPORT_MAX_PLAYERS[sport]} players, "
                     f"and {have} + {needed} is {have + needed}.")
        elif len(note) > 500:
            error = "Note is too long (500 characters max)."

        if error is None:
            starts = round_up_5(now_local() + timedelta(minutes=_int(form.get("starts_in"))))
            ends = starts + timedelta(minutes=_int(form.get("duration")))
            event_id = insert_event({
                "title": f"Need {needed} for {SPORTS[sport]}", "sport": sport, "location": location,
                "skill_level": skill_level, "starts_at": to_db(starts), "ends_at": to_db(ends),
                # `have` includes the host, who is counted through their RSVP.
                "max_players": have + needed, "extra_players": have - 1, "note": note, "is_quick": 1,
            })
            flash("Posted! The whole pack can see it at the top of the feed 🐺", "celebrate")
            return redirect(url_for("events.detail", event_id=event_id))
        flash(error, "error")
    return render_template("events/quick.html", form=form, start_options=QUICK_START_OPTIONS,
                           durations=QUICK_DURATIONS)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------ detail / RSVP

@bp.route("/events/<int:event_id>")
@login_required
def detail(event_id):
    event = get_event(event_id)
    attendees = get_db().execute(
        """SELECT u.id, u.full_name, u.grad_year, u.avatar_updated
           FROM rsvps r JOIN users u ON u.id = r.user_id
           WHERE r.event_id = ? ORDER BY r.created_at""",
        (event_id,),
    ).fetchall()
    return render_template("events/detail.html", event=event, attendees=attendees,
                           ended=from_db(event["ends_at"]) < now_local(),
                           share_url=public_url("events.detail", event_id=event_id),
                           blocked=is_blocked_between(g.user["id"], event["host_id"]))


@bp.route("/events/<int:event_id>/join", methods=("POST",))
@login_required
def join(event_id):
    event = get_event(event_id)
    if event["cancelled"]:
        flash("This event was canceled.", "error")
    elif from_db(event["ends_at"]) < now_local():
        flash("This event already ended.", "error")
    elif event["i_am_going"]:
        flash("You're already going.", "info")
    elif is_blocked_between(g.user["id"], event["host_id"]):
        # Blocking means no contact at all, and that includes showing up to each other's games.
        flash("You can't join this game.", "error")
    else:
        db = get_db()
        # The capacity check and the insert happen in one statement, so two people
        # clicking "Join" at the same moment can't both take the last spot.
        cur = db.execute(
            """INSERT INTO rsvps (event_id, user_id, created_at)
               SELECT e.id, :me, :now FROM events e
               WHERE e.id = :id AND (e.max_players IS NULL OR
                     e.extra_players + (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id) < e.max_players)""",
            {"me": g.user["id"], "id": event_id, "now": to_db(now_local())},
        )
        db.commit()
        if cur.rowcount:
            flash("You're in! See you there, Dawg 🐺", "celebrate")
            clash = overlapping_event(event)
            if clash:
                flash(f"Heads up: this overlaps with “{event_title(clash)}” ({fmt_clock(clash['starts_at'])}), "
                      "which you're also going to.", "info")
        else:
            flash("Sorry, this event is full. Check the feed for another game!", "error")
    if request.form.get("next"):  # joined from a card in the feed: stay there
        return redirect(safe_next(request.form["next"]))
    return redirect(url_for("events.detail", event_id=event_id))


def overlapping_event(event):
    """Another event I'm going to that overlaps this one's time, if any."""
    rows = query_events(
        ["e.id != :id", "e.cancelled = 0", "e.starts_at < :ends", "e.ends_at > :starts",
         "EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me)"],
        {"id": event["id"], "starts": event["starts_at"], "ends": event["ends_at"]}, limit=1)
    return rows[0] if rows else None


# Seattle's time zone rules, so calendar apps put the event at the right local time (RFC 5545).
ICS_TIMEZONE = [
    "BEGIN:VTIMEZONE", "TZID:America/Los_Angeles",
    "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0800", "TZOFFSETTO:-0700", "TZNAME:PDT", "DTSTART:19700308T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
    "BEGIN:STANDARD", "TZOFFSETFROM:-0700", "TZOFFSETTO:-0800", "TZNAME:PST", "DTSTART:19701101T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD",
    "END:VTIMEZONE",
]


def ics_fold(line):
    """Calendar files allow at most 75 bytes per line; longer lines continue on the next line after a space."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += encoded
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


@bp.route("/events/<int:event_id>/calendar.ics")
@login_required
def calendar_file(event_id):
    """'Add to calendar': a standard .ics file that Apple/Google/Outlook calendars open."""
    event = get_event(event_id)

    def ics_time(value):
        return from_db(value).strftime("%Y%m%dT%H%M%S")

    def ics_text(value):
        return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    link = public_url("events.detail", event_id=event["id"])
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Sportive Circle UW//EN", "CALSCALE:GREGORIAN",
        *ICS_TIMEZONE,
        "BEGIN:VEVENT",
        f"UID:event-{event['id']}@sportivecircle",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID=America/Los_Angeles:{ics_time(event['starts_at'])}",
        f"DTEND;TZID=America/Los_Angeles:{ics_time(event['ends_at'])}",
        f"SUMMARY:{ics_text(event_title(event))}",
        f"LOCATION:{ics_text(event['location'])}",
        f"DESCRIPTION:{ics_text((event['note'] + chr(10) if event['note'] else '') + link)}",
        f"URL:{link}",
        f"STATUS:{'CANCELLED' if event['cancelled'] else 'CONFIRMED'}",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return Response("\r\n".join(ics_fold(line) for line in lines) + "\r\n", mimetype="text/calendar",
                    headers={"Content-Disposition": f"attachment; filename=sportive-circle-{event['id']}.ics"})


@bp.route("/events/<int:event_id>/leave", methods=("POST",))
@login_required
def leave(event_id):
    event = get_event(event_id)
    if event["host_id"] == g.user["id"]:
        flash("You're the host. Cancel the event instead if you can't make it.", "error")
    elif from_db(event["ends_at"]) < now_local():
        flash("This game is over, so it stays in your history.", "info")
    else:
        db = get_db()
        db.execute("DELETE FROM rsvps WHERE event_id = ? AND user_id = ?", (event_id, g.user["id"]))
        db.commit()
        flash("You left the event. Your spot is open for another Dawg.", "info")
    return redirect(url_for("events.detail", event_id=event_id))


# --------------------------------------------------------------- My events

@bp.route("/me/events")
@login_required
def my_events():
    now = {"now": to_db(now_local())}
    hosting = query_events(["e.host_id = :me", "e.cancelled = 0", "e.ends_at >= :now"], now)
    going = query_events(
        ["e.host_id != :me", "e.ends_at >= :now",
         "EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me)"], now)
    past = query_events(
        ["e.ends_at < :now", "e.cancelled = 0",
         "EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me)"],
        now, order="e.starts_at DESC", limit=10)
    return render_template("events/mine.html", hosting=hosting, going=going, past=past)
