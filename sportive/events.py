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
from .mail import send_email
from .ranks import (LEVEL_REQUIREMENT, check_rank_ups, compute_rank, level_allowed, my_ranks, played_together,
                    props_open, sport_rep, vouch_counts)
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
               EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me) AS i_am_going,
               (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id AND r.is_tryout = 1) AS tryouts_used
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


MAX_TRYOUT_SPOTS = 3


def read_ranked_options(form, skill_level):
    """Tryout spots and +1s, from the New event and Need players forms. Returns (tryout_spots, allow_plus_ones, error).

    Both only matter for Intermediate / Competitive games; other levels are open to everyone anyway.
    """
    tryout_raw = form.get("tryout_spots", "0").strip() or "0"
    if not tryout_raw.isdigit() or int(tryout_raw) > MAX_TRYOUT_SPOTS:
        return 0, 1, f"Tryout spots can be 0 to {MAX_TRYOUT_SPOTS}."
    tryout_spots = int(tryout_raw)
    if tryout_spots and skill_level not in LEVEL_REQUIREMENT:
        # Tryouts let lower-ranked players into a harder game. Casual and All levels games
        # are already open to everyone, so there's nothing to try out for.
        return 0, 1, "Tryout spots are only for Intermediate and Competitive games. Everyone can join this one."
    return tryout_spots, 1 if form.get("allow_plus_ones") else 0, None


def tryout_open(event):
    """Is there a free tryout spot for someone below this game's level?"""
    return event["tryout_spots"] > event["tryouts_used"]


MAX_PLUS_ONES_PER_GAME = 2


def my_plus_one_invites():
    """{event_id: invite row with the sponsor's name} for invites sent to me (once per request)."""
    if "plus_one_invites" not in g:
        g.plus_one_invites = {row["event_id"]: row for row in get_db().execute(
            """SELECT i.event_id, i.sponsor_id, u.full_name FROM plus_one_invites i JOIN users u ON u.id = i.sponsor_id
               WHERE i.guest_id = ?""", (g.user["id"],))} if g.get("user") is not None else {}
    return g.plus_one_invites


def my_plus_one_invite(event_id):
    return my_plus_one_invites().get(event_id)


def can_join_or_tryout(event):
    """For templates: 'join', 'plus_one', 'tryout', or None (locked)."""
    if level_allowed(my_ranks(), event["sport"], event["skill_level"])[0]:
        return "join"
    if my_plus_one_invite(event["id"]):
        return "plus_one"
    return "tryout" if tryout_open(event) else None


def plus_one_state(event):
    """What the 'Bring a friend' box on the event page should show for me."""
    db = get_db()
    me = g.user["id"]
    my_rsvp = db.execute("SELECT is_tryout, plus_one_of FROM rsvps WHERE event_id = ? AND user_id = ?",
                         (event["id"], me)).fetchone()
    sent = db.execute(
        """SELECT i.guest_id, u.full_name,
                  EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = i.event_id AND r.user_id = i.guest_id) AS joined
           FROM plus_one_invites i JOIN users u ON u.id = i.guest_id WHERE i.event_id = ? AND i.sponsor_id = ?""",
        (event["id"], me)).fetchone()
    used = db.execute("SELECT COUNT(*) FROM plus_one_invites WHERE event_id = ?", (event["id"],)).fetchone()[0]
    eligible = (event["skill_level"] in LEVEL_REQUIREMENT and event["allow_plus_ones"] and not event["cancelled"]
                and from_db(event["ends_at"]) >= now_local() and my_rsvp is not None
                and not my_rsvp["is_tryout"] and my_rsvp["plus_one_of"] is None
                and level_allowed(my_ranks(), event["sport"], event["skill_level"])[0])
    friends = []
    if eligible and sent is None and used < MAX_PLUS_ONES_PER_GAME:
        friends = db.execute(
            """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f
               JOIN users u ON u.id = CASE WHEN f.requester_id = :me THEN f.addressee_id ELSE f.requester_id END
               WHERE (f.requester_id = :me OR f.addressee_id = :me) AND f.status = 'accepted'
                 AND u.id NOT IN (SELECT user_id FROM rsvps WHERE event_id = :event)
                 AND u.id NOT IN (SELECT guest_id FROM plus_one_invites WHERE event_id = :event)
               ORDER BY u.full_name""", {"me": me, "event": event["id"]}).fetchall()
    return {"eligible": eligible, "sent": sent, "friends": friends,
            "full": used >= MAX_PLUS_ONES_PER_GAME and sent is None}


def round_up_5(dt):
    return dt + timedelta(minutes=-dt.minute % 5)


def insert_event(data):
    db = get_db()
    cur = db.execute(
        """INSERT INTO events (host_id, title, sport, location, starts_at, ends_at, skill_level,
                               max_players, extra_players, note, is_quick, tryout_spots, allow_plus_ones, club_id)
           VALUES (:host_id, :title, :sport, :location, :starts_at, :ends_at, :skill_level,
                   :max_players, :extra_players, :note, :is_quick, :tryout_spots, :allow_plus_ones, :club_id)""",
        {"host_id": g.user["id"], "extra_players": 0, "is_quick": 0, "tryout_spots": 0, "allow_plus_ones": 1,
         "club_id": None, **data},
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
    """Unlock new badges and celebrate rank-ups (with confetti)."""
    new = sync_badges(user_id)
    if len(new) == 1:
        flash(f"New badge unlocked: {new[0].emoji} {new[0].name}!", "celebrate")
    elif new:
        flash(f"{len(new)} new badges unlocked: {' '.join(badge.emoji for badge in new)} "
              "Check them out on your profile!", "celebrate")
    rank_ups = check_rank_ups(user_id, my_ranks())
    if len(rank_ups) == 1:
        flash(rank_ups[0], "celebrate")
    elif rank_ups:
        flash(f"You ranked up in {len(rank_ups)} sports! 🔥 See your ranks on your profile.", "celebrate")


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
    tryout_spots, allow_plus_ones, error = read_ranked_options(form, skill_level)
    if error:
        return None, error

    return {
        "title": title, "sport": sport, "location": location, "skill_level": skill_level,
        "starts_at": to_db(starts), "ends_at": to_db(ends), "max_players": max_players, "note": note,
        "tryout_spots": tryout_spots,
        "allow_plus_ones": allow_plus_ones,
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
            # Club events are for everyone: no ranks, no tryouts, no +1s needed.
            data.update(club_id=club["id"], skill_level="All levels", tryout_spots=0)
        if error is None:
            error = level_allowed(my_ranks(), data["sport"], data["skill_level"])[1]
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
        form = MultiDict({"starts_at": starts, "ends_at": ends, "skill_level": "All levels", "allow_plus_ones": "1",
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
            data.update(skill_level="All levels", tryout_spots=0)
        if error is None and (data["skill_level"], data["sport"]) != (event["skill_level"], event["sport"]):
            error = level_allowed(my_ranks(), data["sport"], data["skill_level"])[1]
        if error is None:
            db = get_db()
            db.execute(
                """UPDATE events SET title = :title, sport = :sport, location = :location,
                       starts_at = :starts_at, ends_at = :ends_at, skill_level = :skill_level,
                       max_players = :max_players, note = :note, tryout_spots = :tryout_spots,
                       allow_plus_ones = :allow_plus_ones
                   WHERE id = :id""",
                {**data, "id": event_id},
            )
            db.commit()
            flash("Event updated.", "success")
            return redirect(url_for("events.detail", event_id=event_id))
        flash(error, "error")
    else:
        form = MultiDict({
            "title": event["title"], "sport": event["sport"], "location": event["location"],
            "skill_level": event["skill_level"], "starts_at": to_form(event["starts_at"]),
            "ends_at": to_form(event["ends_at"]), "note": event["note"],
            "max_players": event["max_players"] or "", "tryout_spots": event["tryout_spots"],
            "allow_plus_ones": "1" if event["allow_plus_ones"] else "",
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


def tell_players_it_was_cancelled(event):
    """Email everyone who joined (except the host), so nobody shows up to an empty field."""
    players = get_db().execute(
        """SELECT u.email, u.full_name FROM rsvps r JOIN users u ON u.id = r.user_id
           WHERE r.event_id = ? AND r.user_id != ?""", (event["id"], event["host_id"])).fetchall()
    title, when = event_title(event), fmt_when(event["starts_at"])
    for player in players:
        try:
            send_email(player["email"], f"Canceled: {title} ({when})",
                       f"Hey {player['full_name'].split()[0]},\n\n"
                       f"Heads up: {event['host_name']} canceled {title} ({when}, {event['location']}).\n\n"
                       f"Find another game: {public_url('events.feed')}\n\nGo Dawgs!\nSportive Circle")
        except Exception:  # one bad address shouldn't stop the others
            log.exception("Couldn't email %s about a canceled event", player["email"])


# ------------------------------------------------------ "Need players" post

@bp.route("/need-players", methods=("GET", "POST"))
@login_required
def quick():
    form = request.form if request.method == "POST" else MultiDict(
        {"starts_in": "30", "duration": "60", "needed": "2", "have": "1", "skill_level": "All levels",
         "tryout_spots": "0", "allow_plus_ones": "1"})
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
        tryout_spots, allow_plus_ones, options_error = read_ranked_options(form, skill_level)

        if sport not in SPORTS:
            error = "Please choose a sport."
        elif location not in LOCATIONS:
            error = "Please choose a location."
        elif location not in SPORT_LOCATIONS[sport]:
            error = f"{SPORTS[sport]} can't be played at {location}. Choose another place."
        elif skill_level not in SKILL_LEVELS:
            error = "Please choose a skill level."
        elif not level_allowed(my_ranks(), sport, skill_level)[0]:
            error = level_allowed(my_ranks(), sport, skill_level)[1]
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
        elif options_error:
            error = options_error
        elif tryout_spots > needed:
            error = (f"You only need {needed} more, so you can have at most {needed} tryout "
                     f"spot{'s' if needed != 1 else ''}.")

        if error is None:
            starts = round_up_5(now_local() + timedelta(minutes=_int(form.get("starts_in"))))
            ends = starts + timedelta(minutes=_int(form.get("duration")))
            event_id = insert_event({
                "title": f"Need {needed} for {SPORTS[sport]}", "sport": sport, "location": location,
                "skill_level": skill_level, "starts_at": to_db(starts), "ends_at": to_db(ends),
                # `have` includes the host, who is counted through their RSVP.
                "max_players": have + needed, "extra_players": have - 1, "note": note, "is_quick": 1,
                "tryout_spots": tryout_spots, "allow_plus_ones": allow_plus_ones,
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
        """SELECT u.id, u.full_name, u.grad_year, u.avatar_updated, u.show_ranks, r.is_tryout, r.plus_one_of
           FROM rsvps r JOIN users u ON u.id = r.user_id
           WHERE r.event_id = ? ORDER BY r.created_at""",
        (event_id,),
    ).fetchall()
    ended = from_db(event["ends_at"]) < now_local()
    sport = event["sport"]
    ranks = {person["id"]: compute_rank(sport, sport_rep(person["id"]).get(sport, 0),
                                        *vouch_counts(person["id"], sport))
             for person in attendees}
    db = get_db()
    props_given = {row["receiver_id"] for row in db.execute(
        "SELECT receiver_id FROM props WHERE event_id = ? AND giver_id = ?", (event_id, g.user["id"]))}
    vouched = {row["receiver_id"] for row in db.execute(
        "SELECT receiver_id FROM vouches WHERE sport = ? AND giver_id = ?", (sport, g.user["id"]))}
    level_ok, level_reason = level_allowed(my_ranks(), sport, event["skill_level"])
    return render_template("events/detail.html", event=event, attendees=attendees, ended=ended,
                           ranks=ranks, props_given=props_given, vouched=vouched,
                           post_game=event["i_am_going"] and props_open(event),
                           level_ok=level_ok, level_reason=level_reason,
                           tryout=not level_ok and tryout_open(event) and not my_plus_one_invite(event_id),
                           my_invite=None if level_ok or event["i_am_going"] else my_plus_one_invite(event_id),
                           plus_one=plus_one_state(event),
                           names={person["id"]: person["full_name"].split()[0] for person in attendees},
                           share_url=public_url("events.detail", event_id=event_id),
                           blocked=is_blocked_between(g.user["id"], event["host_id"]),
                           ranked_game=event["skill_level"] in LEVEL_REQUIREMENT)


@bp.route("/events/<int:event_id>/props/<int:user_id>", methods=("POST",))
@login_required
def give_props(event_id, user_id):
    """🤝 Props: a thumbs-up for a teammate after a game (once per person per game)."""
    event = get_event(event_id)
    if user_id == g.user["id"]:
        flash("Nice try, but you can't give yourself props 😄", "error")
    elif not props_open(event):
        flash("Props can be given after a game ends, for up to a week.", "error")
    elif not played_together(event_id, g.user["id"], user_id):
        flash("You can only give props to people who played in this game with you.", "error")
    else:
        db = get_db()
        cur = db.execute("INSERT OR IGNORE INTO props (event_id, giver_id, receiver_id, created_at) VALUES (?, ?, ?, ?)",
                         (event_id, g.user["id"], user_id, to_db(now_local())))
        db.commit()
        if cur.rowcount:
            flash("Props sent! 🤝 That's how Huskies do it.", "success")
    return redirect(url_for("events.detail", event_id=event_id) + "#post-game")


@bp.route("/events/<int:event_id>/plus-one/<int:friend_id>", methods=("POST",))
@login_required
def invite_plus_one(event_id, friend_id):
    """Bring a friend: invite one friend into a ranked game you're playing in."""
    event = get_event(event_id)
    state = plus_one_state(event)
    if not state["eligible"]:
        flash("Only ranked players going to this game can bring a +1, and only if the host allows it.", "error")
    elif state["sent"] is not None:
        flash("You already invited a friend to this game. One +1 per player!", "error")
    elif state["full"]:
        flash(f"This game already has {MAX_PLUS_ONES_PER_GAME} +1 invites, which is the max.", "error")
    elif friend_id not in {friend["id"] for friend in state["friends"]}:
        flash("You can only bring a friend (someone who accepted your friend request).", "error")
    else:
        db = get_db()
        now = to_db(now_local())
        db.execute("INSERT INTO plus_one_invites (event_id, sponsor_id, guest_id, created_at) VALUES (?, ?, ?, ?)",
                   (event_id, g.user["id"], friend_id, now))
        link = public_url("events.detail", event_id=event_id)
        db.execute("INSERT INTO direct_messages (sender_id, recipient_id, body, created_at) VALUES (?, ?, ?, ?)",
                   (g.user["id"], friend_id,
                    f"🤝 I invited you as my +1 to {event_title(event)} ({fmt_when(event['starts_at'])}). "
                    f"It's a {event['skill_level']} game, but you can come with me! Join here: {link}", now))
        db.commit()
        flash("Invite sent! 🤝 They'll get a message and can join as your +1.", "success")
    return redirect(url_for("events.detail", event_id=event_id) + "#plus-one")


@bp.route("/events/<int:event_id>/plus-one/cancel", methods=("POST",))
@login_required
def cancel_plus_one(event_id):
    db = get_db()
    db.execute("""DELETE FROM plus_one_invites WHERE event_id = ? AND sponsor_id = ?
                  AND guest_id NOT IN (SELECT user_id FROM rsvps WHERE event_id = ?)""",
               (event_id, g.user["id"], event_id))
    db.commit()
    flash("+1 invite canceled.", "info")
    return redirect(url_for("events.detail", event_id=event_id) + "#plus-one")


@bp.route("/events/<int:event_id>/vouch/<int:user_id>", methods=("POST",))
@login_required
def vouch(event_id, user_id):
    """⬆️ Vouch: 'they're ready for the next level' in this sport (once per person per sport)."""
    event = get_event(event_id)
    if user_id == g.user["id"]:
        flash("You can't vouch for yourself. Your teammates have to do that! 😄", "error")
    elif not props_open(event):
        flash("You can vouch for someone after a game ends, for up to a week.", "error")
    elif not played_together(event_id, g.user["id"], user_id):
        flash("You can only vouch for people who played in this game with you.", "error")
    else:
        db = get_db()
        cur = db.execute("INSERT OR IGNORE INTO vouches (sport, giver_id, receiver_id, created_at) VALUES (?, ?, ?, ?)",
                         (event["sport"], g.user["id"], user_id, to_db(now_local())))
        db.commit()
        if cur.rowcount:
            flash(f"Vouch sent! ⬆️ You helped a teammate on their way up in {SPORTS[event['sport']]}.", "success")
    return redirect(url_for("events.detail", event_id=event_id) + "#post-game")


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
    elif (not level_allowed(my_ranks(), event["sport"], event["skill_level"])[0]
          and not tryout_open(event) and not my_plus_one_invite(event_id)):
        flash(level_allowed(my_ranks(), event["sport"], event["skill_level"])[1], "error")
    else:
        below_level = not level_allowed(my_ranks(), event["sport"], event["skill_level"])[0]
        sponsor = my_plus_one_invite(event_id) if below_level else None
        tryout = below_level and sponsor is None
        db = get_db()
        # The capacity check and the insert happen in one statement, so two people
        # clicking "Join" at the same moment can't both take the last spot.
        cur = db.execute(
            """INSERT INTO rsvps (event_id, user_id, created_at, is_tryout, plus_one_of)
               SELECT e.id, :me, :now, :tryout, :sponsor FROM events e
               WHERE e.id = :id AND (e.max_players IS NULL OR
                     e.extra_players + (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id) < e.max_players)
                 AND (:tryout = 0 OR
                      (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id AND r.is_tryout = 1) < e.tryout_spots)""",
            {"me": g.user["id"], "id": event_id, "now": to_db(now_local()), "tryout": int(tryout),
             "sponsor": sponsor["sponsor_id"] if sponsor else None},
        )
        db.commit()
        if cur.rowcount and sponsor:
            flash(f"You're in as {sponsor['full_name'].split()[0]}'s +1 🤝 Have a great game together!", "celebrate")
        elif cur.rowcount and tryout:
            flash("You're in as a tryout 🎟️ Show what you've got, then ask for vouches after the game!", "celebrate")
        elif cur.rowcount:
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
