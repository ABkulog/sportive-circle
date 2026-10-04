"""Clubs getting noticed: launch post, Clubs for you, try-it-out sessions, friends in a club, officers' week."""
from datetime import timedelta

from sportive.db import get_db
from sportive.timeutil import now_local, to_db
from test_feed import approved_club, as_user, form_time, user_id


def test_a_newly_approved_club_is_announced_once_to_its_sport(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="officer@uw.edu", sports=("running",))
    with app.app_context():
        db = get_db()
        club = db.execute("""INSERT INTO clubs (name, sport, description, created_by, status, created_at)
                             VALUES ('UW Run Club', 'running', 'Weekly runs, all paces. Free.', ?, 'pending', ?)""",
                          (user_id(app, "officer@uw.edu"), to_db(now_local()))).lastrowid
        db.execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'officer', ?)",
                   (club, user_id(app, "officer@uw.edu"), to_db(now_local())))
        db.commit()
    accounts.logout()
    accounts.signup(email="admin@uw.edu", sports=("basketball",))
    client.post(f"/admin/clubs/{club}/approve")
    client.post(f"/admin/clubs/{club}/remove", data={"note": "check"})
    client.post(f"/admin/clubs/{club}/approve")
    accounts.logout()
    accounts.signup(email="runner@uw.edu", sports=("running",))
    feed = client.get("/feed").data.decode()
    assert feed.count('class="card feed-card feed-mini"') == 1 and "joined Sportive Circle" in feed  # one short line


def test_clubs_for_you_until_you_follow_one(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    accounts.logout()
    accounts.signup(email="fresh@uw.edu", sports=("running",))
    assert "Clubs for you" in client.get("/feed").data.decode()
    assert client.post(f"/clubs/{club}/follow", data={"next": "/feed"}).headers["Location"] == "/feed"
    assert "Clubs for you" not in client.get("/feed").data.decode()


def test_try_it_out_sessions_welcome_new_people(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("tennis",))
    club = approved_club(app, "officer@uw.edu", name="UW Tennis Club", sport="tennis")
    game = {"title": "Open courts", "sport": "tennis", "location": "IMA North Tennis Courts", "players": "8",
            "starts_at": form_time(timedelta(days=2)), "ends_at": form_time(timedelta(days=2, hours=2)), "note": "",
            "club": club, "try_it": "1"}
    refused = client.post("/events/new", data={**game, "is_private": "members"}, follow_redirects=True).data.decode()
    assert "has to be open to everyone" in refused
    client.post("/events/new", data=game)
    accounts.logout()
    accounts.signup(email="newbie@uw.edu", sports=("tennis",))
    feed = client.get("/feed").data.decode()
    assert "👋 Try it out, new people welcome!" in feed and "Try-it-out session: new people welcome" in feed
    assert "👋 New people welcome" in client.get("/").data.decode()                    # on Play too


def test_friends_in_a_club_and_the_officers_week(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    accounts.logout()
    accounts.signup(email="maya@uw.edu", name="Maya Chen", sports=("running",))
    client.post(f"/clubs/{club}/follow")
    accounts.logout()
    accounts.signup(email="me@uw.edu", sports=("running",))
    with app.app_context():
        get_db().execute("INSERT INTO friendships (requester_id, addressee_id, status, created_at)"
                         " VALUES (?, ?, 'accepted', '2026-09-01 10:00')",
                         (user_id(app, "me@uw.edu"), user_id(app, "maya@uw.edu")))
        get_db().commit()
    assert "Your friend Maya is in this club" in client.get(f"/clubs/{club}").data.decode()
    client.post(f"/clubs/{club}/join", data={"message": "hi"})
    as_user(accounts, "officer@uw.edu")
    page = client.get(f"/clubs/{club}").data.decode()
    assert "This week" in page and "<b>2</b> new follower" in page and "<b>1</b> waiting to join" in page
    assert "Post an update!" in page
