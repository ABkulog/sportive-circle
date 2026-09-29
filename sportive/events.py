"""Feed, event create/edit/cancel, RSVPs, 'Need players' quick posts, and My events."""
import logging
import secrets
from datetime import datetime, time, timedelta, timezone
from urllib.parse import quote

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.datastructures import MultiDict

from .auth import login_required, safe_next
from .badges import sync_badges
from .clubs import featured_clubs, suggested_clubs
from .constants import (DEFAULT_MAX_HOURS, DEFAULT_PLAYERS, LOCATION_COORDS, OFF_CAMPUS, OPEN_TO_GENDERS, OPEN_TO_LABELS, OPEN_TO_PHRASE,
                        STATED_GENDERS, LOCATIONS, QUICK_DURATIONS, QUICK_START_OPTIONS,
                        SKILL_LEVELS, SPORT_LOCATIONS, SPORT_MAX_HOURS, MAX_PLAYERS, SPORT_TEAM_SIZES, SPORTS)
from .db import get_db, user_sports
from .invites import (HELD, MAX_PARTY, count_wrong_password, held_spots, hold_minutes_left, hold_spots, my_invite,
                      now_param, pending_invites, requested_invites, team_counts, too_many_password_tries)
from .links import public_url
from .sms import text_user
from .reminders import REMIND_CHOICES
from .notifications import mark_seen, notify
from .mail import compose, send_email
from .social import friends_of, is_blocked_between
from .spirit import greeting, top_dawgs
from .textutil import one_line
from .timeutil import fmt_clock, fmt_when, from_db, now_local, parse_form, to_db, to_form

bp = Blueprint("events", __name__)
log = logging.getLogger(__name__)

MIN_PASSWORD, MAX_PASSWORD = 4, 30     # private games
MAX_DAYS_AHEAD = 365
OPEN_SPOT_CHOICES = ("1", "2", "3", "4", "5", "10")  # the "Open spots" filter on Home
QUICK_WINDOW = timedelta(hours=3)      # quick posts starting this soon go to the top of the feed
UP_NEXT_WINDOW = timedelta(hours=2)    # your own events starting this soon get a banner on the feed


# ---------------------------------------------------------------- queries

def query_events(where, params=None, order="e.starts_at", limit=100):
    """Events + host name + how many are going + whether *I* am going.

    `where` is a list of SQL conditions written in this file (never user input);
    user values always go through `params`.
    """
    me = g.user["id"] if g.get("user") is not None else 0  # 0 = a visitor (e.g. opening an invite link)
    params = {"me": me, "hold_now": now_param(), **(params or {})}
    sql = f"""
        SELECT e.*, u.full_name AS host_name, u.avatar_updated AS host_avatar, cl.name AS club_name,
               (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id) AS going_count,
               EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me) AS i_am_going,
               {HELD} AS held_count,
               EXISTS (SELECT 1 FROM invites i WHERE i.event_id = e.id AND i.guest_id = :me
                       AND i.status = 'pending') AS i_am_invited,
               EXISTS (SELECT 1 FROM club_members cm WHERE cm.club_id = e.club_id AND cm.user_id = :me
                       AND cm.role IN ('member', 'officer')) AS i_am_member
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


# SQL for "is this game full?": spots held for invited friends count as taken (for their 30 minutes).
SPOTS_LEFT_SQL = (f"(e.max_players - e.extra_players - {HELD}"
                  " - (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id))")
IS_FULL_SQL = f"(e.max_players IS NOT NULL AND {SPOTS_LEFT_SQL} <= 0)"
# ...and "is it mine?": I host it, I'm going, or a spot is held for me. Needs :me and :hold_now.
IS_MINE_SQL = ("(e.host_id = :me OR EXISTS (SELECT 1 FROM rsvps m WHERE m.event_id = e.id AND m.user_id = :me)"
               " OR EXISTS (SELECT 1 FROM invites mi WHERE mi.event_id = e.id AND mi.guest_id = :me"
               " AND mi.status = 'pending'))")
# Full games are hidden everywhere (nobody can join them), except your own and the Home "Full" tab.
SHOWN_UNLESS_FULL = f"(NOT {IS_FULL_SQL} OR {IS_MINE_SQL})"


def spots_left(event):
    """Open spots anyone can take (held spots for invited friends don't count). None = unlimited."""
    if event["max_players"] is None:
        return None
    return max(event["max_players"] - event["going_count"] - event["extra_players"] - event["held_count"], 0)


def can_quick_join(event):
    """For the Join button on feed cards: private and team games need their page (password, teams)."""
    return (not event["cancelled"] and not event["i_am_going"] and not event["team_size"] and not not_for_me(event)
            and (not event["members_only"] or event["i_am_member"])
            and (event["i_am_invited"] or (not event["is_private"] and spots_left(event) != 0)))


def event_title(event):
    """Need-players posts show a live count ("Need 2 more for Soccer") instead of the saved title."""
    if not event["is_quick"]:
        return event["title"]
    sport = SPORTS[event["sport"]]
    if event["cancelled"] or from_db(event["ends_at"]) < now_local():
        return f"{sport} pickup game"
    if event["is_private"]:
        return f"Private {sport.lower()} game"
    if event["team_size"]:
        return f"{sport} {event['team_size']}v{event['team_size']}: challenge us"
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


def insert_event(data, reserve=()):
    """Save a new game with its host going, and reserve spots for the friends in `reserve` (the caller has
    checked they're friends and that they fit). One commit, so nobody can take those spots in between."""
    db = get_db()
    cur = db.execute(
        """INSERT INTO events (host_id, title, sport, location, starts_at, ends_at, skill_level,
                               max_players, extra_players, note, is_quick, club_id, is_private, password, team_size,
                               open_to, members_only)
           VALUES (:host_id, :title, :sport, :location, :starts_at, :ends_at, :skill_level,
                   :max_players, :extra_players, :note, :is_quick, :club_id, :is_private, :password, :team_size,
                   :open_to, :members_only)""",
        {"host_id": g.user["id"], "extra_players": 0, "is_quick": 0, "club_id": None, "is_private": 0,
         "password": "", "team_size": None, "open_to": "everyone", "members_only": 0, **data},
    )
    # The host is automatically going to their own event (on team 1 in a team vs team game).
    db.execute("INSERT INTO rsvps (event_id, user_id, created_at, team) VALUES (?, ?, ?, ?)",
               (cur.lastrowid, g.user["id"], to_db(now_local()), 1 if data.get("team_size") else None))
    if reserve:
        event = get_event(cur.lastrowid)
        hold_spots(event["id"], g.user["id"], reserve, 1 if data.get("team_size") else None,
                   f"{g.user['full_name'].split()[0]} wants you in {event_title(event)} "
                   f"({fmt_when(event['starts_at'])}). You down?", url_for("events.detail", event_id=event["id"]))
    db.commit()
    return cur.lastrowid


def read_game_options(form, sport, event=None):
    """Private game (password) and format (regular or team vs team), from the New event and Need players forms.
    Returns (is_private, password, team_size, error). The format can't change after the game is made."""
    is_private = 1 if form.get("is_private") == "1" else 0   # club events can also say "members"
    password = one_line(form.get("password")) if is_private else ""
    if is_private and not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        return 0, "", None, f"Pick a password for your private game ({MIN_PASSWORD} to {MAX_PASSWORD} characters)."
    team_size = event["team_size"] if event is not None else None
    team_raw = form.get("team_size", "").strip()
    sizes = SPORT_TEAM_SIZES.get(sport, [])
    if event is None and team_raw:
        if not sizes:
            return 0, "", None, f"{SPORTS[sport]} isn't played team vs team. Pick Regular game."
        if not team_raw.isdigit() or int(team_raw) not in sizes:
            return 0, "", None, f"{SPORTS[sport]} teams can be {', '.join(f'{n}v{n}' for n in sizes)}."
        team_size = int(team_raw)
    if event is not None and team_size and team_size not in sizes:
        return 0, "", None, f"A {team_size}v{team_size} game can't be changed to {SPORTS[sport]}."
    if is_private and team_size:
        return 0, "", None, "Team vs team is for games anyone can join. Pick Anyone, or a regular game."
    return is_private, password, team_size, None


def suggested_password():
    """A private game's password, filled in for the host (they can change it): easy to say out loud."""
    return f"dawgs{secrets.randbelow(9000) + 1000}"


def created_message(is_private, reserve, public_text):
    if is_private:
        return "Your private game is up! Send the invite link to your friends." if not reserve else \
            "Your private game is up! Your friends got an invite. Send the link to anyone else."
    return public_text + (" Your friends' spots are held for 30 minutes." if reserve else "")


def read_reservations(form, room):
    """Friends the host picked to reserve spots for. Returns (friend ids, error). `room` = spots they can use."""
    chosen = list(dict.fromkeys(int(value) for value in form.getlist("reserve") if value.isdigit()))
    friends = {friend["id"] for friend in friends_of(g.user["id"])}
    if any(friend_id not in friends for friend_id in chosen):
        return [], "You can only reserve spots for your friends."
    if len(chosen) > MAX_PARTY:
        return [], f"You can reserve up to {MAX_PARTY} spots at once."
    if len(chosen) > room:
        return [], f"There's only room to reserve {room} spot{'s' if room != 1 else ''} for friends."
    return chosen, None


# -------------------------------------------------------------------- feed

# A club's members-only events only show up for its members (and on the club's own page).
MEMBERS_ONLY_FOR_MEMBERS = """(e.members_only = 0 OR EXISTS (SELECT 1 FROM club_members cm WHERE cm.club_id = e.club_id
                                                              AND cm.user_id = :me AND cm.role IN ('member', 'officer')))"""

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
    filters = {key: request.args.get(key, "") for key in ("scope", "sport", "location", "skill", "when", "open")}
    if filters["scope"] not in ("interests", "all", "full"):
        filters["scope"] = "interests" if my_sports else "all"

    now = now_local()
    where = ["e.cancelled = 0", "e.ends_at >= :now", NOT_BLOCKED, games_open_to_me(), MEMBERS_ONLY_FOR_MEMBERS]
    params = {"now": to_db(now)}

    if filters["sport"] in SPORTS:
        where.append("e.sport = :sport")
        params["sport"] = filters["sport"]
    elif filters["scope"] == "interests" and my_sports:
        names = [f":s{i}" for i in range(len(my_sports))]
        where.append(f"e.sport IN ({', '.join(names)})")
        params.update({f"s{i}": sport for i, sport in enumerate(my_sports)})
    # Full games (reserved spots count) are hidden except in the "Full" tab. Your own games always show.
    where.append(f"({IS_FULL_SQL} AND NOT {IS_MINE_SQL})" if filters["scope"] == "full" else SHOWN_UNLESS_FULL)
    if filters["location"] in LOCATIONS:
        where.append("e.location = :location")
        params["location"] = filters["location"]
    if filters["skill"] in SKILL_LEVELS:
        where.append("e.skill_level = :skill")
        params["skill"] = filters["skill"]
    if filters["open"] in OPEN_SPOT_CHOICES:
        # "We're a group of 5": games with at least that many spots anyone can take right now.
        where.append(f"(e.max_players IS NULL OR {SPOTS_LEFT_SQL} >= :min_open)")
        params["min_open"] = int(filters["open"])
    else:
        filters["open"] = ""
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
            ["e.cancelled = 0", "e.is_quick = 1", "e.ends_at >= :now", "e.starts_at <= :soon", NOT_BLOCKED,
             games_open_to_me(),
             # a private post isn't a call to everyone: only its players and invited friends see it up top
             "(e.is_private = 0 OR EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me)"
             " OR EXISTS (SELECT 1 FROM invites i WHERE i.event_id = e.id AND i.guest_id = :me AND i.status = 'pending'))"],
            {"now": to_db(now), "soon": to_db(now + QUICK_WINDOW)},
            limit=10,
        )
        if spots_left(e) != 0 or e["i_am_going"] or e["i_am_invited"]
    ]
    shown = {e["id"] for e in need_players}
    events = [e for e in events if e["id"] not in shown]

    up_next = query_events(
        ["e.cancelled = 0", "e.ends_at >= :now", "e.starts_at <= :soon",
         "EXISTS (SELECT 1 FROM rsvps r WHERE r.event_id = e.id AND r.user_id = :me)"],
        {"now": to_db(now), "soon": to_db(now + UP_NEXT_WINDOW)}, limit=1)

    celebrate_progress(g.user["id"])
    mark_seen("need_players")
    return render_template("events/feed.html", events=events, need_players=need_players,
                           filters=filters, my_sports=my_sports, up_next=up_next[0] if up_next else None,
                           hello=greeting(g.user["full_name"].split()[0]), top_dawgs=top_dawgs(now=now),
                           club_picks=suggested_clubs(g.user["id"], my_sports))


# ---------------------------------------------------------- create / edit

def read_event_form(form, event=None):
    """Validate the create/edit form. Returns (data, error)."""
    title = one_line(form.get("title"))
    sport = form.get("sport", "")
    location = form.get("location", "")
    skill_level = form.get("skill_level") or "All levels"  # not asked for private games
    note = form.get("note", "").strip()
    now = now_local()

    if len(title) > 80:
        return None, "Event name is too long (80 characters max)."
    if sport not in SPORTS:
        return None, "Please choose a sport."
    if location not in LOCATIONS:
        return None, "Please choose a location."
    if location not in SPORT_LOCATIONS[sport]:
        return None, f"{SPORTS[sport]} can't be played at {location}. Choose another place."
    if location == OFF_CAMPUS and not note:
        return None, "Off campus: add where in the note, so people can find you."
    if skill_level not in SKILL_LEVELS:
        return None, "Please choose a skill level."
    title = title or default_title(sport, location)
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
    max_hours = SPORT_MAX_HOURS.get(sport, DEFAULT_MAX_HOURS)
    if ends - starts > timedelta(hours=max_hours):
        longest = f"{max_hours // 24} days" if max_hours % 24 == 0 else f"{max_hours} hours"
        return None, f"{SPORTS[sport]} events can be at most {longest} long."
    if ends <= now:
        return None, "The end time has already passed."
    start_changed = event is None or to_db(starts) != event["starts_at"]
    if start_changed and starts < now:
        return None, "Event date can't be before now."
    if starts > now + timedelta(days=MAX_DAYS_AHEAD):
        return None, "Event date can't be more than a year away."

    if len(note) > 500:
        return None, "Note is too long (500 characters max)."

    is_private, password, team_size, error = read_game_options(form, sport, event)
    if error:
        return None, error
    max_players, extra_players, error = read_players(form, sport, team_size, event)
    if error:
        return None, error
    open_to, error = read_open_to(form, is_private)
    if error:
        return None, error

    return {
        "title": title, "sport": sport, "location": location, "skill_level": skill_level,
        "starts_at": to_db(starts), "ends_at": to_db(ends), "max_players": max_players,
        "extra_players": extra_players, "note": note,
        "is_private": is_private, "password": password, "team_size": team_size, "open_to": open_to,
    }, None


def read_open_to(form, is_private):
    """Who an open game is for (private games are for whoever the host invites). Returns (open_to, error)."""
    open_to = form.get("open_to") or "everyone"
    if is_private:
        return "everyone", None
    if open_to not in OPEN_TO_LABELS:  # (an older game may still say "Women & nonbinary")
        return "everyone", "Please pick who the game is open to."
    return open_to, None


def not_for_me(event):
    """Why this game isn't open to me, from the gender I chose on my profile (None = it's open to me)."""
    groups = OPEN_TO_GENDERS.get(event["open_to"])
    gender = g.user["gender"] if g.get("user") is not None else ""
    if groups and gender in STATED_GENDERS and gender not in groups:
        return f"This game is for {OPEN_TO_PHRASE[event['open_to']]}."
    return None


def join_confirm(event):
    """For the Join buttons: people who left gender blank are asked to confirm a game that's for a group."""
    gender = g.user["gender"] if g.get("user") is not None else ""
    if event["open_to"] in OPEN_TO_GENDERS and gender not in STATED_GENDERS:
        return f"This game is for {OPEN_TO_PHRASE[event['open_to']]}. Join?"
    return ""


def games_open_to_me():
    """SQL: leave out games whose group doesn't include the gender on my profile (nothing is hidden if it's blank)."""
    gender = g.user["gender"] if g.get("user") is not None else ""
    if gender not in STATED_GENDERS:
        return "1"
    fits = ["everyone"] + [key for key, genders in OPEN_TO_GENDERS.items() if gender in genders]
    return f"e.open_to IN ({', '.join(repr(key) for key in fits)})"


def default_title(sport, location):
    """A name for games created without one: "Basketball at the IMA", "Soccer at Denny Field"."""
    place = location.split(" (")[0]
    place = {"IMA": "the IMA", "Online": "online"}.get(place, place)
    if location == OFF_CAMPUS:
        return f"{SPORTS[sport]} off campus"
    return f"{SPORTS[sport]} {'' if place == 'online' else 'at '}{place}"


def read_players(form, sport, team_size, event=None):
    """How many can play, and how many friends not on the app are already coming.
    Returns (max_players, extra_players, error). "Players" includes the host; in team vs team it's both teams."""
    # Friends who aren't on the app get an invite link after posting (so they're counted once they join).
    extra = event["extra_players"] if event is not None else 0
    if team_size:
        return 2 * team_size, 0, None
    raw = form.get("players", "").strip()
    players = int(raw) if raw.isdigit() else (DEFAULT_PLAYERS.get(sport, 10) if not raw else 0)
    if not 2 <= players <= MAX_PLAYERS:
        return None, 0, f"Pick 2 to {MAX_PLAYERS} participants (you included)."
    taken = (event["going_count"] + event["extra_players"]) if event is not None else 1 + extra
    if players < taken:
        return None, 0, (f"{taken} people are already in, so it can't be fewer players than that." if event
                         else "That's more people than participants.")
    return players, extra, None


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
        repeat = _int(form.get("repeat")) or 1
        if error is None and club is not None:
            # Club events are open to all levels; they can be for members only, and repeat weekly (practices).
            data.update(club_id=club["id"], skill_level="All levels",
                        members_only=1 if form.get("is_private") == "members" else 0)
            if not 1 <= repeat <= MAX_REPEAT_WEEKS:
                error = f"A club event can repeat for up to {MAX_REPEAT_WEEKS} weeks."
        elif error is None:
            repeat = 1
        if error is None:
            duplicate = get_db().execute(
                "SELECT 1 FROM events WHERE host_id = ? AND title = ? AND starts_at = ? AND cancelled = 0",
                (g.user["id"], data["title"], data["starts_at"]),
            ).fetchone()
            if duplicate:
                error = "This event has already been created."
        if error is None:
            room = data["team_size"] - 1 if data["team_size"] else data["max_players"] - 1 - data["extra_players"]
            reserve, error = read_reservations(form, room)
        if error is None:
            event_id = insert_event(data, reserve)
            for week in range(1, repeat):  # the same practice every week after the first
                later = dict(data, starts_at=to_db(from_db(data["starts_at"]) + timedelta(weeks=week)),
                             ends_at=to_db(from_db(data["ends_at"]) + timedelta(weeks=week)))
                insert_event(later)
            if club is not None:
                post_club_event(club, event_id, data, repeat)
                flash(f"Posted {repeat} weekly events. Your followers see it in Club updates." if repeat > 1 else
                      "Posted! Your followers see it in Club updates.", "celebrate")
            else:
                flash(created_message(data["is_private"], reserve, "Your game is up!"), "celebrate")
            return redirect(url_for("events.detail", event_id=event_id))
        flash(error, "error")
    else:
        starts, ends = default_times()
        form = MultiDict({"starts_at": starts, "ends_at": ends, "skill_level": "All levels",
                          "password": suggested_password(),
                          "sport": request.args.get("sport", "") or (club["sport"] if club else "")})
    return render_template("events/form.html", form=form, event=None, club=club, friends=friends_of(g.user["id"]),
                           min_start=now_local().strftime("%Y-%m-%dT%H:%M"))


MAX_REPEAT_WEEKS = 12  # about a quarter of weekly practices


def post_club_event(club, event_id, data, repeat):
    """A new club event goes in the club's updates, so followers and members hear about it (Clubs tab)."""
    when = fmt_when(data["starts_at"])
    if repeat > 1:
        starts = from_db(data["starts_at"])
        text = (f"New: {data['title']}, every {starts.strftime('%A')} at {fmt_clock(data['starts_at'])} "
                f"for {repeat} weeks, starting {when} · {data['location']}")
    else:
        text = f"New event: {data['title']} · {when} · {data['location']}"
    if data.get("members_only"):
        text += " (members only)"
    get_db().execute("INSERT INTO club_posts (club_id, author_id, body, created_at, event_id) VALUES (?, ?, ?, ?, ?)",
                     (club["id"], g.user["id"], text, to_db(now_local()), event_id))
    get_db().commit()


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
        flash("This game was canceled, so it can't be edited.", "error")
        return redirect(url_for("events.detail", event_id=event_id))
    if request.method == "POST":
        form = request.form
        data, error = read_event_form(form, event)
        if error is None and event["club_id"]:
            data.update(skill_level="All levels", members_only=1 if form.get("is_private") == "members" else 0)
        elif error is None:
            data.update(members_only=0)
        if error is None:
            db = get_db()
            db.execute(
                """UPDATE events SET title = :title, sport = :sport, location = :location,
                       starts_at = :starts_at, ends_at = :ends_at, skill_level = :skill_level,
                       max_players = :max_players, note = :note, is_private = :is_private, password = :password,
                       open_to = :open_to, members_only = :members_only
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
            "players": event["max_players"] or "",
            "is_private": "1" if event["is_private"] else ("members" if event["members_only"] else ""),
            "password": event["password"], "open_to": event["open_to"],
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
    flash("Canceled. Everyone who joined was told.", "info")
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
        notify(player["id"], "game_updates", f"{host} changed {title}: {', '.join(changes)}", link,
               key=f"change:{event['id']}")
    if any(change.startswith(("new time", "new place")) for change in changes):
        for player in players:
            text_user(player["id"], f"{host} changed {title}: now {fmt_when(data['starts_at'])} at {data['location']}. "
                                    f"{public_url('events.detail', event_id=event['id'])}")
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
               url_for("events.feed"), key=f"change:{event['id']}")
    get_db().commit()
    for player in players:
        text_user(player["id"], f"{event['host_name'].split()[0]} canceled {title} ({when}).")
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
        {"starts_in": "30", "duration": "60", "skill_level": "All levels", "password": suggested_password()})
    if request.method == "POST":
        error = None
        sport = form.get("sport", "")
        location = form.get("location", "")
        skill_level = form.get("skill_level") or "All levels"  # not asked for private games
        note = form.get("note", "").strip()
        starts_in = dict(QUICK_START_OPTIONS).get(_int(form.get("starts_in")))
        duration = dict(QUICK_DURATIONS).get(_int(form.get("duration")))
        is_private, password, team_size, max_players, extra, reserve = 0, "", None, 0, 0, []

        if sport not in SPORTS:
            error = "Please choose a sport."
        elif location not in LOCATIONS:
            error = "Please choose a location."
        elif location not in SPORT_LOCATIONS[sport]:
            error = f"{SPORTS[sport]} can't be played at {location}. Choose another place."
        elif location == OFF_CAMPUS and not note:
            error = "Off campus: add where in the note, so people can find you."
        elif skill_level not in SKILL_LEVELS:
            error = "Please choose a skill level."
        elif starts_in is None or duration is None:
            error = "Please choose when you're playing."
        elif len(note) > 500:
            error = "Note is too long (500 characters max)."
        open_to = "everyone"
        if error is None:
            is_private, password, team_size, error = read_game_options(form, sport)
        if error is None:
            open_to, error = read_open_to(form, is_private)
        if error is None:
            max_players, extra, error = read_players(form, sport, team_size)
        if error is None:
            room = team_size - 1 if team_size else max_players - 1 - extra
            reserve, error = read_reservations(form, room)
            if error and is_private:
                error = error.replace("reserve", "invite")
        needed = (max_players or 0) - 1 - extra - len(reserve)
        if error is None and needed < 1 and not team_size:
            error = "Everyone's already coming, so there's no one to find. Pick more participants."

        if error is None:
            starts = round_up_5(now_local() + timedelta(minutes=_int(form.get("starts_in"))))
            ends = starts + timedelta(minutes=_int(form.get("duration")))
            event_id = insert_event({
                "title": f"{team_size}v{team_size} {SPORTS[sport]}" if team_size else f"Need {needed} for {SPORTS[sport]}",
                "sport": sport, "location": location,
                "skill_level": skill_level, "starts_at": to_db(starts), "ends_at": to_db(ends),
                "max_players": max_players, "extra_players": extra, "note": note, "is_quick": 1,
                "is_private": is_private, "password": password, "team_size": team_size, "open_to": open_to,
            }, reserve)
            flash(created_message(is_private, reserve, "Posted! It's at the top of everyone's feed."), "celebrate")
            return redirect(url_for("events.detail", event_id=event_id))
        flash(error, "error")
    return render_template("events/quick.html", form=form, start_options=QUICK_START_OPTIONS,
                           durations=QUICK_DURATIONS, friends=friends_of(g.user["id"]))


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
    me = g.user["id"]
    attendees = get_db().execute(
        """SELECT u.id, u.full_name, u.grad_year, u.avatar_updated, r.team
           FROM rsvps r JOIN users u ON u.id = r.user_id
           WHERE r.event_id = ? ORDER BY r.created_at""",
        (event_id,),
    ).fetchall()
    invite = None if event["i_am_going"] else my_invite(event_id, me)
    my_team = next((person["team"] for person in attendees if person["id"] == me), None)
    teams = None
    if event["team_size"]:
        counts = team_counts(event_id)
        teams = {team: {"players": [p for p in attendees if p["team"] == team], "count": counts[team],
                        "held": held_spots(event_id, team=team)} for team in (1, 2)}
    my_rsvp = get_db().execute("SELECT remind_minutes FROM rsvps WHERE event_id = ? AND user_id = ?",
                               (event_id, me)).fetchone()
    return render_template("events/detail.html", event=event, attendees=attendees,
                           my_reminder=my_rsvp["remind_minutes"] if my_rsvp else None, remind_choices=REMIND_CHOICES,
                           ended=from_db(event["ends_at"]) < now_local(),
                           share_url=public_url("events.detail", event_id=event_id),
                           blocked=is_blocked_between(me, event["host_id"]),
                           invite=invite, hold_minutes=hold_minutes_left(invite),
                           invited=pending_invites(event_id), teams=teams, my_team=my_team,
                           requests=requested_invites(event_id) if event["i_am_going"] else [],
                           # my own held spot is still mine to take, even if the game looks full to others
                           spots_for_me=None if spots_left(event) is None
                           else spots_left(event) + (1 if hold_minutes_left(invite) else 0))


def join_problem(event, password=None):
    """Why I can't join this game right now (None = I can). Checks everything except the capacity,
    which try_join checks in the same statement that adds the player."""
    me = g.user["id"]
    invite = my_invite(event["id"], me)
    if event["cancelled"]:
        return "This game was canceled."
    if from_db(event["ends_at"]) < now_local():
        return "This game already ended."
    if event["i_am_going"]:
        return "You're already going."
    if is_blocked_between(me, event["host_id"]):
        # Blocking means no contact at all, and that includes showing up to each other's games.
        return "You can't join this game."
    if not_for_me(event):
        return not_for_me(event)
    if event["members_only"] and not event["i_am_member"]:
        return f"This event is for {event['club_name']} members."
    if event["team_size"] and invite is None:
        return "Team games are invite-only. Challenge them with your own team, or ask a player to invite you."
    if event["is_private"] and invite is None:
        if too_many_password_tries(event["id"], me):
            return "Too many wrong passwords. Try again in an hour, or ask to be invited."
        if not password or not secrets.compare_digest(password.strip(), event["password"]):
            count_wrong_password(event["id"], me)
            return "That's not the password." if password else "This game is private. Enter the password."
    return None


def try_join(event, password=None, team=None):
    """Join (or explain why not). Returns (joined, message). Uses my held spot if I was invited."""
    problem = join_problem(event, password)
    if problem:
        return False, problem
    me = g.user["id"]
    invite = my_invite(event["id"], me)
    team = invite["team"] if invite and invite["team"] else team
    db = get_db()
    # The capacity check and the insert happen in one statement, so two people tapping "Join" at the
    # same moment can't both take the last spot. Spots held for other invited friends don't count as open.
    cur = db.execute(
        f"""INSERT INTO rsvps (event_id, user_id, created_at, team)
            SELECT e.id, :me, :now, :team FROM events e
            WHERE e.id = :id AND (e.max_players IS NULL OR
                  e.extra_players + (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id)
                  + ({HELD} - (SELECT COUNT(*) FROM invites o WHERE o.event_id = e.id AND o.guest_id = :me
                                AND o.status = 'pending' AND o.expires_at > :hold_now)) < e.max_players)
              AND (:team IS NULL OR e.team_size IS NULL OR
                   (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id AND r.team = :team)
                   + (SELECT COUNT(*) FROM invites t WHERE t.event_id = e.id AND t.team = :team AND t.guest_id != :me
                      AND t.status = 'pending' AND t.expires_at > :hold_now) < e.team_size)""",
        {"me": me, "id": event["id"], "now": to_db(now_local()), "hold_now": now_param(), "team": team})
    if not cur.rowcount:
        db.commit()
        return False, "Sorry, this game is full."
    if invite:
        db.execute("UPDATE invites SET status = 'accepted' WHERE id = ?", (invite["id"],))
        notify(invite["inviter_id"], "invites", f"{g.user['full_name'].split()[0]} is in for {event_title(event)}.",
               url_for("events.detail", event_id=event["id"]), key=f"reply:{event['id']}:{me}")
    db.commit()
    return True, "You're in! See you there."


@bp.route("/events/<int:event_id>/join", methods=("POST",))
@login_required
def join(event_id):
    event = get_event(event_id)
    joined, message = try_join(event, request.form.get("password"))
    flash(message, "celebrate" if joined else ("info" if message == "You're already going." else "error"))
    if joined:
        clash = overlapping_event(event)
        if clash:
            flash(f"Heads up: this overlaps with “{event_title(clash)}” ({fmt_clock(clash['starts_at'])}), "
                  "which you're also going to.", "info")
    if request.form.get("next") and (joined or not event["is_private"]):  # joined from a feed card: stay there
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


@bp.route("/events/<int:event_id>/reminder", methods=("POST",))
@login_required
def set_reminder(event_id):
    """Each player picks when their reminder email comes: 1 hour or 30 min before, or none."""
    minutes = request.form.get("remind", type=int)
    if minutes not in REMIND_CHOICES:
        abort(400)
    get_db().execute("UPDATE rsvps SET remind_minutes = ? WHERE event_id = ? AND user_id = ?",
                     (minutes, event_id, g.user["id"]))
    get_db().commit()
    return redirect(url_for("events.detail", event_id=event_id))


@bp.route("/events/<int:event_id>/leave", methods=("POST",))
@login_required
def leave(event_id):
    event = get_event(event_id)
    if event["host_id"] == g.user["id"]:
        flash("You're the host. Cancel the game instead.", "error")
    elif from_db(event["ends_at"]) < now_local():
        flash("This game is over, so it stays in your history.", "info")
    else:
        db = get_db()
        db.execute("DELETE FROM rsvps WHERE event_id = ? AND user_id = ?", (event_id, g.user["id"]))
        db.commit()
        flash("You left. Your spot is open again.", "info")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.route("/events/<int:event_id>/players/<int:user_id>/remove", methods=("POST",))
@login_required
def remove_player(event_id, user_id):
    """The host takes someone off their game (e.g. they don't fit who it's for). They get a notice."""
    event = get_event(event_id, host_only=True)
    if user_id == g.user["id"] or from_db(event["ends_at"]) < now_local():
        abort(400)
    db = get_db()
    cur = db.execute("DELETE FROM rsvps WHERE event_id = ? AND user_id = ?", (event_id, user_id))
    if cur.rowcount:
        notify(user_id, "game_updates", f"{g.user['full_name'].split()[0]} took you off {event_title(event)}.",
               url_for("events.feed"), key=f"change:{event_id}")
    db.commit()
    flash("Removed from the game." if cur.rowcount else "They're not in this game.", "info")
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
