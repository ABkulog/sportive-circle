import re
from datetime import timedelta
from io import BytesIO

from conftest import event_id_from
from sportive import create_app
from sportive.db import get_db
from sportive.timeutil import now_local


def form_time(delta):
    return (now_local() + delta).strftime("%Y-%m-%dT%H:%M")


def event_form(**overrides):
    data = {
        "title": "Pickup 5v5", "sport": "basketball", "location": "IMA (Intramural Activities Building)",
        "skill_level": "Casual", "starts_at": form_time(timedelta(days=1)),
        "ends_at": form_time(timedelta(days=1, hours=2)), "max_players": "", "note": "",
    }
    data.update(overrides)
    return data


# ------------------------------------------------------------------ accounts

def test_landing_page_for_visitors(client):
    assert b"Find people to play with" in client.get("/").data


def test_signup_requires_uw_email(accounts, client):
    response = accounts.signup(email="someone@gmail.com", verify=False)
    assert b"Please use your UW email address" in response.data


def test_older_uw_addresses_work(accounts, client, app):
    accounts.signup(email="husky@u.washington.edu", verify=False)
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM users WHERE email = 'husky@u.washington.edu'").fetchone()[0] == 1
    assert b"Please use your UW email" in client.post("/signup", data={
        "full_name": "X", "email": "x@washington.edu.evil.com", "password": "longenough1",
        "password2": "longenough1", "birth_date": "2005-01-01"}).data


def test_signup_rejects_mismatched_passwords(client):
    response = client.post("/signup", data={
        "full_name": "A", "email": "a@uw.edu", "password": "longenough1",
        "password2": "different11", "birth_date": "2005-01-01",
    })
    assert b"Passwords do not match." in response.data


def test_signup_rejects_too_young(accounts):
    young = (now_local().date() - timedelta(days=365 * 10)).isoformat()
    response = accounts.signup(birth_date=young, verify=False)
    assert b"age range" in response.data


def test_signup_verify_and_login(accounts, client, app):
    accounts.signup()
    with app.app_context():
        user = get_db().execute("SELECT * FROM users WHERE email = 'dubs@uw.edu'").fetchone()
        assert user["verified"] == 1
        assert user["password_hash"] != "purple-and-gold"  # stored hashed, never plain
    accounts.logout()
    assert accounts.login().status_code == 302
    assert b", Dubs!" in client.get("/").data  # "Morning, Dubs!" / "Evening, Dubs!" ...


def test_wrong_code_is_rejected_and_attempts_are_limited(accounts, client):
    accounts.signup(verify=False)
    for _ in range(5):
        assert b"Wrong code" in client.post("/verify", data={"code": "000000"}).data
    response = client.post("/verify", data={"code": accounts.code_for("dubs@uw.edu")})
    assert b"Too many wrong tries" in response.data


def test_unverified_user_cannot_log_in(accounts, client):
    accounts.signup(verify=False)
    client.post("/logout")
    response = accounts.login()
    assert response.headers["Location"].endswith("/verify")


def test_wrong_password(accounts):
    accounts.signup()
    accounts.logout()
    assert b"Wrong email or password!" in accounts.login(password="nope-nope-nope").data


def test_email_already_used(accounts):
    accounts.signup()
    accounts.logout()
    assert b"already in use" in accounts.signup(verify=False).data


# -------------------------------------------------------------------- events

def test_pages_need_login(client):
    assert client.get("/events/new").headers["Location"].startswith("/login")


def test_create_event_and_host_is_going(accounts, client):
    accounts.signup()
    response = client.post("/events/new", data=event_form())
    page = client.get(f"/events/{event_id_from(response)}").data
    assert b"Pickup 5v5" in page and b"1 going" in page


def test_event_validation(accounts, client):
    accounts.signup()
    cases = {
        b"Event name cannot be empty.": event_form(title=""),
        b"has to end after it starts": event_form(ends_at=form_time(timedelta(hours=20))),
        b"can&#39;t be before now": event_form(starts_at=form_time(timedelta(hours=-2)),
                                               ends_at=form_time(timedelta(hours=1))),
        b"Please choose a location.": event_form(location="Moon"),
        b"Max players must be": event_form(max_players="1"),
    }
    for message, data in cases.items():
        assert message in client.post("/events/new", data=data).data, message


def test_duplicate_event_is_rejected(accounts, client):
    accounts.signup()
    client.post("/events/new", data=event_form())
    assert b"already been created" in client.post("/events/new", data=event_form()).data


def test_join_leave_and_capacity(accounts, client):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form(max_players="2")))
    accounts.logout()

    accounts.signup(email="second@uw.edu")
    client.post(f"/events/{event_id}/join")
    assert "You're going".encode() in client.get(f"/events/{event_id}").data
    accounts.logout()

    accounts.signup(email="third@uw.edu")
    response = client.post(f"/events/{event_id}/join", follow_redirects=True)
    assert b"this event is full" in response.data
    accounts.logout()

    accounts.login(email="second@uw.edu")
    client.post(f"/events/{event_id}/leave")
    accounts.logout()
    accounts.login(email="third@uw.edu")
    assert b"You&#39;re in!" in client.post(f"/events/{event_id}/join", follow_redirects=True).data


def test_only_host_can_edit_or_cancel(accounts, client):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="other@uw.edu")
    assert client.get(f"/events/{event_id}/edit").status_code == 403
    assert client.post(f"/events/{event_id}/cancel").status_code == 403


def test_cancelled_event_leaves_feed(accounts, client):
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form(title="Soon cancelled")))
    assert b"Soon cancelled" in client.get("/").data
    client.post(f"/events/{event_id}/cancel")
    assert b"Soon cancelled" not in client.get("/").data


def test_feed_shows_my_sports_by_default(accounts, client):
    accounts.signup(sports=("tennis",))
    client.post("/events/new", data=event_form(title="Hoops night", sport="basketball"))
    client.post("/events/new", data=event_form(title="Tennis doubles", sport="tennis", location="IMA South Tennis Courts"))
    mine = client.get("/").data
    assert b"Tennis doubles" in mine and b"Hoops night" not in mine
    assert b"Hoops night" in client.get("/?scope=all").data


def test_quick_post_counts_existing_players(accounts, client):
    accounts.signup()
    response = client.post("/need-players", data={
        "sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "have": "8", "needed": "2",
    })
    page = client.get(f"/events/{event_id_from(response)}").data
    assert b"Need 2 more for Soccer" in page
    assert b"8 going of 10" in page
    assert "<strong>Up next</strong>" in client.get("/").data.decode()   # the poster sees their own game once
    accounts.logout()
    accounts.signup(email="someone.else@uw.edu")
    home = client.get("/").data.decode()
    assert 'aria-label="Happening soon"' in home and "<strong>Need 2</strong>" in home   # everyone else: "Need 2"


# ------------------------------------------------------------------ security

def test_csrf_blocks_forged_posts(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "csrf.db"), "SECRET_KEY": "t"})
    assert app.test_client().post("/login", data={"email": "x@uw.edu", "password": "x"}).status_code == 400


def test_login_next_cannot_redirect_offsite(accounts, client):
    accounts.signup()
    accounts.logout()
    response = client.post("/login", data={"email": "dubs@uw.edu", "password": "purple-and-gold",
                                           "next": "//evil.example"})
    assert response.headers["Location"] == "/"


def test_profile_edit(accounts, client):
    accounts.signup()
    client.post("/profile/edit", data={"full_name": "Dubs II", "grad_year": "2029",
                                       "bio": "Hoops daily", "sports": ["climbing"]})
    page = client.get("/me/events").data  # any page works; check the profile itself:
    with client.application.app_context():
        user_id = get_db().execute("SELECT id FROM users").fetchone()[0]
    page = client.get(f"/u/{user_id}").data
    assert b"Dubs II" in page and b"Climbing" in page and b"Hoops daily" in page


def test_quick_post_title_counts_down_and_start_is_rounded(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/need-players", data={
        "sport": "basketball", "location": "IMA (Intramural Activities Building)", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "have": "8", "needed": "2",
    }))
    with app.app_context():
        starts_at = get_db().execute("SELECT starts_at FROM events WHERE id = ?", (event_id,)).fetchone()[0]
    assert int(starts_at[-2:]) % 5 == 0
    accounts.logout()

    accounts.signup(email="joiner1@uw.edu")
    client.post(f"/events/{event_id}/join")
    assert b"Need 1 more for Basketball" in client.get(f"/events/{event_id}").data
    accounts.logout()
    accounts.signup(email="joiner2@uw.edu")
    client.post(f"/events/{event_id}/join")
    assert b"Basketball: full" in client.get(f"/events/{event_id}").data


def test_relative_time_counts_hours_across_midnight(monkeypatch):
    from datetime import datetime
    from sportive import timeutil
    monkeypatch.setattr(timeutil, "now_local", lambda: datetime(2026, 9, 26, 23, 4))
    assert timeutil.fmt_relative("2026-09-26 23:15") == "in 11 min"
    assert timeutil.fmt_relative("2026-09-27 00:43") == "in 1 hr"
    assert timeutil.fmt_relative("2026-09-27 19:00") == "tomorrow"
    assert timeutil.fmt_relative("2026-09-30 19:00") == "in 4 days"


# ------------------------------------------------------------- review fixes

def test_old_database_gets_new_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE,"
                " password_hash TEXT NOT NULL, full_name TEXT NOT NULL, grad_year INTEGER, birth_date TEXT,"
                " bio TEXT NOT NULL DEFAULT '', verified INTEGER NOT NULL DEFAULT 0, verify_code TEXT,"
                " verify_expires TEXT, verify_attempts INTEGER NOT NULL DEFAULT 0,"
                " created_at TEXT NOT NULL DEFAULT (datetime('now')))")
    old.commit()
    old.close()
    create_app({"TESTING": True, "DATABASE": str(path), "SECRET_KEY": "t"})
    columns = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(users)")}
    assert {"verify_sent_at", "failed_logins", "locked_until"} <= columns


def test_login_locks_after_too_many_wrong_passwords(accounts):
    accounts.signup()
    accounts.logout()
    for _ in range(10):
        accounts.login(password="wrong-password")
    assert b"Too many wrong passwords" in accounts.login().data  # even the right one is blocked


def test_resend_code_has_a_cooldown(accounts, client):
    accounts.signup(verify=False)
    assert b"Wait a minute" in client.post("/verify/resend", follow_redirects=True).data


def test_shared_link_survives_signup(accounts, client):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    login_page = client.get(f"/events/{event_id}")
    assert "next=" in login_page.headers["Location"]
    client.get(f"/signup?next=/events/{event_id}")
    client.post("/signup", data={"full_name": "New Person", "email": "new@uw.edu", "password": "longenough1",
                                 "password2": "longenough1", "birth_date": "2005-01-01"})
    response = client.post("/verify", data={"code": accounts.code_for("new@uw.edu")})
    assert response.headers["Location"] == f"/events/{event_id}"


def test_ended_quick_post_title(accounts, client, app):
    accounts.signup()
    event_id = event_id_from(client.post("/need-players", data={
        "sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
        "starts_in": "0", "duration": "30", "have": "2", "needed": "3",
    }))
    with app.app_context():
        db = get_db()
        db.execute("UPDATE events SET starts_at = '2020-01-01 10:00', ends_at = '2020-01-01 11:00'")
        db.commit()
    page = client.get(f"/events/{event_id}").data
    assert b"Soccer pickup game" in page and b"more for Soccer" not in page


def test_edit_cannot_move_end_into_the_past(accounts, client):
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    data = event_form(starts_at=form_time(timedelta(hours=-3)), ends_at=form_time(timedelta(hours=-1)))
    assert b"already passed" in client.post(f"/events/{event_id}/edit", data=data).data


def test_joining_overlapping_events_warns(accounts, client):
    accounts.signup(email="host@uw.edu")
    first = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    second = event_id_from(client.post("/events/new", data=event_form(title="Soccer", sport="soccer",
                                                                      location="Denny Field")))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    client.post(f"/events/{first}/join")
    page = client.post(f"/events/{second}/join", follow_redirects=True).data
    assert b"Heads up: this overlaps with" in page


def test_calendar_file(accounts, client):
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form(title="Hoops, then food")))
    response = client.get(f"/events/{event_id}/calendar.ics")
    assert response.mimetype == "text/calendar"
    body = response.data.decode()
    assert "SUMMARY:Hoops\\, then food" in body and "TZID=America/Los_Angeles" in body


def test_email_only_visible_to_people_you_played_with(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="stranger@uw.edu")
    with app.app_context():
        host_id = get_db().execute("SELECT id FROM users WHERE email = 'host@uw.edu'").fetchone()[0]
    assert b"host@uw.edu" not in client.get(f"/u/{host_id}").data
    client.post(f"/events/{event_id}/join")
    assert b"host@uw.edu" in client.get(f"/u/{host_id}").data


def test_friendly_404(accounts, client):
    accounts.signup()
    response = client.get("/events/9999")
    assert response.status_code == 404 and b"Go home" in response.data


def test_refuses_to_run_publicly_without_secret_key(tmp_path):
    import pytest
    with pytest.raises(RuntimeError):
        create_app({"DATABASE": str(tmp_path / "x.db")})


def test_dates_show_year_when_not_this_year(monkeypatch):
    from datetime import datetime
    from sportive import timeutil
    monkeypatch.setattr(timeutil, "now_local", lambda: datetime(2026, 12, 20, 12, 0))
    assert timeutil.fmt_when("2027-01-08 17:30") == "Fri Jan 8, 2027 · 5:30 PM"
    assert timeutil.fmt_when("2026-12-21 09:05") == "Mon Dec 21 · 9:05 AM"


# ------------------------------------------------- feed join, reminders, delete

def test_join_from_feed_card_stays_on_feed(accounts, client):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    feed = client.get("/?scope=all").data
    assert f'/events/{event_id}/join'.encode() in feed
    response = client.post(f"/events/{event_id}/join", data={"next": "/?scope=all"})
    assert response.headers["Location"] == "/?scope=all"
    assert f'/events/{event_id}/join'.encode() not in client.get("/?scope=all").data  # already going


def test_up_next_banner(accounts, client):
    accounts.signup()
    client.post("/events/new", data=event_form(title="Soon game", starts_at=form_time(timedelta(minutes=45)),
                                               ends_at=form_time(timedelta(hours=2))))
    page = client.get("/").data
    assert b"Up next" in page and b"Soon game" in page


def _reminder_setup(accounts, client, app, joined_minutes_before):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form(
        title="Evening hoops", starts_at=form_time(timedelta(minutes=40)), ends_at=form_time(timedelta(hours=2)))))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    client.post(f"/events/{event_id}/join")
    with app.app_context():
        db = get_db()
        starts = db.execute("SELECT starts_at FROM events").fetchone()[0]
        from sportive.timeutil import from_db, to_db
        joined = to_db(from_db(starts) - timedelta(minutes=joined_minutes_before))
        db.execute("UPDATE rsvps SET created_at = ?", (joined,))
        db.commit()


def test_reminders_are_sent_once(accounts, client, app, monkeypatch):
    from sportive import reminders
    sent = []
    monkeypatch.setattr(reminders, "send_email", lambda to, subject, body: sent.append((to, subject, body)))
    _reminder_setup(accounts, client, app, joined_minutes_before=120)
    with app.app_context():
        assert reminders.send_due_reminders() == 2  # host + player
        assert reminders.send_due_reminders() == 0  # never twice
    assert {to for to, _, _ in sent} == {"host@uw.edu", "player@uw.edu"}
    assert "Evening hoops" in sent[0][1] and "/events/1" in sent[0][2]


def test_no_reminder_for_last_minute_joins_or_opt_outs(accounts, client, app, monkeypatch):
    from sportive import reminders
    sent = []
    monkeypatch.setattr(reminders, "send_email", lambda to, subject, body: sent.append(to))
    _reminder_setup(accounts, client, app, joined_minutes_before=5)
    with app.app_context():
        assert reminders.send_due_reminders() == 0
    assert sent == []


def test_reminder_opt_out(accounts, client, app, monkeypatch):
    from sportive import reminders
    sent = []
    monkeypatch.setattr(reminders, "send_email", lambda to, subject, body: sent.append(to))
    _reminder_setup(accounts, client, app, joined_minutes_before=120)
    client.post("/profile/edit", data={"full_name": "Player"})  # reminders box left unchecked
    with app.app_context():
        reminders.send_due_reminders()
    assert sent == ["host@uw.edu"]


def test_reminders_command_runs(app):
    result = app.test_cli_runner().invoke(args=["send-reminders"])
    assert "Sent 0 reminder(s)." in result.output


def test_delete_account(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    client.post("/events/new", data=event_form())
    assert b"not deleted" in client.post("/profile/delete", data={"password": "wrong", "confirm": "DELETE"},
                                         follow_redirects=True).data
    response = client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"},
                           follow_redirects=True)
    assert b"was deleted" in response.data and b"Find people to play with" in response.data
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM rsvps").fetchone()[0] == 0
    assert b"Wrong email or password" in accounts.login(email="host@uw.edu").data


# ------------------------------------------------------ per-sport rules

def test_sport_can_only_be_played_at_its_places(accounts, client):
    accounts.signup()
    page = client.post("/events/new", data=event_form(sport="basketball", location="Burke-Gilman Trail")).data
    assert b"Basketball can&#39;t be played at Burke-Gilman Trail" in page
    quick = client.post("/need-players", data={
        "sport": "rowing", "location": "Denny Field", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "have": "2", "needed": "2",
    }).data
    assert b"Rowing / Kayaking can&#39;t be played at Denny Field" in quick


def test_every_sport_has_rules():
    from sportive.constants import LOCATIONS, SPORT_LOCATIONS, SPORT_MAX_PLAYERS, SPORTS
    assert set(SPORT_LOCATIONS) == set(SPORTS) == set(SPORT_MAX_PLAYERS)
    assert all(place in LOCATIONS for places in SPORT_LOCATIONS.values() for place in places)


def test_player_cap_per_sport(accounts, client, app):
    accounts.signup()
    assert b"Basketball events can have at most 10 players." in client.post(
        "/events/new", data=event_form(max_players="11")).data
    event_id = event_id_from(client.post("/events/new", data=event_form(max_players="")))  # blank = the cap
    with app.app_context():
        assert get_db().execute("SELECT max_players FROM events WHERE id = ?", (event_id,)).fetchone()[0] == 10


def test_quick_post_player_cap(accounts, client):
    accounts.signup()
    page = client.post("/need-players", data={
        "sport": "tennis", "location": "IMA North Tennis Courts", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "have": "3", "needed": "2",
    }).data
    assert b"Tennis games max out at 4 players" in page


def test_forms_include_sport_rules(accounts, client):
    accounts.signup()
    for url in ("/events/new", "/need-players"):
        page = client.get(url).data
        assert b'id="sport-rules"' in page and b"forms.js" in page


def test_sport_stats_command(accounts, client, app):
    runner = app.test_cli_runner()
    assert "No finished events yet" in runner.invoke(args=["sport-stats"]).output
    accounts.signup()
    client.post("/events/new", data=event_form(max_players="8"))
    with app.app_context():
        db = get_db()
        db.execute("UPDATE events SET starts_at = '2026-01-01 10:00', ends_at = '2026-01-01 11:00'")
        db.commit()
    output = runner.invoke(args=["sport-stats"]).output
    assert "Basketball" in output and "8.0" in output


# ------------------------------------------------- profile pictures & how it works

def test_how_it_works_is_public(client):
    page = client.get("/how-it-works").data
    assert b"Sign up with your UW email" in page and b"Need players" in page


def test_new_users_must_add_a_photo(accounts, client):
    accounts.signup(photo=False)
    assert client.get("/").headers["Location"] == "/profile/photo"
    assert client.get("/events/new").headers["Location"] == "/profile/photo"
    assert client.get("/how-it-works").status_code == 200  # still allowed
    response = accounts.upload_photo()
    assert response.headers["Location"] == "/events/new"  # back to the page they tried to open
    assert client.get("/").status_code == 200


def test_first_photo_leads_to_how_it_works(accounts, client):
    accounts.signup(photo=False)
    client.get("/")  # the feed is the normal landing spot, so no special destination
    assert accounts.upload_photo().headers["Location"] == "/how-it-works"


def test_photo_is_resized_and_location_data_removed(accounts, client, app):
    from io import BytesIO
    from PIL import Image
    from conftest import make_image
    accounts.signup(photo=False)
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (47.0, 39.0, 20.0)}  # GPS info, like a phone adds
    accounts.upload_photo(make_image(size=(3000, 2000), fmt="JPEG", exif=exif), "phone.jpg")
    with app.app_context():
        user_id = get_db().execute("SELECT id FROM users").fetchone()[0]
    response = client.get(f"/u/{user_id}/photo")
    assert response.mimetype == "image/jpeg"
    served = Image.open(BytesIO(response.data))
    assert served.size == (256, 256)
    assert not served.getexif()


def test_non_photos_are_rejected(accounts, client):
    accounts.signup(photo=False)
    page = client.post("/profile/photo", data={"photo": (BytesIO(b"<svg onload=alert(1)>"), "x.svg")},
                       content_type="multipart/form-data", follow_redirects=True).data
    assert b"isn&#39;t a photo we can use" in page


def test_too_big_upload(app, accounts, client):
    accounts.signup(photo=False)
    app.config["MAX_CONTENT_LENGTH"] = 1000
    response = accounts.upload_photo()
    assert response.status_code == 413 and b"too big" in response.data


def test_photos_need_login(accounts, client):
    accounts.signup()
    accounts.logout()
    assert client.get("/u/1/photo").headers["Location"].startswith("/login")


def test_shared_link_survives_photo_step(accounts, client):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="new@uw.edu", photo=False)
    client.get(f"/events/{event_id}")
    assert accounts.upload_photo().headers["Location"] == f"/events/{event_id}"


def test_deleting_account_removes_photo(accounts, client, app):
    accounts.signup()
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM avatars").fetchone()[0] == 0


def test_spikeball_on_the_quad(accounts, client):
    accounts.signup(sports=("spikeball",))
    response = client.post("/events/new", data=event_form(title="Spikeball on the Quad", sport="spikeball",
                                                          location="The Quad"))
    assert b"Spikeball on the Quad" in client.get(f"/events/{event_id_from(response)}").data
    assert b"Spikeball on the Quad" in client.get("/").data  # shows in a Spikeball fan's feed
    assert b"can&#39;t be played at The Quad" in client.post(
        "/events/new", data=event_form(sport="basketball", location="The Quad")).data


def test_soccer_is_played_on_the_fields():
    from sportive.constants import SPORT_LOCATIONS
    assert SPORT_LOCATIONS["soccer"] == SPORT_LOCATIONS["ultimate"]  # same open fields as frisbee
    assert "IMA (Intramural Activities Building)" not in SPORT_LOCATIONS["soccer"]
    from sportive.constants import OPEN_FIELDS
    for sport in ("soccer", "football", "ultimate", "volleyball", "spikeball", "running", "other"):
        assert set(OPEN_FIELDS) <= set(SPORT_LOCATIONS[sport]), sport


def test_gym_buddy_places():
    from sportive.constants import SPORT_LOCATIONS
    assert SPORT_LOCATIONS["gym"] == ["IMA (Intramural Activities Building)", "Fitness Center West (under Elm Hall)",
                                       "Off campus (see note)"]


def test_ultimate_frisbee_places(accounts, client):
    from sportive.constants import SPORT_LOCATIONS
    assert SPORT_LOCATIONS["ultimate"] == ["Denny Field", "The Quad", "Husky Track",
                                           "Recreation Field 1 (by the IMA)", "Recreation Field 2 (by Husky Track)",
                                           "Recreation Field 3 (by the golf range)",
                                           "Recreation Field 4 (by the golf range)", "Off campus (see note)"]
    accounts.signup()
    response = client.post("/events/new", data=event_form(title="Frisbee on the fields", sport="ultimate",
                                                          location="Recreation Field 1 (by the IMA)"))
    assert response.status_code == 302


def test_football_on_the_fields(accounts, client):
    accounts.signup(sports=("football",))
    response = client.post("/events/new", data=event_form(title="Flag football", sport="football",
                                                          location="Recreation Field 1 (by the IMA)"))
    assert b"Flag football" in client.get(f"/events/{event_id_from(response)}").data
    assert b"can&#39;t be played at Burke-Gilman Trail" in client.post(
        "/events/new", data=event_form(sport="football", location="Burke-Gilman Trail")).data


def test_add_photo_later(accounts, client):
    accounts.signup(photo=False)
    assert b"Add later" in client.get("/profile/photo").data
    response = client.post("/profile/photo/skip")
    assert response.headers["Location"] == "/how-it-works"
    feed = client.get("/")
    assert feed.status_code == 200                     # still logged in and using the app
    assert b"Add a profile picture so people know" in feed.data  # gentle reminder
    accounts.upload_photo()
    assert b"Add a profile picture so people know" not in client.get("/").data


def test_asked_again_after_next_login(accounts, client):
    accounts.signup(photo=False)
    client.post("/profile/photo/skip")
    accounts.logout()
    accounts.login()
    assert client.get("/").headers["Location"] == "/profile/photo"


def test_add_later_keeps_shared_link(accounts, client):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="new@uw.edu", photo=False)
    client.get(f"/events/{event_id}")
    assert client.post("/profile/photo/skip").headers["Location"] == f"/events/{event_id}"


def test_reminder_email_is_friendly(accounts, client, app, monkeypatch):
    from sportive import reminders
    sent = {}
    monkeypatch.setattr(reminders, "send_email", lambda to, subject, body: sent.update({to: (subject, body)}))
    _reminder_setup(accounts, client, app, joined_minutes_before=120)
    with app.app_context():
        reminders.send_due_reminders()
    subject, body = sent["player@uw.edu"]
    assert subject.startswith("🏀 Evening hoops starts in") and "see you there!" in subject
    assert "Hey Dubs! 👋" in body and "You + 1 other\n" in body and "tap “Leave”" in body
    host_subject, host_body = sent["host@uw.edu"]
    assert "You're the host" in host_body


# ---------------------------------------------------------------- maps

def test_every_campus_place_has_a_map_entry():
    from sportive.constants import LOCATION_COORDS, LOCATIONS
    for place in LOCATIONS:
        if place.startswith("Off campus") or place == "Online":
            assert place not in LOCATION_COORDS
        else:
            assert place in LOCATION_COORDS, place
    from math import cos, hypot, radians
    for place, coords in LOCATION_COORDS.items():
        if coords:  # every pin is near UW (catches typos like a swapped digit): within 5 km of Red Square
            lat, lng = coords
            km = hypot(lat - 47.6560, (lng + 122.3095) * cos(radians(47.656))) * 111.2
            assert km < 5, (place, round(km, 1))


def test_event_page_shows_map_and_directions(accounts, client):
    accounts.signup()
    page = client.get(f"/events/{event_id_from(client.post('/events/new', data=event_form()))}").data.decode()
    assert 'id="event-map"' in page and 'data-lat="47.653743"' in page
    assert "google.com/maps/dir/?api=1&amp;destination=47.653743,-122.301231&amp;travelmode=walking" in page
    assert "maps.apple.com/?daddr=47.653743,-122.301231&amp;dirflg=w" in page


def test_place_without_a_pin_gets_search_directions(accounts, client):
    accounts.signup(sports=("running",))
    page = client.get(f"/events/{event_id_from(client.post('/events/new', data=event_form(sport='running', location='Burke-Gilman Trail')))}").data.decode()
    assert 'id="event-map"' not in page and "leaflet.js" not in page
    assert "destination=Burke-Gilman%20Trail%2C%20University%20of%20Washington%2C%20Seattle" in page


def test_off_campus_and_online_have_no_map(accounts, client):
    accounts.signup(sports=("esports",))
    online = client.get(f"/events/{event_id_from(client.post('/events/new', data=event_form(sport='esports', location='Online')))}").data
    assert b"Directions" not in online
    off = client.get(f"/events/{event_id_from(client.post('/events/new', data=event_form(title='Hike', sport='hiking', location='Off campus (see note)')))}").data
    assert b"the address is in the note" in off


def test_this_month_filter(accounts, client, app, monkeypatch):
    from datetime import datetime
    from sportive import events
    accounts.signup()
    client.post("/events/new", data=event_form(title="September game"))
    client.post("/events/new", data=event_form(title="Next month game"))
    with app.app_context():
        db = get_db()
        db.execute("UPDATE events SET starts_at = '2026-09-29 18:00', ends_at = '2026-09-29 19:00' WHERE title = 'September game'")
        db.execute("UPDATE events SET starts_at = '2026-10-02 18:00', ends_at = '2026-10-02 19:00' WHERE title = 'Next month game'")
        db.commit()
    monkeypatch.setattr(events, "now_local", lambda: datetime(2026, 9, 27, 12, 0))
    page = client.get("/?when=month").data
    assert b"September game" in page and b"Next month game" not in page
    assert b'value="month" selected' in page
    everything = client.get("/").data
    assert b"September game" in everything and b"Next month game" in everything


def test_this_month_works_in_december(monkeypatch):
    from datetime import datetime, timedelta
    now = datetime(2026, 12, 15, 9, 0)
    next_month = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    assert next_month.date().isoformat() == "2027-01-01"



# --------------------------------------------------------------- Husky spirit

def _finish_all_events(app):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE events SET starts_at = '2026-01-10 07:00', ends_at = '2026-01-10 08:00'")
        db.commit()


def test_greeting_by_time_of_day():
    from datetime import datetime
    from sportive.spirit import SPIRIT_LINES, greeting
    assert greeting("Maya", datetime(2026, 9, 27, 8, 0))[0] == "Morning, Maya!"
    assert greeting("Maya", datetime(2026, 9, 27, 14, 0))[0] == "Afternoon, Maya!"
    assert greeting("Maya", datetime(2026, 9, 27, 19, 0))[0] == "Evening, Maya!"
    assert greeting("Maya", datetime(2026, 9, 27, 1, 0))[0] == "Late night, Maya!"
    assert greeting("Maya")[1] in SPIRIT_LINES


def test_badges(accounts, client, app):
    from sportive.badges import eligible
    accounts.signup()
    client.post("/events/new", data=event_form())
    _finish_all_events(app)  # a 7 AM game in January 2026 (before the app's first season)
    with app.app_context():
        user_id = get_db().execute("SELECT id FROM users").fetchone()[0]
        assert eligible(user_id) == {"first_game", "rain_or_shine", "early_dawg", "founding_dawg"}
    page = client.get(f"/u/{user_id}").data
    assert page.count(b'class="showcase-badge') == 3        # only 3 on the profile
    locker = client.get("/profile/badges").data
    assert b"Rain or Shine" in locker and b"Founding Dawg" in locker and b"Earned" in locker
    assert b"Host 5 games" in locker  # badges still to earn show how


def test_cancelled_games_dont_count_for_badges(accounts, client, app):
    from sportive.badges import eligible
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    client.post(f"/events/{event_id}/cancel")
    _finish_all_events(app)
    with app.app_context():
        assert eligible(1) == {"founding_dawg"}


def test_top_dawgs(accounts, client, app, monkeypatch):
    from datetime import datetime
    from sportive import events, spirit
    accounts.signup(email="host@uw.edu", name="Hana Host")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="player@uw.edu", name="Pat Player")
    client.post(f"/events/{event_id}/join")
    _finish_all_events(app)
    fake_now = lambda: datetime(2026, 1, 20, 12, 0)
    monkeypatch.setattr(events, "now_local", fake_now)
    with app.app_context():
        board = spirit.top_dawgs(now=fake_now())
        assert [row["full_name"] for row in board] == ["Hana Host", "Pat Player"]
    feed = client.get("/").data
    assert b"Top Dawgs this month" in feed and b"Hana Host" in feed


def test_celebration_and_footer(accounts, client):
    accounts.signup()
    response = client.post("/events/new", data=event_form(), follow_redirects=True).data
    assert b"flash-celebrate" in response and b"Go Dawgs" in response
    assert b"Made by Huskies, for Huskies" in response
    assert b"Not an official University of Washington service" in response


# ------------------------------------------------------------ ranks & badges

def _user_id(app, email):
    with app.app_context():
        return get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]


def _played_games(app, sport, user_ids, count=1, level="Casual", start="2026-09-22 10:00", end="2026-09-22 11:00"):
    """Insert finished games (hosted by the first user) that everyone in user_ids played."""
    ids = []
    with app.app_context():
        db = get_db()
        for _ in range(count):
            cur = db.execute(
                "INSERT INTO events (host_id, title, sport, location, starts_at, ends_at, skill_level, max_players)"
                " VALUES (?, 'Past game', ?, 'Denny Field', ?, ?, ?, 22)", (user_ids[0], sport, start, end, level))
            for user_id in user_ids:
                db.execute("INSERT INTO rsvps (event_id, user_id, created_at) VALUES (?, ?, '2026-09-01 10:00')",
                           (cur.lastrowid, user_id))
            ids.append(cur.lastrowid)
        db.commit()
    return ids


def test_rank_ladder_needs_rep_and_vouches():
    from sportive.ranks import compute_rank
    assert compute_rank("soccer", 0, 0, 0).name == "Casual 1"
    assert compute_rank("soccer", 95, 0, 0).name == "Casual 3"
    blocked = compute_rank("soccer", 400, 2, 0)            # lots of rep, not enough vouches
    assert blocked.name == "Casual 3" and blocked.blocked_by == "Intermediate" and blocked.vouches == 2
    assert compute_rank("soccer", 400, 3, 0).name == "Intermediate 3"
    stuck = compute_rank("soccer", 800, 9, 4)              # Competitive needs 5 vouches from Intermediate+
    assert stuck.name == "Intermediate 3" and stuck.blocked_by == "Competitive"
    assert compute_rank("soccer", 800, 9, 5).name == "Competitive 2"
    assert compute_rank("soccer", 5000, 9, 5).name == "Legend"


def test_everyone_starts_casual_and_cant_host_higher_levels(accounts, client):
    accounts.signup()
    page = client.post("/events/new", data=event_form(skill_level="Competitive")).data
    assert b"reached Competitive" in page and b"Casual 1" in page
    assert client.post("/events/new", data=event_form(skill_level="All levels")).status_code == 302
    quick = client.post("/need-players", data={
        "sport": "basketball", "location": "IMA (Intramural Activities Building)", "skill_level": "Intermediate",
        "starts_in": "15", "duration": "60", "have": "2", "needed": "2"}).data
    assert b"reached Intermediate" in quick


def test_casual_players_cant_join_competitive_games(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    with app.app_context():
        db = get_db()
        db.execute("UPDATE events SET skill_level = 'Competitive' WHERE id = ?", (event_id,))
        db.commit()
    accounts.logout()
    accounts.signup(email="newbie@uw.edu")
    feed = client.get("/?scope=all").data
    assert "🔒 Competitive+".encode() in feed and f"/events/{event_id}/join".encode() not in feed
    page = client.post(f"/events/{event_id}/join", follow_redirects=True).data
    assert b"reached Competitive" in page
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (event_id,)).fetchone()[0] == 1


def test_props_and_vouches_rules(accounts, client, app):
    accounts.signup(email="a@uw.edu")
    accounts.logout()
    accounts.signup(email="b@uw.edu")
    a, b = _user_id(app, "a@uw.edu"), _user_id(app, "b@uw.edu")
    from sportive.timeutil import now_local, to_db
    recent_start, recent_end = to_db(now_local() - timedelta(hours=3)), to_db(now_local() - timedelta(hours=2))
    (game,) = _played_games(app, "soccer", [a, b], start=recent_start, end=recent_end)
    page = client.get(f"/events/{game}").data
    assert b"GG! How was the game?" in page
    assert b"can&#39;t give yourself props" in client.post(f"/events/{game}/props/{b}", follow_redirects=True).data
    client.post(f"/events/{game}/props/{a}")
    client.post(f"/events/{game}/props/{a}")          # twice = still once
    client.post(f"/events/{game}/vouch/{a}")
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) FROM props").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM vouches WHERE sport = 'soccer'").fetchone()[0] == 1
        from sportive.ranks import sport_rep
        assert sport_rep(a)["soccer"] == 10 + 10 + 5   # played + hosted + props
    (old_game,) = _played_games(app, "soccer", [a, b], start="2026-01-05 10:00", end="2026-01-05 11:00")
    assert b"up to a week" in client.post(f"/events/{old_game}/props/{a}", follow_redirects=True).data


def test_rank_up_to_intermediate_unlocks_games(accounts, client, app):
    accounts.signup(email="star@uw.edu")
    star = _user_id(app, "star@uw.edu")
    teammates = []
    for n in range(3):
        accounts.logout()
        accounts.signup(email=f"mate{n}@uw.edu")
        teammates.append(_user_id(app, f"mate{n}@uw.edu"))
    _played_games(app, "soccer", [star] + teammates, count=8)  # 8 hosted games = 160 rep
    with app.app_context():
        db = get_db()
        for mate in teammates:
            db.execute("INSERT INTO vouches VALUES ('soccer', ?, ?, '2026-09-23 10:00')", (mate, star))
        db.commit()
    accounts.logout()
    accounts.login(email="star@uw.edu")
    feed = client.get("/").data.decode()
    assert "RANK UP! Soccer: you&#39;re now Intermediate 1" in feed
    assert "RANK UP!" not in client.get("/").data.decode()   # celebrated only once
    ok = client.post("/events/new", data=event_form(sport="soccer", location="Denny Field", skill_level="Intermediate"))
    assert ok.status_code == 302
    profile = client.get(f"/u/{star}").data
    assert b"Intermediate 1" in profile and b"Level Up" in profile


def test_season_badges_retire():
    from datetime import date
    from sportive.badges import catalog, is_retired, season_of
    assert season_of(date(2026, 9, 27)) == (2026, "Autumn")
    assert season_of(date(2027, 2, 1)) == (2027, "Winter")
    now_badges = {b.key for b in catalog(date(2026, 9, 27))}
    assert "season-2026-autumn" in now_badges and "season-2027-winter" not in now_badges
    later = {b.key: b for b in catalog(date(2027, 2, 1))}
    assert "season-2027-winter" in later
    assert is_retired(later["season-2026-autumn"], date(2027, 2, 1))
    assert is_retired(later["founding_dawg"], date(2027, 2, 1))
    assert not is_retired(later["season-2027-winter"], date(2027, 2, 1))


def test_badges_are_kept_forever(accounts, client, app):
    from sportive.badges import earned_badges, sync_badges
    accounts.signup(email="host@uw.edu")
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    host, player = _user_id(app, "host@uw.edu"), _user_id(app, "player@uw.edu")
    _played_games(app, "soccer", [host, player])            # Sept 22, 2026 = Autumn 2026
    with app.app_context():
        new = {b.key for b in sync_badges(player)}
        assert {"first_game", "season-2026-autumn", "founding_dawg"} <= new
        db = get_db()
        db.execute("DELETE FROM users WHERE id = ?", (host,))  # host deletes account -> the game is gone
        db.commit()
        sync_badges(player)
        assert "season-2026-autumn" in earned_badges(player)   # the flex stays
    page = client.get(f"/u/{player}").data
    assert b"Autumn 2026" in page
    assert b"% of Huskies" in client.get("/profile/badges").data


def test_midnight_games_count_as_night_not_early(accounts, client, app):
    from sportive.badges import eligible
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    _played_games(app, "soccer", [me], start="2026-09-22 00:43", end="2026-09-22 01:30")
    with app.app_context():
        keys = eligible(me)
    assert "night_dawg" in keys and "early_dawg" not in keys


def test_many_new_badges_share_one_banner(accounts, client, app):
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    _played_games(app, "soccer", [me], start="2026-09-22 06:30", end="2026-09-22 07:30")
    feed = client.get("/").data.decode()
    assert "new badges unlocked" in feed and feed.count("New badge unlocked") == 0


# ------------------------------------------------------------ badge showcase

def test_showcase_is_three_badges_you_choose(accounts, client, app):
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    _played_games(app, "soccer", [me], start="2026-09-22 06:30", end="2026-09-22 07:30")  # early + autumn...
    client.get("/")  # unlocks badges
    with app.app_context():
        from sportive.badges import earned_badges, showcase
        earned = list(earned_badges(me))
        assert len(earned) >= 4 and len(showcase(me)) == 3        # default: 3 rarest
    assert b"only show 3" in client.post("/profile/badges", data={"show": earned[:4]}, follow_redirects=True).data
    assert b"badges you&#39;ve earned" in client.post("/profile/badges", data={"show": ["legend"]},
                                                       follow_redirects=True).data
    client.post("/profile/badges", data={"show": [earned[1], earned[0]]})
    with app.app_context():
        assert [b.key for b in showcase(me)] == [earned[1], earned[0]]
    accounts.logout()
    accounts.signup(email="other@uw.edu")
    public = client.get(f"/u/{me}").data
    assert public.count(b'class="showcase-badge') == 2 and b"choose 3" not in public


# ---------------------------------------------------------------- friends

def test_friend_requests(accounts, client, app):
    accounts.signup(email="a@uw.edu")
    accounts.logout()
    accounts.signup(email="b@uw.edu")
    a, b = _user_id(app, "a@uw.edu"), _user_id(app, "b@uw.edu")
    client.post(f"/friends/request/{a}")
    assert b"Request sent" in client.get(f"/u/{a}").data
    accounts.logout()
    accounts.login(email="a@uw.edu")
    assert b'<span class="count-dot">1</span>' in client.get("/friends").data   # 1 request in the nav
    client.post(f"/friends/accept/{b}")
    assert "✅ Friends".encode() in client.get(f"/u/{b}").data
    client.post(f"/friends/remove/{b}")
    assert b"+ Add friend" in client.get(f"/u/{b}").data


def test_played_with_suggestions(accounts, client, app):
    accounts.signup(email="a@uw.edu", name="Alex Ace")
    accounts.logout()
    accounts.signup(email="b@uw.edu", name="Blake Buddy")
    a, b = _user_id(app, "a@uw.edu"), _user_id(app, "b@uw.edu")
    _played_games(app, "soccer", [a, b], count=2)
    page = client.get("/friends").data
    assert "People you've played with".encode() in page and b"Alex Ace" in page and b"2 games together" in page


# ---------------------------------------------------------- direct messages

def test_dm_rules_and_unread(accounts, client, app):
    accounts.signup(email="a@uw.edu")
    accounts.logout()
    accounts.signup(email="b@uw.edu")
    a, b = _user_id(app, "a@uw.edu"), _user_id(app, "b@uw.edu")
    client.post(f"/messages/{a}", data={"body": "yo"})           # strangers can't DM
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM direct_messages").fetchone()[0] == 0
    _played_games(app, "soccer", [a, b])                           # now they've played together
    client.post(f"/messages/{a}", data={"body": "gg today! <script>alert(1)</script>"})
    accounts.logout()
    accounts.login(email="a@uw.edu")
    feed = client.get("/").data
    assert b'Messages, 1 unread' in feed
    thread = client.get(f"/messages/{b}").data
    assert b"gg today!" in thread and b"<script>alert(1)</script>" not in thread   # escaped
    assert b"Messages, 1 unread" not in client.get("/").data                    # read now
    client.post(f"/messages/{b}", data={"body": "gg!"})
    new = client.get(f"/messages/{b}/poll?after=0").get_json()["messages"]
    assert [m["body"] for m in new][-1] == "gg!" and new[-1]["mine"] is True
    assert b"up to 1000 characters" in client.post(f"/messages/{b}", data={"body": "x" * 1001},
                                                   follow_redirects=True).data


def test_friends_can_dm_without_playing(accounts, client, app):
    accounts.signup(email="a@uw.edu")
    accounts.logout()
    accounts.signup(email="b@uw.edu")
    a = _user_id(app, "a@uw.edu")
    client.post(f"/friends/request/{a}")
    accounts.logout()
    accounts.login(email="a@uw.edu")
    b = _user_id(app, "b@uw.edu")
    client.post(f"/friends/accept/{b}")
    client.post(f"/messages/{b}", data={"body": "hey friend"})
    with app.app_context():
        assert get_db().execute("SELECT body FROM direct_messages").fetchone()[0] == "hey friend"


def test_blocking_stops_messages_and_requests(accounts, client, app):
    accounts.signup(email="a@uw.edu")
    accounts.logout()
    accounts.signup(email="b@uw.edu")
    a, b = _user_id(app, "a@uw.edu"), _user_id(app, "b@uw.edu")
    _played_games(app, "soccer", [a, b])
    accounts.logout()
    accounts.login(email="a@uw.edu")
    client.post(f"/block/{b}")
    accounts.logout()
    accounts.login(email="b@uw.edu")
    client.post(f"/messages/{a}", data={"body": "hello?"})
    client.post(f"/friends/request/{a}")
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) FROM direct_messages").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM friendships").fetchone()[0] == 0
    assert b"+ Add friend" not in client.get(f"/u/{a}").data


def test_message_rate_limit(accounts, client, app):
    accounts.signup(email="a@uw.edu")
    accounts.logout()
    accounts.signup(email="b@uw.edu")
    a, b = _user_id(app, "a@uw.edu"), _user_id(app, "b@uw.edu")
    _played_games(app, "soccer", [a, b])
    for n in range(20):
        client.post(f"/messages/{a}", data={"body": f"msg {n}"})
    assert b"slow down" in client.post(f"/messages/{a}", data={"body": "one more"}, follow_redirects=True).data


# -------------------------------------------------------------- event chat

def test_event_group_chat(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    client.post(f"/events/{event_id}/chat", data={"body": "Court 3, bring a light shirt"})
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    outside = client.get(f"/events/{event_id}/chat", follow_redirects=True).data
    assert b"Join the event to see" in outside and b"Court 3" not in outside
    assert client.get(f"/events/{event_id}/chat/poll").status_code == 403
    client.post(f"/events/{event_id}/join")
    detail = client.get(f"/events/{event_id}").data
    assert f'href="/events/{event_id}/chat"'.encode() in detail and b'<span class="count-dot">1</span>' in detail
    assert b"Court 3, bring a light shirt" in client.get(f"/events/{event_id}/chat").data
    assert b'<span class="count-dot">1</span>' not in client.get(f"/events/{event_id}").data  # seen now
    client.post(f"/events/{event_id}/chat", data={"body": "on my way!"})
    msgs = client.get(f"/events/{event_id}/chat/poll?after=1").get_json()["messages"]
    assert [m["body"] for m in msgs] == ["on my way!"]


# -------------------------------------------------------------------- news

SAMPLE_FEED = """<rss version="2.0"><channel>
<item><title>Huskies Win B1G Opener</title><link>https://gohuskies.com/news/2026/9/25/volleyball-win</link>
  <category>Volleyball</category><pubDate>Fri, 25 Sep 2026 18:11:00 PST</pubDate></item>
<item><title>UW Handed First Loss</title><link>https://gohuskies.com/news/2026/9/26/football-loss</link>
  <category>Football</category><pubDate>Sat, 26 Sep 2026 23:34:00 PST</pubDate></item>
<item><title>Academic Honor Roll</title><link>https://gohuskies.com/news/2026/9/20/general</link>
  <category>Cross Country, Football, Men's Basketball, Softball, Volleyball</category>
  <pubDate>Sun, 20 Sep 2026 10:00:00 PST</pubDate></item>
<item><title>Sketchy</title><link>https://evil.example/phish</link><category>Football</category></item>
</channel></rss>"""


def test_news_parsing():
    from sportive.news import parse_feed
    stories = parse_feed(SAMPLE_FEED)
    assert [s["title"] for s in stories] == ["Huskies Win B1G Opener", "UW Handed First Loss", "Academic Honor Roll"]
    assert stories[1]["teams"] == ["football"] and not stories[1]["general"]
    assert stories[2]["general"]                     # tagged with every team = department news


def test_news_page_filters(accounts, client, monkeypatch):
    from sportive import news
    monkeypatch.setattr(news, "get_stories", lambda: sorted(news.parse_feed(SAMPLE_FEED),
                                                           key=lambda s: s["published"], reverse=True))
    accounts.signup(sports=("football",))
    mine = client.get("/news").data
    assert b"UW Handed First Loss" in mine and b"Huskies Win B1G Opener" not in mine
    everything = client.get("/news?scope=all").data
    assert b"Huskies Win B1G Opener" in everything and b"Academic Honor Roll" in everything
    team = client.get("/news?team=wvball").data
    assert b"Huskies Win B1G Opener" in team and b"UW Handed First Loss" not in team
    assert b"GoHuskies.com" in mine and b"evil.example" not in everything


def test_news_survives_gohuskies_being_down(monkeypatch):
    from sportive import news
    def broken(code):
        raise OSError("down")
    monkeypatch.setattr(news, "_download", broken)
    assert news.fetch_all() == []


# ------------------------------------------ placement, tryouts, chill mode, delete

def _set_seen_level(app, user_id, sport, level):
    with app.app_context():
        db = get_db()
        db.execute("INSERT OR REPLACE INTO ranks_seen (user_id, sport, level) VALUES (?, ?, ?)", (user_id, sport, level))
        db.commit()


def test_good_new_player_gets_placed_by_good_players(accounts, client, app):
    from sportive.ranks import FIRST_LEVEL_OF, compute_rank, sport_rep, vouch_counts
    accounts.signup(email="star@uw.edu")
    star = _user_id(app, "star@uw.edu")
    vets = []
    for n in range(3):
        accounts.logout()
        accounts.signup(email=f"vet{n}@uw.edu")
        vets.append(_user_id(app, f"vet{n}@uw.edu"))
        _set_seen_level(app, vets[-1], "basketball", FIRST_LEVEL_OF["Competitive"])  # they're Competitive
    _played_games(app, "basketball", [vets[0], star] + vets[1:])  # ONE game together
    with app.app_context():
        db = get_db()
        for vet in vets:
            db.execute("INSERT INTO vouches VALUES ('basketball', ?, ?, '2026-09-23 10:00')", (vet, star))
        db.commit()
        rank = compute_rank("basketball", sport_rep(star)["basketball"], *vouch_counts(star, "basketball"))
    assert rank.name == "Competitive 1"      # one game, 10 rep, straight to Competitive


def test_tryout_spots(accounts, client, app):
    from sportive.ranks import FIRST_LEVEL_OF
    accounts.signup(email="host@uw.edu")
    host = _user_id(app, "host@uw.edu")
    _set_seen_level(app, host, "basketball", FIRST_LEVEL_OF["Competitive"])
    with app.app_context():  # give the host a real Competitive rank
        db = get_db()
        for n in range(5):
            db.execute("INSERT INTO users (email, password_hash, full_name, verified) VALUES (?, 'x', 'Vet', 1)",
                       (f"v{n}@uw.edu",))
        db.commit()
    vets = [_user_id(app, f"v{n}@uw.edu") for n in range(5)]
    for vet in vets:
        _set_seen_level(app, vet, "basketball", FIRST_LEVEL_OF["Competitive"])
    _played_games(app, "basketball", [host] + vets, count=25)
    with app.app_context():
        db = get_db()
        for vet in vets:
            db.execute("INSERT INTO vouches VALUES ('basketball', ?, ?, '2026-09-23 10:00')", (vet, host))
        db.commit()
    event_id = event_id_from(client.post("/events/new", data=event_form(skill_level="Competitive", tryout_spots="1")))
    accounts.logout()
    accounts.signup(email="newbie@uw.edu")
    feed = client.get("/?scope=all").data.decode()
    assert "🎟️ 1 tryout spot" in feed and ">Try out<" in feed.replace("\n", "").replace("  ", "")
    page = client.post(f"/events/{event_id}/join", follow_redirects=True).data.decode()
    assert "You&#39;re in as a tryout" in page and "🎟️ Tryout</span>" in page
    accounts.logout()
    accounts.signup(email="newbie2@uw.edu")
    assert b"reached Competitive" in client.post(f"/events/{event_id}/join", follow_redirects=True).data


def test_tryout_spots_only_for_ranked_games(accounts, client, app):
    accounts.signup()
    page = client.post("/events/new", data=event_form(skill_level="Casual", tryout_spots="2")).data
    assert b"Tryout spots are only for Intermediate and Competitive games" in page
    event_id = event_id_from(client.post("/events/new", data=event_form(skill_level="Casual", tryout_spots="0")))
    with app.app_context():
        assert get_db().execute("SELECT tryout_spots FROM events WHERE id = ?", (event_id,)).fetchone()[0] == 0


def test_no_rank_chips_in_casual_games(accounts, client):
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form(skill_level="Casual")))
    assert b"rank-chip" not in client.get(f"/events/{event_id}").data


def test_chill_mode_hides_ranks(accounts, client, app):
    accounts.signup(email="chill@uw.edu", sports=("soccer",))
    chill = _user_id(app, "chill@uw.edu")
    _played_games(app, "soccer", [chill])
    client.post("/profile/edit", data={"full_name": "Chill Dawg", "sports": ["soccer"]})  # show_ranks unchecked
    own = client.get(f"/u/{chill}").data.decode()
    assert "Chill mode: only you can see these" in own and "Casual 1" in own
    accounts.logout()
    accounts.signup(email="other@uw.edu")
    other = client.get(f"/u/{chill}").data.decode()
    assert "chill mode" in other and "Casual 1" not in other


def test_delete_account_needs_are_you_sure(accounts, client, app):
    accounts.signup()
    client.post("/events/new", data=event_form())
    page = client.get("/profile/delete").data.decode()
    assert "Are you sure" in page and "No, keep my account" in page and "can't be undone" in page
    assert "upcoming event you host" in page
    wrong = client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "yes"},
                        follow_redirects=True).data
    assert b"Type DELETE" in wrong
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1   # still here
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "delete"})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


# ------------------------------------------------------------ bring a friend (+1)

def _make_competitive(app, user_id, sport="basketball"):
    """Give someone a real Competitive rank in a sport (5 Competitive vouchers + lots of games)."""
    from sportive.ranks import FIRST_LEVEL_OF
    with app.app_context():
        db = get_db()
        vets = []
        for n in range(5):
            cur = db.execute("INSERT INTO users (email, password_hash, full_name, verified) VALUES (?, 'x', 'Vet', 1)",
                             (f"vet{user_id}-{n}@uw.edu",))
            vets.append(cur.lastrowid)
            db.execute("INSERT INTO ranks_seen VALUES (?, ?, ?)", (cur.lastrowid, sport, FIRST_LEVEL_OF["Competitive"]))
        db.commit()
    _played_games(app, sport, [user_id] + vets, count=25)
    with app.app_context():
        db = get_db()
        for vet in vets:
            db.execute("INSERT INTO vouches VALUES (?, ?, ?, '2026-09-23 10:00')", (sport, vet, user_id))
        db.commit()


def _befriend(client, accounts, a_email, b_email, app):
    accounts.login(email=a_email)
    client.post(f"/friends/request/{_user_id(app, b_email)}")
    accounts.logout()
    accounts.login(email=b_email)
    client.post(f"/friends/accept/{_user_id(app, a_email)}")
    accounts.logout()


def test_bring_a_friend_to_a_competitive_game(accounts, client, app):
    accounts.signup(email="pro@uw.edu", name="Pat Pro")
    accounts.logout()
    accounts.signup(email="buddy@uw.edu", name="Bo Buddy")
    accounts.logout()
    pro, buddy = _user_id(app, "pro@uw.edu"), _user_id(app, "buddy@uw.edu")
    _make_competitive(app, pro)
    _befriend(client, accounts, "pro@uw.edu", "buddy@uw.edu", app)
    accounts.login(email="pro@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form(skill_level="Competitive", allow_plus_ones="1")))
    page = client.get(f"/events/{event_id}").data.decode()
    assert "Bring a friend" in page and "Bo Buddy" in page
    client.post(f"/events/{event_id}/plus-one/{buddy}")
    assert "One +1 per player" in client.post(f"/events/{event_id}/plus-one/{buddy}", follow_redirects=True).data.decode()
    accounts.logout()
    accounts.login(email="buddy@uw.edu")
    assert "invited you as my +1" in client.get(f"/messages/{pro}").data.decode()      # got a DM
    assert "Join as +1" in client.get("/?scope=all").data.decode()                   # card shows the way in
    joined = client.post(f"/events/{event_id}/join", follow_redirects=True).data.decode()
    assert "You&#39;re in as Pat&#39;s +1" in joined and "🤝 Pat's +1" in joined
    with app.app_context():
        row = get_db().execute("SELECT plus_one_of, is_tryout FROM rsvps WHERE user_id = ? AND event_id = ?",
                               (buddy, event_id)).fetchone()
        assert (row["plus_one_of"], row["is_tryout"]) == (pro, 0)


def test_plus_one_rules(accounts, client, app):
    for email in ("pro@uw.edu", "buddy@uw.edu", "stranger@uw.edu", "buddy2@uw.edu"):
        accounts.signup(email=email)
        accounts.logout()
    pro, stranger = _user_id(app, "pro@uw.edu"), _user_id(app, "stranger@uw.edu")
    _make_competitive(app, pro)
    _befriend(client, accounts, "pro@uw.edu", "buddy@uw.edu", app)
    _befriend(client, accounts, "buddy@uw.edu", "buddy2@uw.edu", app)
    accounts.login(email="pro@uw.edu")
    closed = event_id_from(client.post("/events/new", data=event_form(title="No plus ones", skill_level="Competitive")))
    assert "Bring a friend" not in client.get(f"/events/{closed}").data.decode()   # host turned +1s off
    event_id = event_id_from(client.post("/events/new", data=event_form(skill_level="Competitive", allow_plus_ones="1")))
    assert "only bring a friend" in client.post(f"/events/{event_id}/plus-one/{stranger}",
                                                follow_redirects=True).data.decode()
    client.post(f"/events/{event_id}/plus-one/{_user_id(app, 'buddy@uw.edu')}")
    accounts.logout()
    accounts.login(email="buddy@uw.edu")
    client.post(f"/events/{event_id}/join")
    # A +1 can't bring their own +1 (no chains).
    assert "Bring a friend" not in client.get(f"/events/{event_id}").data.decode()
    accounts.logout()
    accounts.login(email="buddy2@uw.edu")
    assert b"reached Competitive" in client.post(f"/events/{event_id}/join", follow_redirects=True).data


# ------------------------------------------------------------------- clubs

CLUB = {"name": "UW Spikeball Club", "sport": "spikeball",
        "description": "Casual roundnet on the Quad. Everyone welcome, nets provided!",
        "meets": "Tuesdays 5-7 PM", "location": "The Quad", "contact_url": "https://uwspikeball.example.com",
        "club_kind": "rso", "verification_url": "https://huskylink.washington.edu/organization/uwspikeball",
        "officer_role": "President", "member_estimate": "30", "focus": "recreational", "joining": "open",
        "experience": "none", "who_can_join": "everyone", "dues": "Free", "gear": "Nets provided",
        "how_to_join": "Come to any Tuesday practice!", "club_email": "spike@uw.edu", "instagram": "@uwspikeball",
        "join_question": "Have you played spikeball before?", "attest": "1"}


def _club_id(app, name="UW Spikeball Club"):
    with app.app_context():
        return get_db().execute("SELECT id FROM clubs WHERE name = ?", (name,)).fetchone()[0]


def _approve(app, club_id):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE clubs SET status = 'approved' WHERE id = ?", (club_id,))
        db.commit()


def test_clubs_are_open_to_everyone(accounts, client, app):
    accounts.signup(email="captain@uw.edu", name="Cap Tain")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app)
    _approve(app, club)
    accounts.logout()
    directory = client.get("/clubs").data.decode()          # no account needed
    assert "UW Spikeball Club" in directory and "1 member" in directory
    page = client.get(f"/clubs/{club}").data.decode()
    assert "Casual roundnet" in page and "✅ Verified" in page and "Sign up to join" in page
    assert "No experience needed" in page and "Come to any Tuesday practice!" in page and "@uwspikeball" in page
    assert "Cap Tain" not in page                             # member names need an account


def test_club_create_validation(accounts, client):
    accounts.signup()
    assert b"https://" in client.post("/clubs/new", data={**CLUB, "contact_url": "javascript:alert(1)"}).data
    assert b"official page" in client.post("/clubs/new", data={**CLUB, "verification_url": "https://myclub.com"}).data
    assert b"at least 5 members" in client.post("/clubs/new", data={**CLUB, "member_estimate": "2"}).data
    assert b"current officer" in client.post("/clubs/new", data={k: v for k, v in CLUB.items() if k != "attest"}).data
    client.post("/clubs/new", data=CLUB)
    assert b"already on Sportive Circle" in client.post("/clubs/new", data={**CLUB, "name": "uw spikeball CLUB"}).data


def test_join_leave_and_officers(accounts, client, app):
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app)
    _approve(app, club)
    assert b"only officer" in client.post(f"/clubs/{club}/leave", follow_redirects=True).data
    accounts.logout()
    accounts.signup(email="fan@uw.edu", name="Fan Person")
    client.post(f"/clubs/{club}/join", data={"message": "Never played, excited to learn!"})
    page = client.get(f"/clubs/{club}").data.decode()
    assert "Request sent" in page and "You're a member" not in page       # NOT a member yet
    assert client.post(f"/clubs/{club}/posts", data={"body": "hi"}).status_code == 403
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    requests = client.get(f"/clubs/{club}").data.decode()
    assert "Join requests (1)" in requests and "Never played, excited to learn!" in requests
    fan = _user_id(app, "fan@uw.edu")
    client.post(f"/clubs/{club}/members/{fan}/approve")
    client.post(f"/clubs/{club}/posts", data={"body": "Nets are at the Quad by 5!"})
    client.post(f"/clubs/{club}/officers/{fan}")
    assert b"You left the club" in client.post(f"/clubs/{club}/leave", follow_redirects=True).data
    assert b"Nets are at the Quad by 5!" in client.get(f"/clubs/{club}").data


def test_club_events_are_all_levels(accounts, client, app):
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app)
    _approve(app, club)
    form_page = client.get(f"/events/new?club={club}").data.decode()
    assert "Club event for" in form_page and 'name="skill_level"' not in form_page
    response = client.post("/events/new", data={**event_form(title="Club night", sport="spikeball",
                                                             location="The Quad", skill_level="Competitive"),
                                                "club": club})
    event_id = event_id_from(response)
    with app.app_context():
        row = get_db().execute("SELECT skill_level, club_id FROM events WHERE id = ?", (event_id,)).fetchone()
        assert (row["skill_level"], row["club_id"]) == ("All levels", club)
    assert "🏛️ UW Spikeball Club".encode() in client.get(f"/events/{event_id}").data
    assert b"Club night" in client.get(f"/clubs/{club}").data
    accounts.logout()
    accounts.signup(email="random@uw.edu")
    assert client.get(f"/events/new?club={club}").status_code == 403       # only officers


# -------------------------------------------------------------- navigation

def test_same_sections_everywhere(accounts, client):
    accounts.signup()
    page = client.get("/").data.decode()
    for label in ("Home", "Clubs", "Create", "News", "Profile", "Messages", "Friends", "How it works"):
        assert f'<span class="tab-label">{label}<' in page, label
    assert 'class="tab  is-active" href="/" aria-current="page"' in page     # Home is highlighted
    assert 'aria-label="How it works"' in page                              # ❓ in the top bar too
    assert "For you" in page and "My events" in page                        # Home tabs
    menu = client.get("/create").data.decode()
    assert "Need players" in menu and "New event" in menu and "Register your club" in menu


def test_visitors_get_simple_menu(client):
    page = client.get("/").data.decode()
    assert 'class="appnav"' not in page and "/clubs" in page and "How it works" in page


def test_chats_hide_the_tab_bar_on_phones(accounts, client):
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    assert b'class="has-app-nav hide-tabs"' in client.get(f"/events/{event_id}/chat").data


# ----------------------------------------------------------------- reports

def _two_players_who_played(accounts, app):
    accounts.signup(email="bad@uw.edu", name="Bad Actor")
    accounts.logout()
    accounts.signup(email="me@uw.edu", name="Me Myself")
    bad, me = _user_id(app, "bad@uw.edu"), _user_id(app, "me@uw.edu")
    _played_games(app, "soccer", [bad, me])
    return bad, me


def test_report_a_profile_and_block(accounts, client, app):
    bad, me = _two_players_who_played(accounts, app)
    form = client.get(f"/report/user/{bad}").data.decode()
    assert "Report Bad Actor" in form and "won't be told who reported them" in form
    done = client.post(f"/report/user/{bad}", data={"reason": "harassment", "details": "keeps bugging me", "block": "1"},
                       follow_redirects=True).data.decode()
    assert "Thanks for letting us know" in done and "You&#39;ve also blocked them" in done
    with app.app_context():
        db = get_db()
        row = db.execute("SELECT * FROM reports").fetchone()
        assert (row["reported_user_id"], row["reason"], row["status"]) == (bad, "harassment", "open")
        assert db.execute("SELECT 1 FROM blocks WHERE blocker_id = ? AND blocked_id = ?", (me, bad)).fetchone()
    assert client.get(f"/report/user/{me}").status_code == 404        # can't report yourself


def test_report_messages_keeps_a_copy(accounts, client, app):
    bad, me = _two_players_who_played(accounts, app)
    accounts.logout()
    accounts.login(email="bad@uw.edu")
    client.post(f"/messages/{me}", data={"body": "you're trash lol"})
    accounts.logout()
    accounts.login(email="me@uw.edu")
    thread = client.get(f"/messages/{bad}").data.decode()
    assert "🚩 Report" in thread
    with app.app_context():
        message_id = get_db().execute("SELECT id FROM direct_messages").fetchone()[0]
    client.post(f"/report/dm/{message_id}", data={"reason": "harassment"})
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM direct_messages")        # even if the message disappears...
        db.commit()
        assert db.execute("SELECT snapshot FROM reports").fetchone()[0] == "you're trash lol"   # ...the copy stays
    client.post(f"/messages/{bad}", data={"body": "stop"})
    with app.app_context():
        my_message = get_db().execute("SELECT id FROM direct_messages WHERE sender_id = ?", (me,)).fetchone()[0]
    assert client.get(f"/report/dm/{my_message}").status_code == 404   # can't report your own message


def test_event_chat_report_rules(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    client.post(f"/events/{event_id}/chat", data={"body": "rude message"})
    with app.app_context():
        message_id = get_db().execute("SELECT id FROM event_messages").fetchone()[0]
    assert client.get(f"/report/event_message/{message_id}").status_code == 404   # own message
    accounts.logout()
    accounts.signup(email="outsider@uw.edu")
    assert client.get(f"/report/event_message/{message_id}").status_code == 404   # not in this chat
    client.post(f"/events/{event_id}/join")
    poll = client.get(f"/events/{event_id}/chat/poll?after=0").get_json()["messages"]
    assert poll[0]["report"] == f"/report/event_message/{message_id}"
    assert client.get(f"/report/event_message/{message_id}").status_code == 200


def test_report_spam_limit(accounts, client, app):
    bad, me = _two_players_who_played(accounts, app)
    for _ in range(10):
        with app.app_context():
            db = get_db()
            db.execute("INSERT INTO reports (reporter_id, reported_user_id, target_type, target_id, reason, created_at)"
                       " VALUES (?, ?, 'user', ?, 'spam', ?)", (me, bad, bad, "2099-01-01 00:00"))
            db.commit()
    assert b"a lot of reports" in client.post(f"/report/user/{bad}", data={"reason": "spam"}, follow_redirects=True).data


def test_admin_reports_page(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="bad@uw.edu", name="Bad Actor")
    accounts.logout()
    bad = _user_id(app, "bad@uw.edu")
    for n in range(3):
        accounts.signup(email=f"witness{n}@uw.edu")
        client.post(f"/report/user/{bad}", data={"reason": "threats"})
        accounts.logout()
    accounts.signup(email="regular@uw.edu")
    assert client.get("/admin/reports").status_code == 404        # hidden from non-admins
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    page = client.get("/admin/reports").data.decode()
    assert "Reported by several people" in page and "Bad Actor" in page and "3 different people" in page
    assert 'aria-label="Reports' in page and "Threats or violence" in page
    with app.app_context():
        report_id = get_db().execute("SELECT id FROM reports").fetchone()[0]
    client.post(f"/admin/reports/{report_id}/reviewed")
    assert "Reviewed (1)" in client.get("/admin/reports").data.decode()



# ---------------------------------------------------------- club verification

def test_new_clubs_wait_for_verification(accounts, client, app):
    accounts.signup(email="captain@uw.edu")
    done = client.post("/clubs/new", data=CLUB, follow_redirects=True).data.decode()
    assert "Waiting for verification" in done
    club = _club_id(app)
    assert client.get(f"/events/new?club={club}").status_code == 403        # no events until verified
    accounts.logout()
    assert "UW Spikeball Club" not in client.get("/clubs").data.decode()     # hidden from the public
    assert client.get(f"/clubs/{club}").status_code == 404
    accounts.signup(email="fan@uw.edu")
    assert client.post(f"/clubs/{club}/join").status_code == 404


def test_admin_approves_or_sends_back(accounts, client, app, monkeypatch):
    from sportive import clubs
    sent = []
    monkeypatch.setattr(clubs, "send_email", lambda to, subject, body: sent.append((to, subject)))
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app)
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    queue = client.get("/admin/clubs").data.decode()
    assert "UW Spikeball Club" in queue and "huskylink.washington.edu/organization/uwspikeball" in queue
    assert "~30 active members" in queue
    assert b"Add a short note" in client.post(f"/admin/clubs/{club}/reject", follow_redirects=True).data
    client.post(f"/admin/clubs/{club}/reject", data={"note": "That HuskyLink page is for a different club."})
    assert sent[-1][0] == "captain@uw.edu"
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    page = client.get(f"/clubs/{club}").data.decode()
    assert "different club" in page and "Update and resubmit" in page
    client.post(f"/clubs/{club}/edit", data={**CLUB, "verification_url": "https://huskylink.washington.edu/organization/spike"})
    with app.app_context():
        assert get_db().execute("SELECT status FROM clubs").fetchone()[0] == "pending"   # back in the queue
    accounts.logout()
    accounts.login(email="admin@uw.edu")
    client.post(f"/admin/clubs/{club}/approve")
    assert "is live" in sent[-1][1]
    accounts.logout()
    assert "UW Spikeball Club" in client.get("/clubs").data.decode()


def test_regular_users_cant_review_clubs(accounts, client, app):
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    assert client.get("/admin/clubs").status_code == 404
    assert client.post(f"/admin/clubs/{_club_id(app)}/approve").status_code == 404


def test_club_quick_filters(accounts, client, app):
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    client.post("/clubs/new", data={**CLUB, "name": "UW Competitive Spikeball", "joining": "tryouts",
                                    "experience": "experienced", "dues": "$60/quarter",
                                    "verification_url": "https://huskylink.washington.edu/organization/comp"})
    with app.app_context():
        db = get_db()
        db.execute("UPDATE clubs SET status = 'approved'")
        db.commit()
    everyone = client.get("/clubs").data.decode()
    assert "UW Spikeball Club" in everyone and "UW Competitive Spikeball" in everyone
    beginner = client.get("/clubs?easy=beginner&easy=free&easy=no_tryouts").data.decode()
    assert "UW Spikeball Club" in beginner and "UW Competitive Spikeball" not in beginner


def test_clubs_featured_on_landing_and_home(accounts, client, app):
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    _approve(app, _club_id(app))
    accounts.logout()
    assert "Verified UW clubs" in client.get("/").data.decode() and "UW Spikeball Club" in client.get("/").data.decode()
    accounts.signup(email="fan@uw.edu", sports=("spikeball",))
    home = client.get("/").data.decode()
    assert "Clubs for you" in home and "UW Spikeball Club" in home
    client.post(f"/clubs/{_club_id(app)}/join")
    assert "Clubs for you" not in client.get("/").data.decode()     # already joined


def test_joining_a_club_jumps_to_how_to_join(accounts, client, app):
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app)
    _approve(app, club)
    accounts.logout()
    accounts.signup(email="fan@uw.edu")
    response = client.post(f"/clubs/{club}/join")
    assert response.headers["Location"].endswith(f"/clubs/{club}#how-to-join")
    page = client.get(f"/clubs/{club}").data.decode()
    assert page.index('id="how-to-join"') < page.index('class="quick-facts"')   # before the Quick facts



# ---------------------------------------------------------- club membership

def _approved_club(accounts, client, app, **overrides):
    accounts.signup(email="captain@uw.edu", name="Cap Tain")
    client.post("/clubs/new", data={**CLUB, **overrides})
    club = _club_id(app, overrides.get("name", CLUB["name"]))
    _approve(app, club)
    accounts.logout()
    return club


def test_follow_is_not_membership(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="curious@uw.edu")
    client.post(f"/clubs/{club}/follow")
    page = client.get(f"/clubs/{club}").data.decode()
    stats = re.findall(r"<strong>(\d+)</strong><span>(\w+)</span>", page)
    assert ">Unfollow<" in page and ("1", "member") in stats and ("1", "follower") in stats   # captain only


def test_tryouts_flow_with_messages(accounts, client, app):
    club = _approved_club(accounts, client, app, joining="tryouts")
    accounts.signup(email="hopeful@uw.edu", name="Hope Ful")
    page = client.get(f"/clubs/{club}").data.decode()
    assert "Sign up for tryouts" in page and "Have you played spikeball before?" in page
    client.post(f"/clubs/{club}/join", data={"message": "Yes, 2 years in high school"})
    assert "Signed up for tryouts" in client.get(f"/clubs/{club}").data.decode()
    hopeful = _user_id(app, "hopeful@uw.edu")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    assert "Made the team" in client.get(f"/clubs/{club}").data.decode()
    client.post(f"/clubs/{club}/members/{hopeful}/decline")
    accounts.logout()
    accounts.login(email="hopeful@uw.edu")
    captain = _user_id(app, "captain@uw.edu")
    assert "Thanks so much for trying out" in client.get(f"/messages/{captain}").data.decode()
    assert ">Unfollow<" in client.get(f"/clubs/{club}").data.decode()       # still following after "not this time"


def test_application_needs_an_answer(accounts, client, app):
    club = _approved_club(accounts, client, app, joining="application")
    accounts.signup(email="applicant@uw.edu")
    assert b"answer the club&#39;s question" in client.post(f"/clubs/{club}/join", follow_redirects=True).data
    client.post(f"/clubs/{club}/join", data={"message": "I love spikeball"})
    with app.app_context():
        row = get_db().execute("SELECT role, message FROM club_members WHERE user_id = ?",
                               (_user_id(app, "applicant@uw.edu"),)).fetchone()
        assert (row["role"], row["message"]) == ("requested", "I love spikeball")


def test_confirmed_member_gets_welcome_message(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu")
    client.post(f"/clubs/{club}/join", data={"message": "hi"})
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    client.post(f"/clubs/{club}/members/{_user_id(app, 'fan@uw.edu')}/approve")
    accounts.logout()
    accounts.login(email="fan@uw.edu")
    assert "You&#39;re officially a member" in client.get(f"/messages/{_user_id(app, 'captain@uw.edu')}").data.decode()
    assert ">Member</span>" in client.get(f"/clubs/{club}").data.decode()


def test_all_club_info_is_required(accounts, client):
    accounts.signup()
    for field in ("meets", "location", "dues", "gear", "how_to_join", "join_question", "club_email"):
        page = client.post("/clubs/new", data={**CLUB, field: ""}).data
        assert b"Please add" in page, field
    # Socials and website are optional: a club with only an email can register.
    client.post("/clubs/new", data={**CLUB, "instagram": "", "contact_url": ""})
    with client.application.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM clubs").fetchone()[0] == 1


def test_anyone_can_contact_a_club(accounts, client, app):
    club = _approved_club(accounts, client, app)
    visitor = client.get(f"/clubs/{club}").data.decode()          # logged out
    assert 'id="contact">Contact' in visitor and "spike@uw.edu" in visitor and "@uwspikeball" in visitor
    accounts.signup(email="question@uw.edu")
    page = client.get(f"/clubs/{club}").data.decode()
    captain = _user_id(app, "captain@uw.edu")
    assert f"/messages/{captain}" in page                          # message an officer before joining
    client.post(f"/messages/{captain}", data={"body": "Do I need my own net?"})
    with app.app_context():
        assert get_db().execute("SELECT body FROM direct_messages").fetchone()[0] == "Do I need my own net?"


def test_club_updates_feed(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.login(email="captain@uw.edu")
    composer = client.get("/clubs/updates").data.decode()
    assert "Post an update" in composer and "Posting as" in composer
    client.post("/clubs/updates", data={"club": club, "body": "Practice moved to the Quad!"})
    accounts.logout()
    accounts.signup(email="stranger@uw.edu")
    feed = client.get("/clubs/updates").data.decode()
    assert "Practice moved to the Quad!" not in feed and "Follow clubs to see their updates" in feed
    assert "Post an update" not in feed
    assert client.post("/clubs/updates", data={"club": club, "body": "spam"}).status_code == 403   # not an officer
    client.post(f"/clubs/{club}/follow")
    assert "Practice moved to the Quad!" in client.get("/clubs/updates").data.decode()



def test_club_socials(accounts, client, app):
    accounts.signup(email="captain@uw.edu")
    bad = client.post("/clubs/new", data={**CLUB, "facebook": "https://evil.example/fb"}).data.decode()
    assert "That Facebook doesn&#39;t look right" in bad
    assert "That TikTok doesn&#39;t look right" in client.post("/clubs/new", data={**CLUB, "tiktok": "no spaces allowed"}).data.decode()
    client.post("/clubs/new", data={**CLUB, "tiktok": "@uwspike", "snapchat": "uwspike", "x_handle": "@uwspike",
                                    "facebook": "https://www.facebook.com/uwspike", "youtube": "https://youtube.com/@uwspike"})
    club = _club_id(app)
    _approve(app, club)
    accounts.logout()
    page = client.get(f"/clubs/{club}").data.decode()
    for link in ("https://www.tiktok.com/@uwspike", "https://www.snapchat.com/add/uwspike", "https://x.com/uwspike",
                 "https://www.facebook.com/uwspike", "https://youtube.com/@uwspike", "https://instagram.com/uwspikeball"):
        assert f'href="{link}"' in page, link


def test_page_titles_are_clean(accounts, client, app):
    """No page should leak markup into the browser tab title."""
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app)
    _approve(app, club)
    for url in ("/", "/clubs", "/clubs/new", f"/clubs/{club}", f"/clubs/{club}/edit", "/events/new", "/need-players",
                "/news", "/how-it-works", "/create", "/me/events", "/friends", "/messages", "/profile/edit",
                "/profile/badges", "/clubs/updates"):
        title = re.search(r"<title>(.*?)</title>", client.get(url).data.decode(), re.S).group(1)
        assert "<" not in title and ">" not in title, (url, title)


def test_need_players_chat_opens(accounts, client):
    """Regression: the chat of a quick "Need players" post used to crash (it needs live player counts)."""
    accounts.signup()
    response = client.post("/need-players", data={
        "sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "have": "8", "needed": "2"})
    event_id = event_id_from(response)
    page = client.get(f"/events/{event_id}/chat")
    assert page.status_code == 200 and b"Need 2 more for Soccer" in page.data


def test_only_officer_cant_delete_account(accounts, client, app):
    _approved_club(accounts, client, app)
    accounts.login(email="captain@uw.edu")
    assert "the only officer" in client.get("/profile/delete").data.decode()
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM users WHERE email = 'captain@uw.edu'").fetchone()[0] == 1


def test_signup_cant_flood_an_inbox(accounts, client):
    accounts.signup(email="target@uw.edu", verify=False)
    client.post("/logout")
    again = accounts.signup(email="target@uw.edu", verify=False).data
    assert b"We just sent a code to that email" in again


# ------------------------------------------------------------ launch-readiness checks

def test_people_search_treats_wildcards_as_text(accounts, client):
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    accounts.logout()
    accounts.signup(email="jordan@uw.edu", name="Jordan Rivera")
    assert b"Maya Chen" in client.get("/friends?q=ma").data
    assert b"Maya Chen" not in client.get("/friends?q=%25%25").data      # "%%" is not "match anything"
    assert b"Maya Chen" not in client.get("/friends?q=m").data           # at least 2 letters
    assert b"Jordan Rivera" not in client.get("/friends?q=jordan").data  # never yourself


def test_officers_can_message_their_followers_and_reply(accounts, client, app):
    club = _approved_club(accounts, client, app)                          # captain@uw.edu is the officer
    accounts.logout()
    accounts.signup(email="stranger@uw.edu", name="Stranger Danger")
    stranger = _user_id(app, "stranger@uw.edu")
    accounts.logout()
    accounts.signup(email="fan@uw.edu", name="Big Fan")
    fan = _user_id(app, "fan@uw.edu")
    client.post(f"/clubs/{club}/follow")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    client.post(f"/messages/{fan}", data={"body": "Practice is at 5!"})
    client.post(f"/messages/{stranger}", data={"body": "Join us!!"})
    with app.app_context():
        bodies = {row[0] for row in get_db().execute("SELECT body FROM direct_messages")}
    assert "Practice is at 5!" in bodies and "Join us!!" not in bodies


def test_anyone_can_reply_to_someone_who_wrote_first(accounts, client, app):
    club = _approved_club(accounts, client, app)
    captain = _user_id(app, "captain@uw.edu")
    accounts.logout()
    accounts.signup(email="asker@uw.edu", name="Curious Husky")
    client.post(f"/messages/{captain}", data={"body": "Do you need cleats?"})   # students can ask officers
    asker = _user_id(app, "asker@uw.edu")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    client.post(f"/clubs/{club}/leave")  # even if they weren't an officer anymore, they could reply
    client.post(f"/messages/{asker}", data={"body": "Nope, just come!"})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM direct_messages").fetchone()[0] == 2


def test_security_headers_everywhere(client):
    response = client.get("/")
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "geolocation=(self)" in response.headers["Permissions-Policy"]


def test_no_inline_scripts_in_any_template():
    import pathlib
    for template in pathlib.Path("sportive/templates").rglob("*.html"):
        text = template.read_text()
        assert not re.search(r"\son(submit|click|change|input|load)=", text), template
        assert not re.search(r"<script>", text), template


def test_change_password_needs_current_password(accounts, client):
    accounts.signup()
    page = client.post("/profile/password", data={"current_password": "wrong", "password": "new-password-1",
                                                  "password2": "new-password-1"}, follow_redirects=True).data
    assert b"current password isn" in page
    accounts.logout()
    assert b"Wrong email or password" in client.post("/login", data={"email": "dubs@uw.edu",
                                                                     "password": "new-password-1"}).data


def test_suspending_cancels_their_upcoming_games(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    host = _user_id(app, "host@uw.edu")
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    client.post(f"/admin/users/{host}/suspend")
    with app.app_context():
        assert get_db().execute("SELECT cancelled FROM events WHERE id = ?", (event_id,)).fetchone()[0] == 1
    client.post(f"/admin/users/{_user_id(app, 'admin@uw.edu')}/suspend")   # admins can't be suspended here
    with app.app_context():
        assert get_db().execute("SELECT suspended FROM users WHERE email = 'admin@uw.edu'").fetchone()[0] == 0


def test_club_form_points_at_the_field_with_the_problem(accounts, client):
    accounts.signup()
    page = client.post("/clubs/new", data={**CLUB, "club_email": "not-an-email"}).data
    assert b'data-error-field="club_email"' in page


def test_info_pages_and_friendly_server_error(client, app):
    @app.route("/boom")
    def boom():
        raise RuntimeError("test")
    app.config["PROPAGATE_EXCEPTIONS"] = False
    for path in ("/privacy", "/terms", "/how-it-works"):
        assert client.get(path).status_code == 200
    response = client.get("/boom")
    assert response.status_code == 500 and b"Something broke on our side" in response.data


def test_calendar_lines_are_folded():
    from sportive.events import ics_fold
    folded = ics_fold("DESCRIPTION:" + "é" * 80)
    assert all(len(line.encode()) <= 75 for line in folded.split("\r\n"))
    assert folded.replace("\r\n ", "") == "DESCRIPTION:" + "é" * 80


def test_skill_level_options_have_fixed_values(accounts, client):
    """forms.js adds a 🔒 to locked levels' text; the submitted value must stay the plain level name."""
    accounts.signup()
    for page in ("/events/new", "/need-players"):
        html = client.get(page).data.decode()
        for level in ("All levels", "Casual", "Intermediate", "Competitive"):
            assert f'<option value="{level}"' in html, (page, level)
    assert 'name="tryout_spots"' in client.get("/need-players").data.decode()


def test_hidden_always_hides():
    """Fields hidden by JavaScript (like tryout spots on Casual games) must really disappear,
    even when their class sets display: grid or flex."""
    import pathlib
    assert "[hidden] { display: none !important; }" in pathlib.Path("sportive/static/style.css").read_text()


# ------------------------------------------------------------ bug hunt (Sept 27, 2026)

def test_huge_numbers_in_links_are_a_404_not_a_crash(accounts, client):
    accounts.signup()
    big = "99999999999999999999"
    assert client.get(f"/events/{big}").status_code == 404
    assert client.get(f"/messages/2/poll?after={big}").status_code in (200, 404)
    assert client.get(f"/events/new?club={big}").status_code in (403, 404)


def test_very_long_searches_dont_crash(accounts, client):
    accounts.signup()
    assert client.get("/friends?q=" + "x" * 100_000).status_code == 200
    assert client.get("/clubs?q=" + "x" * 100_000).status_code == 200


def test_names_have_a_length_limit_and_one_line(accounts, client, app):
    page = client.post("/signup", data={"full_name": "x" * 61, "email": "long@uw.edu", "password": "purple-and-gold",
                                        "password2": "purple-and-gold", "birth_date": "2005-01-15"}).data
    assert b"under 60 characters" in page
    accounts.signup(name="Dubs\r\n  Husky")
    with app.app_context():
        assert get_db().execute("SELECT full_name FROM users WHERE email = 'dubs@uw.edu'").fetchone()[0] == "Dubs Husky"
    client.post("/events/new", data=event_form(title="Hoops\r\nBcc: spam"))
    with app.app_context():
        assert get_db().execute("SELECT title FROM events").fetchone()[0] == "Hoops Bcc: spam"


def test_one_failed_reminder_doesnt_stop_the_others(accounts, client, app, monkeypatch):
    from sportive import reminders
    accounts.signup(email="host@uw.edu")
    host = _user_id(app, "host@uw.edu")
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    player = _user_id(app, "player@uw.edu")
    with app.app_context():
        db = get_db()
        soon = now_local() + timedelta(minutes=45)
        cur = db.execute("INSERT INTO events (host_id, title, sport, location, starts_at, ends_at, skill_level)"
                         " VALUES (?, 'Game', 'basketball', 'IMA (Intramural Activities Building)', ?, ?, 'Casual')",
                         (host, soon.strftime("%Y-%m-%d %H:%M"), (soon + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")))
        for user in (host, player):
            db.execute("INSERT INTO rsvps (event_id, user_id, created_at) VALUES (?, ?, '2026-01-01 10:00')",
                       (cur.lastrowid, user))
        db.commit()
        calls = []

        def flaky(to, subject, body):
            calls.append(to)
            if to == "host@uw.edu":
                raise OSError("mailbox full")
        monkeypatch.setattr(reminders, "send_email", flaky)
        assert reminders.send_due_reminders() == 1
        assert sorted(calls) == ["host@uw.edu", "player@uw.edu"]


def test_blocked_people_cant_join_each_others_games(accounts, client, app):
    accounts.signup(email="host@uw.edu", name="Host Husky")
    event_id = event_id_from(client.post("/events/new", data=event_form(title="Private-ish game")))
    accounts.logout()
    accounts.signup(email="pest@uw.edu", name="Pest Husky")
    pest = _user_id(app, "pest@uw.edu")
    accounts.logout()
    accounts.login(email="host@uw.edu")
    client.post(f"/block/{pest}")
    accounts.logout()
    accounts.login(email="pest@uw.edu")
    assert b"Private-ish game" not in client.get("/?scope=all").data
    assert b"You can&#39;t join this game" in client.post(f"/events/{event_id}/join", follow_redirects=True).data
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rsvps WHERE user_id = ?", (pest,)).fetchone()[0] == 0


def test_suspended_profiles_are_hidden_from_students(accounts, client, app):
    accounts.signup(email="bad@uw.edu")
    bad = _user_id(app, "bad@uw.edu")
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    client.post(f"/admin/users/{bad}/suspend")
    assert client.get(f"/u/{bad}").status_code == 200        # admins can still look
    accounts.logout()
    accounts.signup(email="student@uw.edu")
    assert client.get(f"/u/{bad}").status_code == 404


def test_chat_title_uses_the_live_need_players_title(accounts, client):
    accounts.signup()
    response = client.post("/need-players", data={"sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
                                                  "starts_in": "15", "duration": "60", "have": "5", "needed": "3"})
    page = client.get(f"/events/{event_id_from(response)}/chat").data.decode()
    assert "<title>Chat · Need 3 more for Soccer" in page


def test_hidden_pill_inputs_cant_widen_the_page():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text()
    assert ".segmented input, .chip-check input, .choice-pill input {" in css and "width: 1px; height: 1px" in css


def test_leap_day_birthdays():
    from datetime import date
    from sportive.auth import is_birthday
    leap_baby = date(2004, 2, 29)
    assert is_birthday(leap_baby, date(2027, 2, 28)) and not is_birthday(leap_baby, date(2028, 2, 28))
    assert is_birthday(leap_baby, date(2028, 2, 29))
    assert is_birthday(date(2005, 1, 15), date(2027, 1, 15)) and not is_birthday(date(2005, 1, 15), date(2027, 1, 16))


def test_deleting_an_account_warns_people_in_their_games(accounts, client, app):
    accounts.signup(email="host@uw.edu", name="Host Husky")
    event_id = event_id_from(client.post("/events/new", data=event_form(title="Saturday hoops")))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    client.post(f"/events/{event_id}/join")
    accounts.logout()
    accounts.login(email="host@uw.edu")
    client.post("/profile/delete", data={"confirm": "DELETE", "password": "purple-and-gold"})
    outbox = app.extensions.get("outbox", [])
    assert any(m["to"] == "player@uw.edu" and m["subject"].startswith("Canceled: Saturday hoops") for m in outbox)


def test_officers_see_how_many_are_waiting_on_their_club_card(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.logout()
    accounts.signup(email="newbie@uw.edu")
    client.post(f"/clubs/{club}/join", data={"message": "hi"})
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    assert "1 waiting to join" in client.get("/clubs?mine=1").data.decode()


def test_saving_the_photo_page_without_a_new_photo_goes_back_to_profile(accounts, client, app):
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    response = client.post("/profile/photo", data={}, content_type="multipart/form-data")
    assert response.headers["Location"].endswith(f"/u/{me}")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM avatars").fetchone()[0] == 1   # photo kept


def test_remove_profile_photo(accounts, client, app):
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    assert b"Remove photo" in client.get("/profile/photo").data
    client.post("/profile/photo/remove")
    with app.app_context():
        assert get_db().execute("SELECT avatar_updated FROM users WHERE id = ?", (me,)).fetchone()[0] is None
        assert get_db().execute("SELECT COUNT(*) FROM avatars").fetchone()[0] == 0
    page = client.get("/")                        # not forced back to the "add a photo" step...
    assert page.status_code == 200 and b"Add a profile picture so people know" in page.data   # ...just reminded


def test_first_photo_still_required_to_pick_one(accounts, client):
    accounts.signup(photo=False)
    assert b"Choose a photo first" in client.post("/profile/photo", data={}, content_type="multipart/form-data",
                                                  follow_redirects=True).data


def test_club_page_counts_followers(accounts, client, app):
    club = _approved_club(accounts, client, app)
    page = client.get(f"/clubs/{club}").data.decode()
    assert "<span>followers</span>" in page and "<span>following</span>" not in page
    accounts.logout()
    accounts.signup(email="fan@uw.edu")
    client.post(f"/clubs/{club}/follow")
    assert "<strong>1</strong><span>follower</span>" in client.get(f"/clubs/{club}").data.decode()


def test_followers_see_one_unfollow_button(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.logout()
    accounts.signup(email="fan@uw.edu")
    client.post(f"/clubs/{club}/follow")
    assert client.get(f"/clubs/{club}").data.decode().count(">Unfollow<") == 1
    client.post(f"/clubs/{club}/leave")
    assert ">Follow<" in client.get(f"/clubs/{club}").data.decode()


def test_reminder_task_needs_the_secret_token(client, app):
    assert client.post("/tasks/send-reminders").status_code == 404            # no token configured: no page
    app.config["TASK_TOKEN"] = "s3cret"
    assert client.post("/tasks/send-reminders", headers={"X-Task-Token": "wrong"}).status_code == 404
    response = client.post("/tasks/send-reminders", headers={"X-Task-Token": "s3cret"})
    assert response.status_code == 200 and response.get_json() == {"sent": 0}


def test_reminder_task_works_with_csrf_on(app):
    app.config.update(CSRF_ENABLED=True, TASK_TOKEN="s3cret")
    response = app.test_client().post("/tasks/send-reminders", headers={"X-Task-Token": "s3cret"})
    assert response.status_code == 200


def test_render_blueprint_is_valid():
    import yaml
    blueprint = yaml.safe_load(open("render.yaml"))
    web = blueprint["services"][0]
    assert web["disk"]["mountPath"] == "/data"
    assert {"key": "DATABASE", "value": "/data/sportive_circle.db"} in web["envVars"]


def test_legal_pages_never_show_an_admins_personal_email(client, app):
    app.config["ADMIN_EMAILS"] = "someone.personal@uw.edu"
    for path in ("/privacy", "/terms"):
        assert "someone.personal@uw.edu" not in client.get(path).data.decode()
    app.config["CONTACT_EMAIL"] = "sportivecircle.app@gmail.com"
    assert "sportivecircle.app@gmail.com" in client.get("/privacy").data.decode()
