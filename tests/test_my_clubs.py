"""My clubs (Clubs tab) and the clubs on someone's profile."""
from datetime import timedelta

from sportive.db import get_db
from sportive.timeutil import now_local, to_db
from test_feed import approved_club, form_time, user_id


def test_my_clubs_shows_my_clubs_whats_coming_up_and_their_posts(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    client.post("/events/new", data={"title": "Tuesday Run", "sport": "running", "location": "Burke-Gilman Trail",
                                     "skill_level": "Casual", "starts_at": form_time(timedelta(days=2)),
                                     "ends_at": form_time(timedelta(days=2, hours=1)), "players": "", "no_limit": "1",
                                     "note": "", "club": club})
    client.post(f"/clubs/{club}/posts", data={"body": "Bring a headlamp tonight 🔦"})
    accounts.logout()
    accounts.signup(email="fresh@uw.edu", sports=("running",))
    empty = client.get("/clubs/updates").data.decode()
    assert "My clubs" in empty and "Your clubs live here." in empty and "UW Run Club" in empty   # a suggestion
    client.post(f"/clubs/{club}/follow")
    page = client.get("/clubs/updates").data.decode()
    assert 'class="my-club"' in page and "Following" in page                                   # the club row
    assert "Coming up in your clubs" in page and "Tuesday Run" in page                         # its events
    assert "Bring a headlamp tonight" in page                                                  # its posts
    assert ">My clubs<" in page                                                                # the tab's name


def test_profiles_show_the_clubs_someone_is_in(accounts, client, app):
    accounts.signup(email="officer@uw.edu", name="Olivia Officer", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    accounts.logout()
    accounts.signup(email="member@uw.edu", sports=("running",))
    member = user_id(app, "member@uw.edu")
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)",
                   (club, member, to_db(now_local())))
        db.commit()
    page = client.get(f"/u/{user_id(app, 'officer@uw.edu')}").data.decode()
    assert "Clubs</h2>" in page and "UW Run Club" in page and "Officer</span>" in page
    assert "UW Run Club" in client.get(f"/u/{member}").data.decode()                       # members too
    accounts.logout()
    accounts.signup(email="loner@uw.edu", sports=("running",))
    mine = client.get(f"/u/{user_id(app, 'loner@uw.edu')}").data.decode()
    assert "You're not in a club yet" in mine and "Find clubs" in mine
    client.post(f"/block/{user_id(app, 'officer@uw.edu')}")
    assert "UW Run Club" not in client.get(f"/u/{user_id(app, 'officer@uw.edu')}").data.decode()   # blocked: hidden


def test_officers_see_who_is_waiting_on_my_clubs(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    accounts.logout()
    accounts.signup(email="hopeful@uw.edu", sports=("running",))
    client.post(f"/clubs/{club}/join", data={"message": "Hi!"})
    accounts.logout()
    accounts.login(email="officer@uw.edu")
    assert "1 waiting</span>" in client.get("/clubs/updates").data.decode()
    assert "All clubs</a>" not in client.get("/clubs").data.decode()          # Find a club is only for finding


def test_profiles_show_posts(accounts, client, app):
    from test_feed import post
    accounts.signup(email="maya@uw.edu", sports=("running",))
    post(client, body="Track day 🏃")
    maya = user_id(app, "maya@uw.edu")
    assert "Track day" in client.get(f"/u/{maya}").data.decode()
    accounts.logout()
    accounts.signup(email="sam@uw.edu", sports=("basketball",))                  # another sport: still on her profile
    assert "Track day" in client.get(f"/u/{maya}").data.decode()
    client.post(f"/block/{maya}")
    assert "Track day" not in client.get(f"/u/{maya}").data.decode()
