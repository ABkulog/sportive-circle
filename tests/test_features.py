"""Step definitions for the Gherkin scenarios in tests/features/*.feature.

Each scenario is written in plain English (tagged with a requirement ID from docs/requirements.md);
the functions below turn every sentence into real requests against the app. Every person in a
scenario gets their own test client, like their own phone, so multi-person flows work naturally.
"""
import html
import re
from datetime import timedelta
from io import BytesIO

import pytest
from PIL import Image
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import make_image
from sportive.db import get_db
from sportive.reminders import send_due_reminders
from sportive.timeutil import from_db, now_local, to_db

scenarios("features")

PASSWORD = "purple-and-gold"
IMA = "IMA (Intramural Activities Building)"


# ------------------------------------------------------------------ the world

class Husky:
    def __init__(self, name, client):
        self.name, self.client = name, client
        self.first = name.split()[0]
        self.email = re.sub(r"[^a-z]", "", self.first.lower()) + "@uw.edu"
        self.password = PASSWORD
        self.id = None


class World:
    """Everything a scenario needs: the app, the people in it, and the last page someone saw."""

    def __init__(self, app):
        self.app = app
        self.people = {}
        self.games = {}           # host's first name -> event id
        self.response = None      # the last page anyone looked at ("they see ...")
        self.client = None        # the client that saw it
        self.last_dm = None

    def person(self, name):
        return self.people.get(name) or next(p for p in self.people.values() if p.first == name)

    def db(self, sql, args=()):
        with self.app.app_context():
            db = get_db()
            rows = db.execute(sql, args).fetchall()
            db.commit()
            return rows

    def outbox(self):
        return self.app.extensions.get("outbox", [])

    def saw(self, response, client):
        self.response, self.client = response, client
        return response

    def text(self):
        return html.unescape(self.response.get_data(as_text=True))

    def visible_text(self):
        """What a person reads: tags removed, spaces collapsed ("From <a>Maya</a>" -> "From Maya")."""
        page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", self.response.get_data(as_text=True), flags=re.S)
        return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.fixture
def world(app):
    app.config["CSRF_ENABLED"] = False
    return World(app)


def sign_up(world, client, email, name="Dubs Husky", birth_date="2005-01-15"):
    return world.saw(client.post("/signup", data={
        "full_name": name, "email": email, "password": PASSWORD, "password2": PASSWORD,
        "birth_date": birth_date, "grad_year": "2028", "sports": ["basketball", "soccer"],
    }, follow_redirects=True), client)


def emailed_code(world, email):
    message = [m for m in world.outbox() if m["to"] == email][-1]
    return re.search(r"\b(\d{6})\b", message["subject"]).group(1)


def add_husky(world, name):
    person = Husky(name, world.app.test_client())
    sign_up(world, person.client, person.email, name=name)
    person.client.post("/verify", data={"code": emailed_code(world, person.email)})
    person.client.post("/profile/photo", data={"photo": (BytesIO(make_image()), "me.png")},
                       content_type="multipart/form-data")
    person.id = world.db("SELECT id FROM users WHERE email = ?", (person.email,))[0]["id"]
    world.people[name] = person
    return person


def event_data(**overrides):
    tomorrow = now_local() + timedelta(days=1)
    data = {"title": "Pickup 5v5", "sport": "basketball", "location": IMA, "skill_level": "All levels",
            "starts_at": tomorrow.strftime("%Y-%m-%dT%H:%M"),
            "ends_at": (tomorrow + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"), "players": "", "note": ""}
    data.update(overrides)
    return data


def host_game(world, host_name, **overrides):
    host = world.person(host_name)
    response = host.client.post("/events/new", data=event_data(**overrides))
    world.saw(response, host.client)
    match = re.search(r"/events/(\d+)", response.headers.get("Location", ""))
    if match:
        world.games[host.first] = int(match.group(1))
    return response


def insert_game(world, host, players, starts, rsvp_time=None, sport="basketball"):
    ends = starts + timedelta(hours=1)
    with world.app.app_context():
        db = get_db()
        cur = db.execute(
            "INSERT INTO events (host_id, title, sport, location, starts_at, ends_at, skill_level)"
            " VALUES (?, 'Pickup 5v5', ?, ?, ?, ?, 'All levels')", (host.id, sport, IMA, to_db(starts), to_db(ends)))
        for player in [host, *players]:
            db.execute("INSERT INTO rsvps (event_id, user_id, created_at) VALUES (?, ?, ?)",
                       (cur.lastrowid, player.id, to_db(rsvp_time or starts - timedelta(days=1))))
        db.commit()
    world.games[host.first] = cur.lastrowid


CLUB = {"sport": "spikeball", "description": "Casual roundnet on the Quad. Everyone welcome, nets provided!",
        "meets": "Tuesdays 5-7 PM", "location": "The Quad", "club_kind": "rso",
        "verification_url": "https://huskylink.washington.edu/organization/uwspikeball", "officer_role": "President",
        "member_estimate": "30", "focus": "recreational", "joining": "open", "experience": "none",
        "who_can_join": "everyone", "dues": "Free", "gear": "Nets provided", "how_to_join": "Come to any practice!",
        "club_email": "spike@uw.edu", "join_question": "Played before?", "attest": "1", "instagram": "uwspikeball",
        "contact_phone_country": "US", "contact_phone": "206-555-0142"}


def club_id(world, club):
    return world.db("SELECT id FROM clubs WHERE name = ?", (club,))[0]["id"]


# ------------------------------------------------------------------ Given

@given(parsers.parse('"{name}" is a Husky'))
def given_husky(world, name):
    add_husky(world, name)


@given(parsers.parse('"{name}" is an admin'))
def given_admin(world, name):
    person = add_husky(world, name)
    world.app.config["ADMIN_EMAILS"] = person.email


@given(parsers.parse('"{host}" hosts a basketball game tomorrow'))
@when(parsers.parse('"{host}" hosts a basketball game tomorrow'))
def hosts_game(world, host):
    host_game(world, host)


@given(parsers.parse('"{host}" hosts a tennis game for {n:d} players tomorrow'))
def hosts_tennis(world, host, n):
    host_game(world, host, sport="tennis", location="IMA South Tennis Courts", players=str(n), title="Doubles")


@given(parsers.parse('"{guest}" joins {host}\'s game'))
@when(parsers.parse('"{guest}" joins {host}\'s game'))
def joins_game(world, guest, host):
    person = world.person(guest)
    world.saw(person.client.post(f"/events/{world.games[host]}/join", follow_redirects=True), person.client)


@given(parsers.parse('"{host}" hosted a basketball game yesterday that "{player}" played in'))
def played_yesterday(world, host, player):
    insert_game(world, world.person(host), [world.person(player)], now_local() - timedelta(days=1))


@given(parsers.parse('"{host}" hosts a basketball game starting in 45 minutes that "{player}" joined yesterday'))
def game_soon(world, host, player):
    insert_game(world, world.person(host), [world.person(player)], now_local() + timedelta(minutes=45),
                rsvp_time=now_local() - timedelta(days=1))


@given(parsers.parse('"{a}" and "{b}" are friends'))
def given_friends(world, a, b):
    first, second = world.person(a), world.person(b)
    first.client.post(f"/friends/request/{second.id}")
    second.client.post(f"/friends/accept/{first.id}")


@given(parsers.parse('"{name}" runs the approved club "{club}"'))
def runs_club(world, name, club):
    person = world.person(name)
    person.client.post("/clubs/new", data={**CLUB, "name": club})
    world.db("UPDATE clubs SET status = 'approved' WHERE name = ?", (club,))


# ------------------------------------------------------------------ When: accounts

@when(parsers.parse('someone signs up with the email "{email}"'))
def someone_signs_up(world, email):
    sign_up(world, world.app.test_client(), email)


@when(parsers.parse('someone born {years:d} years ago signs up with the email "{email}"'))
def child_signs_up(world, email, years):
    born = now_local().date().replace(year=now_local().year - years, day=1)
    sign_up(world, world.app.test_client(), email, birth_date=born.isoformat())


@when(parsers.parse('they enter the code that was emailed to "{email}"'))
def enter_emailed_code(world, email):
    world.saw(world.client.post("/verify", data={"code": emailed_code(world, email)}, follow_redirects=True),
              world.client)


@when(parsers.parse('they enter the code "{code}"'))
def enter_code(world, code):
    world.saw(world.client.post("/verify", data={"code": code}, follow_redirects=True), world.client)


@when(parsers.parse('they tap "Add later"'))
def add_later(world):
    world.saw(world.client.post("/profile/photo/skip", follow_redirects=True), world.client)


def log_in(world, person, password):
    client = world.app.test_client()
    return world.saw(client.post("/login", data={"email": person.email, "password": password},
                                 follow_redirects=True), client)


@when(parsers.parse('"{name}" logs in with the wrong password {times:d} times'))
def wrong_password(world, name, times):
    for _ in range(times):
        log_in(world, world.person(name), "not-my-password")


@when(parsers.parse('"{name}" logs in with the right password'))
def right_password(world, name):
    log_in(world, world.person(name), world.person(name).password)


@when(parsers.parse('"{name}" asks to reset her password'))
def ask_reset(world, name):
    client = world.app.test_client()
    world.saw(client.post("/forgot", data={"email": world.person(name).email}, follow_redirects=True), client)


@when(parsers.parse('someone asks to reset the password for "{email}"'))
def ask_reset_unknown(world, email):
    client = world.app.test_client()
    world.saw(client.post("/forgot", data={"email": email}, follow_redirects=True), client)


@when(parsers.parse('"{name}" enters the reset code and the new password "{password}"'))
def enter_reset(world, name, password):
    person = world.person(name)
    code = emailed_code(world, person.email)
    world.saw(world.client.post("/reset", data={"code": code, "password": password, "password2": password},
                                follow_redirects=True), world.client)


@when(parsers.parse('"{name}" changes her password to "{password}"'))
def change_password(world, name, password):
    person = world.person(name)
    world.saw(person.client.post("/profile/password", data={
        "current_password": person.password, "password": password, "password2": password}, follow_redirects=True),
        person.client)


@when(parsers.parse('"{name}" tries to delete her account without typing DELETE'))
def delete_without_word(world, name):
    person = world.person(name)
    world.saw(person.client.post("/profile/delete", data={"confirm": "", "password": person.password},
                                 follow_redirects=True), person.client)


@when(parsers.parse('"{name}" deletes her account properly'))
def delete_account(world, name):
    person = world.person(name)
    world.saw(person.client.post("/profile/delete", data={"confirm": "DELETE", "password": person.password},
                                 follow_redirects=True), person.client)


@when(parsers.parse('"{admin}" suspends "{name}"'))
def suspend(world, admin, name):
    world.person(admin).client.post(f"/admin/users/{world.person(name).id}/suspend")


# ------------------------------------------------------------------ When: profiles

@when(parsers.parse('"{name}" uploads a photo that has GPS data in it'))
def upload_gps_photo(world, name):
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (47.0, 39.0, 20.0)}
    person = world.person(name)
    person.client.post("/profile/photo", data={"photo": (BytesIO(make_image((3000, 2000), "JPEG", exif)), "p.jpg")},
                       content_type="multipart/form-data")


@when(parsers.parse('"{name}" opens her own profile'))
def open_own_profile(world, name):
    person = world.person(name)
    world.saw(person.client.get(f"/u/{person.id}"), person.client)


@when(parsers.re(r'"(?P<viewer>[^"]+)" opens (?P<owner>\w+)\'s profile'))
def open_profile(world, viewer, owner):
    person = world.person(viewer)
    world.saw(person.client.get(f"/u/{world.person(owner).id}"), person.client)


# ------------------------------------------------------------------ When: games

@when(parsers.parse('"{host}" tries to host rowing at "{place}"'))
def host_rowing(world, host, place):
    host_game(world, host, sport="rowing", location=place, title="Row")


@when(parsers.parse('"{host}" hosts pickleball at "{place}"'))
def host_pickleball(world, host, place):
    host_game(world, host, sport="pickleball", location=place, title="Pickleball doubles")
    assert world.response.status_code == 302, "the game wasn't created"
    world.saw(world.client.get(world.response.headers["Location"]), world.client)


@when(parsers.parse('"{host}" tries to host pickleball at "{place}"'))
def try_host_pickleball(world, host, place):
    host_game(world, host, sport="pickleball", location=place, title="Pickleball doubles")


def next_weekday(weekday, hour, minute=0):
    """The next date (at least 2 days away) that falls on `weekday` (0 = Monday), at hour:minute, Seattle time."""
    day = now_local() + timedelta(days=2)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


@when(parsers.parse('"{host}" tries to host basketball at the IMA on a Saturday from {start:d} to {end:d}'))
def host_at_ima_saturday(world, host, start, end):
    world.app.config["CHECK_PLACE_HOURS"] = True  # tests run at any hour: only these check the places' hours
    starts = next_weekday(5, start)
    host_game(world, host, starts_at=starts.strftime("%Y-%m-%dT%H:%M"),
              ends_at=starts.replace(hour=end).strftime("%Y-%m-%dT%H:%M"))


@when(parsers.parse('"{host}" tries to host basketball for {n:d} players'))
def host_too_big(world, host, n):
    host_game(world, host, players=str(n))


@given(parsers.parse('"{host}" hosts a Competitive basketball game tomorrow'))
@when(parsers.parse('"{host}" hosts a Competitive basketball game tomorrow'))
def host_competitive(world, host):
    host_game(world, host, skill_level="Competitive")


@when(parsers.parse('"{host}" posts that she needs {n:d} more for soccer in 15 minutes'))
def need_players(world, host, n):
    person = world.person(host)
    world.saw(person.client.post("/need-players", data={
        "sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "players": str(1 + n)}), person.client)


@when(parsers.re(r'"(?P<viewer>[^"]+)" opens (?P<host>\w+)\'s game'))
def open_game(world, viewer, host):
    person = world.person(viewer)
    world.saw(person.client.get(f"/events/{world.games[host]}"), person.client)


@when(parsers.parse('"{guest}" leaves {host}\'s game'))
def leave_game(world, guest, host):
    person = world.person(guest)
    world.saw(person.client.post(f"/events/{world.games[host]}/leave", follow_redirects=True), person.client)


@when(parsers.parse('"{host}" cancels her game'))
def cancel_game(world, host):
    person = world.person(host)
    world.saw(person.client.post(f"/events/{world.games[person.first]}/cancel", follow_redirects=True),
              person.client)


def edit_game(world, host_name, **changes):
    host = world.person(host_name)
    event_id = world.games[host.first]
    row = world.db("SELECT * FROM events WHERE id = ?", (event_id,))[0]
    form = {"title": row["title"], "sport": row["sport"], "location": row["location"],
            "skill_level": row["skill_level"], "starts_at": row["starts_at"].replace(" ", "T"),
            "ends_at": row["ends_at"].replace(" ", "T"), "players": str(row["max_players"] or ""),
            "note": row["note"], **changes}
    world.saw(host.client.post(f"/events/{event_id}/edit", data=form, follow_redirects=True), host.client)


@when(parsers.parse('"{host}" moves her game an hour later'))
def move_game(world, host):
    row = world.db("SELECT starts_at, ends_at FROM events WHERE id = ?", (world.games[host],))[0]
    later = lambda value: (from_db(value) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    edit_game(world, host, starts_at=later(row["starts_at"]), ends_at=later(row["ends_at"]))


@when(parsers.parse('"{host}" changes the note of her game to "{note}"'))
def change_note(world, host, note):
    edit_game(world, host, note=note)


@when(parsers.parse('"{guest}" downloads the calendar file for {host}\'s game'))
def download_calendar(world, guest, host):
    person = world.person(guest)
    world.saw(person.client.get(f"/events/{world.games[host]}/calendar.ics"), person.client)


@when("the reminder job runs")
def run_reminders(world):
    with world.app.app_context():
        send_due_reminders()


@when(parsers.parse('"{name}" opens the chat for {host}\'s game'))
def open_chat(world, name, host):
    person = world.person(name)
    world.saw(person.client.get(f"/events/{world.games[host]}/chat", follow_redirects=True), person.client)


# ------------------------------------------------------------------ parties, private games, teams

def the_game(world):
    """The one game in this scenario (every party scenario has exactly one)."""
    return next(iter(world.games.values()))


@given(parsers.parse('"{name}" parties up with "{friend}"'))
@when(parsers.parse('"{name}" parties up with "{friend}"'))
def party_up(world, name, friend):
    person = world.person(name)
    world.saw(person.client.post(f"/events/{the_game(world)}/party", data={"friend": world.person(friend).id},
                                 follow_redirects=True), person.client)


@when(parsers.parse('"{name}" asks to bring "{friend}" with the note "{note}"'))
def ask_to_bring(world, name, friend, note):
    person = world.person(name)
    world.saw(person.client.post(f"/events/{the_game(world)}/party",
                                 data={"friend": world.person(friend).id, "note": note}, follow_redirects=True),
              person.client)


@when(parsers.parse('"{host}" approves the request for "{guest}"'))
def approve_request(world, host, guest):
    person = world.person(host)
    world.saw(person.client.post(f"/events/{the_game(world)}/requests/{world.person(guest).id}/approve",
                                 follow_redirects=True), person.client)


@when(parsers.parse('"{name}" challenges {host}\'s game with "{friend}"'))
def challenge(world, name, host, friend):
    person = world.person(name)
    world.saw(person.client.post(f"/events/{world.games[host]}/party", data={"friend": world.person(friend).id},
                                 follow_redirects=True), person.client)


@when(parsers.re(r'"(?P<name>[^"]+)" says (?P<answer>yes|no) to the invite'))
def answer_invite(world, name, answer):
    person = world.person(name)
    world.saw(person.client.post(f"/events/{the_game(world)}/invite/answer", data={"answer": answer},
                                 follow_redirects=True), person.client)


@given(parsers.parse('"{host}" hosts a private basketball game with the password "{password}"'))
def host_private(world, host, password):
    host_game(world, host, is_private="1", password=password)


@given(parsers.parse('"{host}" hosts a 2v2 team game tomorrow'))
def host_team_game(world, host):
    host_game(world, host, team_size="2", title="2v2")


@given(parsers.parse('"{name}" tries to join {host}\'s game with the password "{password}"'))
@when(parsers.parse('"{name}" tries to join {host}\'s game with the password "{password}"'))
def join_with_password(world, name, host, password):
    person = world.person(name)
    world.saw(person.client.post(f"/events/{world.games[host]}/join", data={"password": password},
                                 follow_redirects=True), person.client)


@then(parsers.parse('"{name}" is on team {team:d} in {host}\'s game'))
def on_team(world, name, team, host):
    rows = world.db("SELECT team FROM rsvps WHERE event_id = ? AND user_id = ?",
                    (world.games[host], world.person(name).id))
    assert rows and rows[0]["team"] == team


@then(parsers.parse('"{name}" doesn\'t see "{text}" in the feed filtered to {n:d} open spots'))
def not_in_filtered_feed(world, name, text, n):
    person = world.person(name)
    world.saw(person.client.get("/", query_string={"scope": "all", "open": str(n)}), person.client)
    assert text not in world.text()
    everything = person.client.get("/", query_string={"scope": "all"}).get_data(as_text=True)
    assert text in everything  # it's there without the filter


# ------------------------------------------------------------------ When: clubs

@when(parsers.parse('"{name}" registers a club without any social media or website'))
def register_club_without_socials(world, name):
    person = world.person(name)
    world.saw(person.client.post("/clubs/new", data={**CLUB, "name": "Some Club", "instagram": "", "contact_url": ""}),
              person.client)


@when(parsers.parse('"{name}" registers the club "{club}"'))
def register_club(world, name, club):
    person = world.person(name)
    world.saw(person.client.post("/clubs/new", data={**CLUB, "name": club}, follow_redirects=True), person.client)


@when(parsers.parse('"{admin}" approves "{club}"'))
def approve_club(world, admin, club):
    world.person(admin).client.post(f"/admin/clubs/{club_id(world, club)}/approve")


@when(parsers.parse('"{name}" asks to join "{club}"'))
def ask_to_join(world, name, club):
    person = world.person(name)
    world.saw(person.client.post(f"/clubs/{club_id(world, club)}/join", data={"message": "Yes, a bit!"},
                                 follow_redirects=True), person.client)


@when(parsers.parse('"{officer}" confirms "{member}" in "{club}"'))
def confirm_member(world, officer, member, club):
    world.person(officer).client.post(
        f"/clubs/{club_id(world, club)}/members/{world.person(member).id}/approve")


# ------------------------------------------------------------------ When: friends & messages

@given(parsers.parse('"{sender}" messages "{recipient}" "{text}"'))
@when(parsers.parse('"{sender}" messages "{recipient}" "{text}"'))
def send_dm(world, sender, recipient, text):
    person = world.person(sender)
    world.saw(person.client.post(f"/messages/{world.person(recipient).id}", data={"body": text},
                                 follow_redirects=True), person.client)


@when(parsers.parse('"{name}" searches for "{query}"'))
def search(world, name, query):
    person = world.person(name)
    world.saw(person.client.get("/friends", query_string={"q": query}), person.client)


@when(parsers.parse('"{a}" sends "{b}" a friend request'))
def friend_request(world, a, b):
    world.person(a).client.post(f"/friends/request/{world.person(b).id}")


@when(parsers.parse('"{a}" accepts the friend request from "{b}"'))
def accept_request(world, a, b):
    world.person(a).client.post(f"/friends/accept/{world.person(b).id}")


@when(parsers.parse('"{a}" blocks "{b}"'))
def block(world, a, b):
    world.person(a).client.post(f"/block/{world.person(b).id}")


@when(parsers.parse('"{name}" reports that message as harassment'))
def report_message(world, name):
    person = world.person(name)
    message_id = world.db("SELECT MAX(id) AS id FROM direct_messages WHERE recipient_id = ?", (person.id,))[0]["id"]
    person.client.post(f"/report/dm/{message_id}", data={"reason": "harassment"})


# ------------------------------------------------------------------ When: safety

@when(parsers.parse('"{name}" logs in from a link that points to "{target}"'))
def login_with_next(world, name, target):
    person = world.person(name)
    client = world.app.test_client()
    world.saw(client.post("/login", data={"email": person.email, "password": person.password, "next": target}),
              client)


@when("a form is sent without its security token")
def no_csrf_token(world):
    world.app.config["CSRF_ENABLED"] = True
    person = next(iter(world.people.values()))
    world.saw(person.client.post("/profile/edit", data={"full_name": "Hacked"}), person.client)


@when("a visitor opens How it works")
def visitor_how(world):
    client = world.app.test_client()
    world.saw(client.get("/how-it-works"), client)


@when(parsers.parse('"{host}" tries to host a 24-hour Spikeball game'))
def host_day_long(world, host):
    tomorrow = now_local() + timedelta(days=1)
    host_game(world, host, sport="spikeball", location="The Quad", starts_at=tomorrow.strftime("%Y-%m-%dT%H:%M"),
              ends_at=(tomorrow + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M"))


@when(parsers.parse('"{name}" adds her Instagram "{handle}" and the pronouns "{pronouns}"'))
def add_socials(world, name, handle, pronouns):
    person = world.person(name)
    person.client.post("/profile/edit", data={"full_name": person.name, "grad_year": "", "bio": "",
                                              "pronouns": pronouns, "gender": ""})
    world.saw(person.client.post("/profile/edit/sports", data={
        "instagram": handle, "snapchat": "", "tiktok": "", "x_handle": ""}, follow_redirects=True), person.client)


@when(parsers.parse('"{admin}" gives "{name}" the Tester badge'))
def give_tester(world, admin, name):
    person = world.person(admin)
    world.saw(person.client.post(f"/admin/users/{world.person(name).id}/tester/give", follow_redirects=True),
              person.client)


@when("a visitor opens the home page")
def visitor_home(world):
    client = world.app.test_client()
    world.saw(client.get("/"), client)


# ------------------------------------------------------------------ Then

@then(parsers.parse('they see "{text}"'))
def they_see(world, text):
    assert text in world.text() or text in world.visible_text()


@then(parsers.parse('they don\'t see "{text}"'))
def they_dont_see(world, text):
    assert text not in world.text() and text not in world.visible_text()


@then(parsers.parse('no account exists for "{email}"'))
def no_account(world, email):
    assert not world.db("SELECT 1 FROM users WHERE email = ? AND verified = 1", (email,))


@then("they are logged in")
def logged_in(world):
    with world.client.session_transaction() as session:
        assert session.get("user_id")


@then("they are asked to add a profile picture")
def asked_for_photo(world):
    assert world.client.get("/").headers["Location"].endswith("/profile/photo")


@then("they can open the feed")
def can_open_feed(world):
    for page, words in (("/feed", "📊 Poll"), ("/", "Upcoming games")):     # the feed, and the games list
        response = world.client.get(page)
        assert response.status_code == 200 and words in response.get_data(as_text=True), page


@then(parsers.parse('"{name}" can log in with the password "{password}"'))
def can_log_in(world, name, password):
    log_in(world, world.person(name), password)
    with world.client.session_transaction() as session:
        assert session.get("user_id") == world.person(name).id


@then("the saved photo is a 640 by 640 JPEG without GPS data")
def photo_is_clean(world):
    image = world.db("SELECT image FROM avatars ORDER BY rowid DESC LIMIT 1")[0]["image"]
    with Image.open(BytesIO(image)) as photo:
        assert photo.format == "JPEG" and photo.size == (640, 640) and not photo.getexif()


@then(parsers.parse('"{name}" sees "{text}" in the feed'))
def sees_in_feed(world, name, text):
    person = world.person(name)
    world.saw(person.client.get("/", query_string={"scope": "all"}), person.client)
    assert text in world.text()


@then(parsers.re(r"(?P<host>\w+)'s game has (?P<n>\d+) players?"))
def game_has_players(world, host, n):
    assert world.db("SELECT COUNT(*) AS n FROM rsvps WHERE event_id = ?", (world.games[host],))[0]["n"] == int(n)


@then(parsers.parse('"{email}" gets no email about "{text}"'))
def gets_no_email(world, email, text):
    assert not any(m["to"] == email and text in m["subject"] for m in world.outbox())


@then(parsers.parse('"{email}" gets an email about "{text}"'))
def gets_email(world, email, text):
    assert any(m["to"] == email and text in m["subject"] for m in world.outbox())


@then("the calendar file is valid for Seattle time")
def calendar_is_valid(world):
    body = world.response.get_data(as_text=True)
    assert world.response.mimetype == "text/calendar"
    lines = body.split("\r\n")
    assert all(len(line.encode()) <= 75 for line in lines)
    assert "BEGIN:VTIMEZONE" in body and "DTSTART;TZID=America/Los_Angeles:" in body
    assert re.search(r"^DTSTAMP:\d{8}T\d{6}Z\r?$", body, re.M)


@then(parsers.parse('visitors see "{club}" in the club list'))
def visitors_see_club(world, club):
    assert club in world.app.test_client().get("/clubs").get_data(as_text=True)


@then(parsers.parse('visitors don\'t see "{club}" in the club list'))
def visitors_dont_see_club(world, club):
    assert club not in world.app.test_client().get("/clubs").get_data(as_text=True)


@then(parsers.parse('"{name}" is "{role}" in "{club}"'))
def has_role(world, name, role, club):
    rows = world.db("SELECT role FROM club_members WHERE club_id = ? AND user_id = ?",
                    (club_id(world, club), world.person(name).id))
    assert rows and rows[0]["role"] == role


@then(parsers.parse('"{name}" sees "{badge}" next to "{club}" in My clubs'))
def sees_badge_in_my_clubs(world, name, badge, club):
    page = html.unescape(world.person(name).client.get("/clubs?mine=1").get_data(as_text=True))
    card = page[page.index(club):]
    card = card[:card.index("</a>")]
    assert f" · {badge} · " in card or f" · {badge}\n" in card or f">{badge}<" in card   # the club's grey line


@then(parsers.parse('"{name}" has a message saying "{text}"'))
def has_message(world, name, text):
    assert world.db("SELECT 1 FROM direct_messages WHERE recipient_id = ? AND body = ?",
                    (world.person(name).id, text))


@then(parsers.parse('"{name}" has no messages'))
def has_no_messages(world, name):
    assert not world.db("SELECT 1 FROM direct_messages WHERE recipient_id = ?", (world.person(name).id,))


@then(parsers.parse('"{a}" and "{b}" are now friends'))
def are_friends(world, a, b):
    ids = (world.person(a).id, world.person(b).id)
    assert world.db("""SELECT 1 FROM friendships WHERE status = 'accepted'
                       AND ((requester_id = ? AND addressee_id = ?) OR (requester_id = ? AND addressee_id = ?))""",
                    (*ids, *reversed(ids)))


@then(parsers.parse('admins have {n:d} open report saying "{text}"'))
def open_reports(world, n, text):
    assert len(world.db("SELECT 1 FROM reports WHERE status = 'open' AND snapshot = ?", (text,))) == n


@then("the page has a Content-Security-Policy")
def has_csp(world):
    policy = world.response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in policy and "'unsafe-inline'" not in policy.split("script-src")[1].split(";")[0]


@then("the page has no inline JavaScript")
def no_inline_js(world):
    page = world.response.get_data(as_text=True)
    assert not re.search(r"<script(?![^>]*\bsrc=)(?![^>]*application/json)[^>]*>", page)
    assert not re.search(r"\son(submit|click|change|load|error|input)=", page, re.I)


@then("the page shows the name safely")
def name_is_escaped(world):
    page = world.response.get_data(as_text=True)
    assert "O'Brien<script>" not in page and "O&#39;Brien&lt;script&gt;" in page
    assert 'data-confirm="Remove Liam as a friend?"' in page  # first name only, no quotes that break things


@then("they end up on this site")
def stays_on_site(world):
    location = world.response.headers["Location"]
    assert location.startswith("/") and not location.startswith("//")


@then("the request is refused")
def refused(world):
    assert world.response.status_code == 400
    person = next(iter(world.people.values()))
    assert world.db("SELECT full_name FROM users WHERE id = ?", (person.id,))[0]["full_name"] != "Hacked"


# ------------------------------------------------------------------ notifications

TAB_LABELS = {"Messages": "Messages", "Clubs": "Clubs", "Home": "Home", "Profile": "Profile",
              "Friends": "Friends", "Bell": "Notifications"}


def tab_number(world, name, label):
    """The number on a tab/icon in the navigation (0 if there's none)."""
    page = world.person(name).client.get("/how-it-works").get_data(as_text=True)
    nav = page[page.index('<nav class="appnav"'):page.index("</nav>", page.index('<nav class="appnav"'))]
    match = re.search(r'<span class="tab-icon">(?:(?!</a>).)*?</span>\s*<span class="tab-label">' + label, nav, re.S)
    assert match, label
    number = re.search(r'<span class="count-dot">([^<]+)</span>', match.group(0))
    return int(number.group(1).rstrip("+")) if number else 0


@then(parsers.re(r'"(?P<name>[^"]+)" has (?P<n>\d+) on the (?P<label>\w+) (?:tab|icon)'))
def has_tab_number(world, name, n, label):
    if label == "Admin":  # Admin, tucked into Settings (reports + trending suggestion topics)
        page = world.person(name).client.get("/settings").get_data(as_text=True)  # Admin is in Settings
        match = re.search(r'href="/admin">.*?(?:<span class="count-dot">(\d+)</span>)?</a>', page, re.S)
        assert match, "no admin icon"
        assert int(match.group(1) or 0) == int(n)
        return
    assert tab_number(world, name, TAB_LABELS[label]) == int(n)


def bell_text(world, name):
    page = html.unescape(world.person(name).client.get("/notifications").get_data(as_text=True))
    if 'class="bell-list"' not in page:
        return ""
    return page[page.index('class="bell-list"'):page.index("</ul>", page.index('class="bell-list"'))]


@then(parsers.parse('"{name}" sees "{text}" in the bell'))
def sees_in_bell(world, name, text):
    assert text in bell_text(world, name)


@then(parsers.parse('"{name}" has nothing in the bell'))
def nothing_in_bell(world, name):
    assert bell_text(world, name) == ""


@when(parsers.parse('"{name}" switches off "{kind}" notifications'))
def switch_off(world, name, kind):
    from sportive.notifications import KINDS
    world.person(name).client.post("/settings/notifications", data={k.key: "1" for k in KINDS if k.key != kind})


@when(parsers.parse('"{name}" switches off every notification'))
def switch_off_all(world, name):
    world.person(name).client.post("/settings/notifications", data={})


@when(parsers.parse('"{name}" opens her messages from "{other}"'))
def open_thread(world, name, other):
    world.person(name).client.get(f"/messages/{world.person(other).id}")


@given(parsers.parse('"{name}" follows "{club}"'))
@when(parsers.parse('"{name}" follows "{club}"'))
def follow_club(world, name, club):
    world.person(name).client.post(f"/clubs/{club_id(world, club)}/follow")


@given(parsers.parse('"{officer}" posts the club update "{text}"'))
@when(parsers.parse('"{officer}" posts the club update "{text}"'))
def post_update(world, officer, text):
    world.person(officer).client.post("/clubs/updates", data={"club": club_id(world, "UW Spikeball Club"), "body": text})


@when(parsers.parse('"{name}" opens Club updates'))
def open_club_updates(world, name):
    world.person(name).client.get("/clubs/updates")


# ------------------------------------------------------------------ suggestions

@when(parsers.re(r'"(?P<name>[^"]+)" sends the (?P<anonymous>anonymous )?suggestion "(?P<text>[^"]+)"'))
def send_suggestion(world, name, anonymous, text):
    person = world.person(name)
    data = {"kind": "idea", "body": text}
    if anonymous:
        data["anonymous"] = "1"
    world.saw(person.client.post("/suggestions", data=data, follow_redirects=True), person.client)


@when(parsers.parse('"{name}" sends {n:d} suggestions in a row'))
def send_many_suggestions(world, name, n):
    for i in range(n):
        send_suggestion(world, name, None, f"Idea number {i + 1}")


@when(parsers.parse('"{name}" opens the suggestions page for admins'))
def open_admin_suggestions(world, name):
    person = world.person(name)
    world.saw(person.client.get("/admin/suggestions"), person.client)


@when("a visitor opens the suggestions page")
def visitor_suggestions(world):
    client = world.app.test_client()
    world.saw(client.get("/suggestions", follow_redirects=True), client)
