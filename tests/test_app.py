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
    assert b"Please use your @uw.edu email." in response.data


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
    client.post("/events/new", data=event_form(title="Tennis doubles", sport="tennis"))
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
    assert b"Need players now" in client.get("/").data


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
    assert response.status_code == 404 and b"Back to the feed" in response.data


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
    assert b"not deleted" in client.post("/profile/delete", data={"password": "wrong"}, follow_redirects=True).data
    response = client.post("/profile/delete", data={"password": "purple-and-gold"}, follow_redirects=True)
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
        "sport": "tennis", "location": "IMA (Intramural Activities Building)", "skill_level": "All levels",
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
    client.post("/profile/delete", data={"password": "purple-and-gold"})
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
    for coords in filter(None, LOCATION_COORDS.values()):
        lat, lng = coords
        assert 47.64 < lat < 47.67 and -122.33 < lng < -122.28  # all on/around the UW campus


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
    assert b"check the note above for the exact address" in off


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
    from sportive.spirit import earned_badges
    accounts.signup()
    client.post("/events/new", data=event_form())
    _finish_all_events(app)  # a 7 AM game in January
    with app.app_context():
        user_id = get_db().execute("SELECT id FROM users").fetchone()[0]
        assert earned_badges(user_id) == {"first_game", "rain_or_shine", "early_dawg"}
    page = client.get(f"/u/{user_id}").data
    assert b"Husky badges" in page and b"3/8" in page and b"Rain or Shine" in page
    assert b"Host 5 games" in page  # your own locked badges show how to earn them


def test_cancelled_games_dont_count_for_badges(accounts, client, app):
    from sportive.spirit import earned_badges
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    client.post(f"/events/{event_id}/cancel")
    _finish_all_events(app)
    with app.app_context():
        assert earned_badges(1) == set()


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
