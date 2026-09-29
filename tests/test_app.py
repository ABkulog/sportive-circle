import re
from datetime import timedelta
from io import BytesIO

from conftest import event_id_from, make_image
from sportive import create_app
from sportive.db import get_db
from sportive.timeutil import now_local


def form_time(delta):
    return (now_local() + delta).strftime("%Y-%m-%dT%H:%M")


def event_form(**overrides):
    data = {
        "title": "Pickup 5v5", "sport": "basketball", "location": "IMA (Intramural Activities Building)",
        "skill_level": "Casual", "starts_at": form_time(timedelta(days=1)),
        "ends_at": form_time(timedelta(days=1, hours=2)), "players": "", "note": "",
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
    assert b"Hey, Dubs" in client.get("/").data


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
    assert b"Wrong email or password." in accounts.login(password="nope-nope-nope").data


def test_unknown_email_login_still_checks_a_password_hash(accounts, monkeypatch):
    from sportive import auth
    checked = []
    real = auth.check_password_hash
    monkeypatch.setattr(auth, "check_password_hash", lambda h, p: checked.append(h) or real(h, p))
    assert b"Wrong email or password." in accounts.login(email="nobody@uw.edu", password="whatever-123").data
    assert checked and checked[0].startswith("pbkdf2:sha256:1000")   # same work as a real account


def test_reset_page_answers_the_same_with_or_without_an_account(accounts, client):
    accounts.signup()
    accounts.logout()
    answers = []
    for email in ("dubs@uw.edu", "nobody@uw.edu"):
        client.post("/forgot", data={"email": email})
        answers.append([client.post("/reset", data={"code": "000000", "password": "new-password-1",
                                                    "password2": "new-password-1"}).data.count(b"Wrong code")
                        for _ in range(3)])
    assert answers[0] == answers[1] == [1, 1, 1]


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
        b"has to end after it starts": event_form(ends_at=form_time(timedelta(hours=20))),
        b"can&#39;t be before now": event_form(starts_at=form_time(timedelta(hours=-2)),
                                               ends_at=form_time(timedelta(hours=1))),
        b"Please choose a location.": event_form(location="Moon"),
        b"Pick 2 to 100 participants": event_form(players="1"),
    }
    for message, data in cases.items():
        assert message in client.post("/events/new", data=data).data, message


def test_games_cant_last_all_day_but_trips_can(accounts, client):
    """Testers: "Why is the Spikeball 24 hours long?" Court and field games max out at 6 hours."""
    accounts.signup()
    day = dict(starts_at=form_time(timedelta(days=1)), ends_at=form_time(timedelta(days=2)))
    too_long = client.post("/events/new", data=event_form(sport="spikeball", location="The Quad", **day)).data
    assert b"Spikeball events can be at most 6 hours long." in too_long
    trip = event_form(title="Rainier day hike", sport="hiking", location="Off campus (see note)", note="Paradise lot", **day)
    assert client.post("/events/new", data=trip).status_code == 302
    three_days = dict(starts_at=form_time(timedelta(days=1)), ends_at=form_time(timedelta(days=5)))
    assert b"at most 3 days long" in client.post("/events/new", data=event_form(
        sport="snow", location="Off campus (see note)", note="Stevens Pass", **three_days)).data


def test_duplicate_event_is_rejected(accounts, client):
    accounts.signup()
    client.post("/events/new", data=event_form())
    assert b"already been created" in client.post("/events/new", data=event_form()).data


def test_join_leave_and_capacity(accounts, client):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form(players="2")))
    accounts.logout()

    accounts.signup(email="second@uw.edu")
    client.post(f"/events/{event_id}/join")
    assert "You're going".encode() in client.get(f"/events/{event_id}").data
    accounts.logout()

    accounts.signup(email="third@uw.edu")
    response = client.post(f"/events/{event_id}/join", follow_redirects=True)
    assert b"this game is full" in response.data
    accounts.logout()

    accounts.login(email="second@uw.edu")
    client.post(f"/events/{event_id}/leave")
    accounts.logout()
    accounts.login(email="third@uw.edu")
    assert b"You&#39;re in!" in client.post(f"/events/{event_id}/join", follow_redirects=True).data


def test_double_tapping_join_doesnt_crash(accounts, client, app):
    from flask import g
    from sportive import events
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    player = _user_id(app, "player@uw.edu")
    with app.test_request_context():
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (player,)).fetchone()
        stale = events.get_event(event_id)           # the page as it was before the first tap landed
        assert events.try_join(stale)[0] is True
        assert events.try_join(stale) == (False, "You're already going.")


def test_saving_notification_settings_keeps_hidden_kinds_on(accounts, client, app):
    from sportive.notifications import KINDS, settings
    accounts.signup()
    client.post("/settings/notifications", data={kind.key: "1" for kind in KINDS if kind.audience == "everyone"})
    with app.app_context():
        chosen = settings(_user_id(app, "dubs@uw.edu"))
    assert chosen["club_requests"] and chosen["suggestion_trends"]   # not on the page, so not switched off


def test_opening_the_bell_leaves_switched_off_notices_unread(accounts, client, app):
    from sportive.notifications import KINDS, notify
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    client.post("/settings/notifications", data={k.key: "1" for k in KINDS if k.key != "invites"})
    with app.test_request_context():
        notify(me, "invites", "Maya wants you in Hoops", "/events/1")
        get_db().commit()
    client.get("/notifications")
    with app.app_context():
        assert get_db().execute("SELECT read_at FROM notices").fetchone()[0] is None


def test_database_uses_wal_and_waits_for_locks(app):
    with app.app_context():
        assert get_db().execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert get_db().execute("PRAGMA busy_timeout").fetchone()[0] >= 10000


def test_host_cannot_shrink_game_below_who_is_in(accounts, client, app, monkeypatch):
    from sportive import events
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form(players="4")))
    for email in ("a@uw.edu", "b@uw.edu"):
        accounts.logout()
        accounts.signup(email=email)
        client.post(f"/events/{event_id}/join")
    accounts.logout()
    accounts.login(email="host@uw.edu")
    assert b"already taken" in client.post(f"/events/{event_id}/edit", data=event_form(players="2")).data
    # someone joins between the form check and the save
    monkeypatch.setattr(events, "read_players", lambda *args, **kwargs: (2, 0, None))
    assert b"Someone just joined" in client.post(f"/events/{event_id}/edit", data=event_form(players="2")).data
    with app.app_context():
        assert get_db().execute("SELECT max_players FROM events WHERE id = ?", (event_id,)).fetchone()[0] == 4


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
        "starts_in": "15", "duration": "60", "players": "3",
    })
    page = client.get(f"/events/{event_id_from(response)}").data
    assert b"Need 2 more for Soccer" in page
    assert b"1 going of 3" in page
    assert "<strong>Up next</strong>" in client.get("/").data.decode()   # the poster sees their own game once
    accounts.logout()
    accounts.signup(email="someone.else@uw.edu")
    home = client.get("/").data.decode()
    assert 'aria-label="Happening soon"' in home and "<strong>Need 2</strong>" in home   # everyone else: "Need 2"


# ------------------------------------------------------------------ security

def test_csrf_blocks_forged_posts(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "csrf.db"), "SECRET_KEY": "t"})
    assert app.test_client().post("/login", data={"email": "x@uw.edu", "password": "x"}).status_code == 400


def test_non_ascii_csrf_token_and_codes_do_not_crash(tmp_path, accounts, client):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "csrf.db"), "SECRET_KEY": "t"})
    web = app.test_client()
    web.get("/login")
    assert web.post("/login", data={"csrf_token": "é🙂", "email": "x@uw.edu", "password": "x"}).status_code == 400

    accounts.signup(verify=False)
    assert b"Wrong code" in client.post("/verify", data={"code": "１２３é🙂"}).data
    full_width = accounts.code_for("dubs@uw.edu").translate({ord(d): 0xFF10 + int(d) for d in "0123456789"})
    assert client.post("/verify", data={"code": full_width}).status_code == 302


def test_changing_the_password_logs_out_other_devices(accounts, client, app):
    accounts.signup()
    phone = app.test_client()
    phone.post("/login", data={"email": "dubs@uw.edu", "password": "purple-and-gold"})
    assert b"Hey, Dubs" in phone.get("/").data
    done = client.post("/profile/password", data={"current_password": "purple-and-gold",
                                                   "password": "brand-new-pass", "password2": "brand-new-pass"},
                       follow_redirects=True)
    assert b"Password changed" in done.data
    assert b"Hey, Dubs" in client.get("/").data               # this device stays logged in
    assert b"Hey, Dubs" not in phone.get("/").data            # the other one is logged out


def test_new_password_must_be_new_and_not_blank(accounts, client):
    accounts.signup()
    same = client.post("/profile/password", data={"current_password": "purple-and-gold", "password": "purple-and-gold",
                                                  "password2": "purple-and-gold"}, follow_redirects=True)
    assert b"the password you have now" in same.data
    spaces = client.post("/profile/password", data={"current_password": "purple-and-gold", "password": " " * 10,
                                                    "password2": " " * 10}, follow_redirects=True)
    assert b"only spaces" in spaces.data


def test_guessing_the_current_password_locks_like_login(accounts, client):
    accounts.signup()
    wrong = {"current_password": "guess-guess", "password": "brand-new-pass", "password2": "brand-new-pass"}
    for _ in range(10):
        client.post("/profile/password", data=wrong)
    right = dict(wrong, current_password="purple-and-gold")
    assert b"Too many wrong passwords" in client.post("/profile/password", data=right, follow_redirects=True).data


def test_login_next_cannot_redirect_offsite(accounts, client):
    accounts.signup()
    accounts.logout()
    response = client.post("/login", data={"email": "dubs@uw.edu", "password": "purple-and-gold",
                                           "next": "//evil.example"})
    assert response.headers["Location"] == "/"


def test_login_next_rejects_whitespace_and_backslash_tricks(accounts, client):
    accounts.signup()
    for target in ("/\t/evil.example", "/\\evil.example", "/\n/evil.example", "/ /evil.example", "/\x0b/evil.example"):
        accounts.logout()
        response = client.post("/login", data={"email": "dubs@uw.edu", "password": "purple-and-gold",
                                               "next": target})
        assert response.headers["Location"] == "/", target


def test_profile_edit(accounts, client):
    accounts.signup()
    step1 = client.post("/profile/edit", data={"full_name": "Dubs II", "grad_year": "2029", "bio": "Hoops daily"})
    assert step1.headers["Location"] == "/profile/edit/sports"              # screen 2: sports
    assert 'value="basketball" checked' in client.get("/profile/edit/sports").data.decode()  # kept from sign up
    client.post("/profile/edit/sports", data={"sports": ["climbing"]})
    page = client.get("/me/events").data  # any page works; check the profile itself:
    with client.application.app_context():
        user_id = get_db().execute("SELECT id FROM users").fetchone()[0]
    page = client.get(f"/u/{user_id}").data
    assert b"Dubs II" in page and b"Climbing" in page and b"Hoops daily" in page


def test_quick_post_title_counts_down_and_start_is_rounded(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/need-players", data={
        "sport": "basketball", "location": "IMA (Intramural Activities Building)", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "players": "3",
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
    assert timeutil.fmt_relative("2026-09-27 00:43") == "in 1 hr 40 min"
    assert timeutil.fmt_relative("2026-09-27 01:03") == "in 2 hr"        # 1:59 away, not "in 1 hr"
    assert timeutil.fmt_relative("2026-09-27 04:50") == "in 6 hr"        # 5:46 away rounds to the nearest hour
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


def test_resend_cooldown_counts_real_seconds(accounts, app):
    from sportive.auth import SENT_AT_FORMAT, now_to_the_second, resend_wait
    accounts.signup(email="new@uw.edu", verify=False)
    with app.app_context():
        db = get_db()
        sent = now_to_the_second() - timedelta(seconds=30)
        db.execute("UPDATE users SET verify_sent_at = ? WHERE email = 'new@uw.edu'", (sent.strftime(SENT_AT_FORMAT),))
        db.commit()
        assert 28 <= resend_wait("new@uw.edu") <= 32
        db.execute("UPDATE users SET verify_sent_at = ? WHERE email = 'new@uw.edu'",
                   ((sent - timedelta(seconds=40)).strftime(SENT_AT_FORMAT),))
        db.commit()
        assert resend_wait("new@uw.edu") == 0


def test_login_locks_after_too_many_wrong_passwords(accounts):
    accounts.signup()
    accounts.logout()
    for _ in range(10):
        accounts.login(password="wrong-password")
    assert b"Too many wrong passwords" in accounts.login().data  # even the right one is blocked


def test_resend_code_has_a_cooldown_with_a_countdown(accounts, client):
    accounts.signup(verify=False)
    page = client.post("/verify/resend", follow_redirects=True).data.decode()
    assert "Give it a minute" in page
    wait = int(re.search(r'data-countdown="(\d+)"', page).group(1))
    assert 50 <= wait <= 61 and "Resend code in {s}s" in page   # app.js counts down from here


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
        "starts_in": "0", "duration": "30", "players": "4",
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


def test_line_breaks_are_saved_as_one_character(accounts, client, app):
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form(note="a\r\n" * 249 + "b")))  # 499 chars typed
    client.post("/profile/edit", data={"full_name": "Dubs Husky", "grad_year": "2028", "bio": "Hoops\r\ndaily"})
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT note FROM events WHERE id = ?", (event_id,)).fetchone()[0] == "a\n" * 249 + "b"
        assert db.execute("SELECT bio FROM users").fetchone()[0] == "Hoops\ndaily"


def test_calendar_file_has_no_stray_line_breaks_from_the_note(accounts, client):
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form(note="Court 3\r\nBring water\rThanks")))
    body = client.get(f"/events/{event_id}/calendar.ics").data.decode()
    assert "\r" not in body.replace("\r\n", "")
    assert "DESCRIPTION:Court 3\\nBring water\\nThanks" in body.replace("\r\n ", "")


def test_email_only_visible_to_people_you_played_with(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="stranger@uw.edu")
    with app.app_context():
        host_id = get_db().execute("SELECT id FROM users WHERE email = 'host@uw.edu'").fetchone()[0]
    assert b"host@uw.edu" not in client.get(f"/u/{host_id}").data
    client.post(f"/events/{event_id}/join")
    assert b"host@uw.edu" not in client.get(f"/u/{host_id}").data    # joining isn't enough...
    with app.app_context():
        get_db().execute("UPDATE events SET starts_at = '2026-01-10 07:00', ends_at = '2026-01-10 08:00'")
        get_db().commit()
    assert b"host@uw.edu" in client.get(f"/u/{host_id}").data        # ...playing together is


def test_friendly_404(accounts, client):
    accounts.signup()
    response = client.get("/events/9999")
    assert response.status_code == 404 and b"Go home" in response.data


def test_refuses_to_run_publicly_without_secret_key(tmp_path):
    import pytest
    with pytest.raises(RuntimeError):
        create_app({"DATABASE": str(tmp_path / "x.db")})
    for weak in ("dev-only-change-me", "short-key", ""):
        with pytest.raises(RuntimeError):
            create_app({"DATABASE": str(tmp_path / "x.db"), "SECRET_KEY": weak})
    assert create_app({"DATABASE": str(tmp_path / "x.db"), "SECRET_KEY": "k" * 40}).secret_key == "k" * 40


def test_dev_mode_gets_its_own_persistent_secret_key(tmp_path):
    first = create_app({"DATABASE": str(tmp_path / "x.db"), "DEBUG": True})
    second = create_app({"DATABASE": str(tmp_path / "x.db"), "DEBUG": True})
    assert first.secret_key == second.secret_key != "dev-only-change-me"
    assert len(first.secret_key) >= 32


def test_bell_times_say_how_long_ago(monkeypatch):
    from datetime import datetime
    from sportive import timeutil
    monkeypatch.setattr(timeutil, "now_local", lambda: datetime(2026, 9, 29, 15, 0))
    assert timeutil.fmt_ago("2026-09-29 15:00:40") == "Just now"       # rows made by SQLite have seconds too
    assert timeutil.fmt_ago("2026-09-29 14:35") == "25 min ago"
    assert timeutil.fmt_ago("2026-09-29 09:00") == "6 hr ago"
    assert timeutil.fmt_ago("2026-09-29 01:30") == "Today, 1:30 AM"
    assert timeutil.fmt_ago("2026-09-28 22:00") == "Yesterday, 10:00 PM"
    assert timeutil.fmt_ago("2026-09-25 10:00") == "Fri, 10:00 AM"
    assert timeutil.fmt_ago("2026-08-01 10:00") == "Aug 1"
    assert timeutil.fmt_ago("2025-08-01 10:00") == "Aug 1, 2025"


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
    monkeypatch.setattr(reminders, "send_email", lambda to, subject, body, **kwargs: sent.append((to, subject, body)))
    _reminder_setup(accounts, client, app, joined_minutes_before=120)
    with app.app_context():
        assert reminders.send_due_reminders() == 2  # host + player
        assert reminders.send_due_reminders() == 0  # never twice
    assert {to for to, _, _ in sent} == {"host@uw.edu", "player@uw.edu"}
    assert "Evening hoops" in sent[0][1] and "/events/1" in sent[0][2]


def test_moving_a_game_rearms_its_reminders(accounts, client, app, monkeypatch):
    from sportive import reminders
    monkeypatch.setattr(reminders, "send_email", lambda *args, **kwargs: None)
    _reminder_setup(accounts, client, app, joined_minutes_before=120)
    with app.app_context():
        assert reminders.send_due_reminders() == 2
    accounts.logout()
    accounts.login(email="host@uw.edu")
    client.post("/events/1/edit", data=event_form(title="Evening hoops", starts_at=form_time(timedelta(days=1)),
                                                  ends_at=form_time(timedelta(days=1, hours=2))))
    with app.app_context():
        assert get_db().execute("SELECT SUM(reminder_sent) FROM rsvps").fetchone()[0] == 0


def test_no_reminder_for_last_minute_joins_or_opt_outs(accounts, client, app, monkeypatch):
    from sportive import reminders
    sent = []
    monkeypatch.setattr(reminders, "send_email", lambda to, subject, body, **kwargs: sent.append(to))
    _reminder_setup(accounts, client, app, joined_minutes_before=5)
    with app.app_context():
        assert reminders.send_due_reminders() == 0
    assert sent == []


def test_reminder_opt_out(accounts, client, app, monkeypatch):
    from sportive import reminders
    sent = []
    monkeypatch.setattr(reminders, "send_email", lambda to, subject, body, **kwargs: sent.append(to))
    _reminder_setup(accounts, client, app, joined_minutes_before=120)
    client.post("/settings/reminders", data={})  # Settings: the reminders switch turned off
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
        "starts_in": "15", "duration": "60", "players": "3",
    }).data
    assert b"Rowing / Kayaking can&#39;t be played at Denny Field" in quick


def test_every_sport_has_rules():
    from sportive.constants import DEFAULT_PLAYERS, LOCATIONS, SPORT_LOCATIONS, SPORTS
    assert set(SPORT_LOCATIONS) == set(SPORTS) == set(DEFAULT_PLAYERS)
    assert all(place in LOCATIONS for places in SPORT_LOCATIONS.values() for place in places)


def test_host_picks_any_number_of_players(accounts, client, app):
    """The user: "there shouldn't be a cap on each sport... it depends how many each person needs." """
    accounts.signup()
    big = event_id_from(client.post("/events/new", data=event_form(title="Big run", players="30")))  # fine for hoops
    event_id = event_id_from(client.post("/events/new", data=event_form(players="")))  # blank = the usual size
    with app.app_context():
        sizes = dict(get_db().execute("SELECT id, max_players FROM events").fetchall())
    assert sizes[big] == 30 and sizes[event_id] == 10                                    # 5v5 by default
    assert b"Pick 2 to 100 participants" in client.post("/events/new", data=event_form(players="101")).data
    page = client.get("/events/new").data.decode()
    assert 'name="players" type="number"' in page and 'max="100"' in page
    assert "Participants <em>(including you)</em>" in page and "<span>3</span> Participants</h2>" in page


def test_quick_post_player_cap(accounts, client):
    accounts.signup()
    page = client.post("/need-players", data={
        "sport": "tennis", "location": "IMA North Tennis Courts", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "players": "5",
    }).data
    assert b"Pick 2 to 100 participants" not in page and b"can have 2 to" not in page   # 5 for tennis is the host's call


def test_forms_include_sport_rules(accounts, client):
    accounts.signup()
    for url in ("/events/new", "/need-players"):
        page = client.get(url).data
        assert b'id="sport-rules"' in page and b"forms.js" in page


def test_sport_stats_command(accounts, client, app):
    runner = app.test_cli_runner()
    assert "No finished events yet" in runner.invoke(args=["sport-stats"]).output
    accounts.signup()
    client.post("/events/new", data=event_form(players="8"))
    with app.app_context():
        db = get_db()
        db.execute("UPDATE events SET starts_at = '2026-01-01 10:00', ends_at = '2026-01-01 11:00'")
        db.commit()
    output = runner.invoke(args=["sport-stats"]).output
    assert "Basketball" in output and "8.0" in output


# ------------------------------------------------- profile pictures & how it works

def test_how_it_works_is_short_and_public(client):
    page = client.get("/how-it-works").data.decode()
    assert "Sign up with your UW email" in page and "/faq" in page
    assert page.count('class="step"') == 3  # Find a game, Start your own, Join a club: no essays
    for step in ("Find a game", "Start your own", "Join a club"):
        assert step in page
    faq = client.get("/faq")
    assert faq.status_code == 200 and b"Is it free?" in faq.data


def test_new_users_must_add_a_photo(accounts, client):
    accounts.signup(photo=False)
    assert client.get("/").headers["Location"] == "/profile/photo"
    assert client.get("/events/new").headers["Location"] == "/profile/photo"
    assert client.get("/how-it-works").status_code == 200  # still allowed
    response = accounts.upload_photo()
    assert response.headers["Location"] == "/events/new"  # back to the page they tried to open
    assert client.get("/").status_code == 200


def test_first_photo_goes_straight_home(accounts, client):
    accounts.signup(photo=False)
    client.get("/")  # the feed is the normal landing spot, so no special destination
    assert accounts.upload_photo().headers["Location"] == "/"


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
    assert served.size == (640, 640)
    assert not served.getexif()


def test_non_photos_are_rejected(accounts, client):
    accounts.signup(photo=False)
    page = client.post("/profile/photo", data={"photo": (BytesIO(b"<svg onload=alert(1)>"), "x.svg")},
                       content_type="multipart/form-data", follow_redirects=True).data
    assert b"isn&#39;t a photo we can use" in page


def test_huge_pictures_are_refused_before_they_eat_the_servers_memory():
    import pytest
    from PIL import Image
    from sportive.photos import MAX_FULL_DECODE_PIXELS, TOO_BIG, make_avatar
    huge = BytesIO()
    Image.new("L", (4100, 4000)).save(huge, "PNG")          # 16.4 MP, tiny as a file
    assert 4100 * 4000 > MAX_FULL_DECODE_PIXELS
    with pytest.raises(ValueError, match=TOO_BIG):
        make_avatar(huge.getvalue())
    # a big phone JPEG is decoded at reduced size and still comes out upright and square
    exif = Image.Exif()
    exif[0x0112] = 6                                        # "rotate 90°", like a phone held upright
    avatar = Image.open(BytesIO(make_avatar(make_image(size=(6000, 4000), fmt="JPEG", exif=exif))))
    assert avatar.size == (640, 640)


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
    assert SPORT_LOCATIONS["gym"] == ["Fitness Center West (under Elm Hall)", "IMA (Intramural Activities Building)",
                                       "Off campus (see note)"]


def test_ultimate_frisbee_places(accounts, client):
    from sportive.constants import SPORT_LOCATIONS
    assert SPORT_LOCATIONS["ultimate"] == ["Denny Field", "Husky Track", "The Quad",
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
    page = client.get("/profile/photo").data.decode()
    # "Add later" opens a "No problem" pop-up on the same page, with Continue inside it.
    assert 'data-dialog="later-dialog"' in page and "No problem" in page and "data-dialog-continue" in page
    response = client.post("/profile/photo/skip")
    assert response.headers["Location"] == "/"
    feed = client.get("/")
    assert feed.status_code == 200 and b"photo-nudge" not in feed.data  # no banner following you around


def test_add_later_leaves_one_reminder_in_the_bell(accounts, client):
    accounts.signup(photo=False)
    client.post("/profile/photo/skip")
    assert "Add a profile photo" in client.get("/notifications").data.decode()
    accounts.upload_photo()
    assert "Add a profile photo" not in client.get("/notifications").data.decode()  # done: gone


def test_add_later_is_remembered(accounts, client, app):
    accounts.signup(photo=False)
    client.post("/profile/photo/skip")
    accounts.logout()
    accounts.login()
    assert client.get("/").status_code == 200           # not asked again at every login
    me = _user_id(app, "dubs@uw.edu")
    profile = client.get(f"/u/{me}").data.decode()
    assert ">Add photo</a>" not in profile and ">Edit profile</a>" in profile   # one button; the photo is in there
    assert "Add photo" in client.get("/profile/edit").data.decode()
    photo_page = client.get("/profile/photo").data.decode()
    assert "Add later" not in photo_page and "Step 3 of 3" not in photo_page


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
    monkeypatch.setattr(reminders, "send_email", lambda to, subject, body, **kwargs: sent.update({to: (subject, body)}))
    _reminder_setup(accounts, client, app, joined_minutes_before=120)
    with app.app_context():
        reminders.send_due_reminders()
    subject, body = sent["player@uw.edu"]
    assert re.fullmatch(r"Evening hoops starts in \d+ min", subject)
    assert "Hey Dubs, your game is coming up" in body and "You + 1 other\n" in body and "Tap “Leave”" in body
    assert "Settings → Email" in body and "30 min" in body
    host_subject, host_body = sent["host@uw.edu"]
    assert "You're the host" in host_body


def test_reminders_run_by_themselves(accounts, client, app, monkeypatch):
    """No outside scheduler needed: each round sends what's due, and nobody gets a reminder twice,
    even when two copies of the app check at the same moment."""
    from sportive import reminders
    sent = []
    monkeypatch.setattr(reminders, "send_email", lambda to, subject, body, **kwargs: sent.append(to))
    _reminder_setup(accounts, client, app, joined_minutes_before=120)
    reminders.reminder_round(app)
    reminders.reminder_round(app)
    assert sorted(sent) == ["host@uw.edu", "player@uw.edu"]

    with app.app_context():
        get_db().execute("UPDATE rsvps SET reminder_sent = 0")
        get_db().commit()
    sent.clear()
    other_copy_ran = []

    def send_while_another_copy_checks(to, subject, body, **kwargs):
        sent.append(to)
        if not other_copy_ran:  # this copy already read both reminders; now the other copy checks too
            other_copy_ran.append(True)
            reminders.reminder_round(app)
    monkeypatch.setattr(reminders, "send_email", send_while_another_copy_checks)
    reminders.reminder_round(app)
    assert sorted(sent) == ["host@uw.edu", "player@uw.edu"]


def test_reminder_loop_only_runs_on_the_server(tmp_path, monkeypatch):
    from sportive import reminders
    started = []
    monkeypatch.setattr(reminders, "start_reminder_loop", lambda app: started.append(app))
    monkeypatch.delenv("REMINDER_LOOP", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "t" * 40)
    create_app({"DATABASE": str(tmp_path / "a.db")})
    assert started == []  # a laptop doesn't email anyone
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://sportive-circle.onrender.com")
    create_app({"DATABASE": str(tmp_path / "a.db")})
    assert len(started) == 1
    create_app({"TESTING": True, "DATABASE": str(tmp_path / "a.db")})
    assert len(started) == 1  # never during tests


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
    off = client.get(f"/events/{event_id_from(client.post('/events/new', data=event_form(title='Hike', sport='hiking', location='Off campus (see note)', note='Rattlesnake Ledge lot')))}").data
    assert b"the address is in the note" in off and b"Rattlesnake Ledge lot" in off
    no_note = client.post("/events/new", data=event_form(title="Hike 2", sport="hiking", location="Off campus (see note)"),
                          follow_redirects=True).data
    assert b"Off campus: add where in the note" in no_note


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
    assert b'value="month" selected>Rest of September<' in page and b">Next 7 days<" in page
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
    _joined_in_founding_year(app)


def test_founding_dawg_deadline_uses_seattle_time_not_utc(accounts, app):
    from sportive.badges import eligible
    from sportive.timeutil import from_sqlite_utc
    assert str(from_sqlite_utc("2027-01-01 05:30:00")) == "2026-12-31 21:30:00"
    accounts.signup(email="late@uw.edu")
    user = _user_id(app, "late@uw.edu")
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET created_at = '2027-01-01 05:30:00' WHERE id = ?", (user,))  # 9:30 PM Dec 31 here
        db.commit()
        assert "founding_dawg" in eligible(user)
        db.execute("UPDATE users SET created_at = '2027-01-01 09:00:00' WHERE id = ?", (user,))  # 1 AM Jan 1 here
        db.commit()
        assert "founding_dawg" not in eligible(user)


def _joined_in_founding_year(app):
    """Accounts get SQLite's real clock as created_at; pin it so Founding Dawg tests still pass after 2026."""
    with app.app_context():
        get_db().execute("UPDATE users SET created_at = '2026-09-01 10:00:00'")
        get_db().commit()


def test_greeting_is_plain(accounts, client):
    from sportive.spirit import greeting
    assert greeting("Maya") == "Hey, Maya"
    accounts.signup(name="Maya Chen")
    page = client.get("/").data.decode()
    assert "Hey, Maya" in page and "Late night" not in page and "Bow down" not in page


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
    assert b"flash-celebrate" in response and b"Your game is up!" in response
    assert b"Made by Huskies, for Huskies" in response
    assert b"Not an official University of Washington service" in response


# ------------------------------------------------------------ badges

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
    _joined_in_founding_year(app)
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
    assert " new badges: " in feed and feed.count("New badge:") == 0


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
    assert b">Friends</span>" in client.get(f"/u/{b}").data
    client.post(f"/friends/remove/{b}")
    assert b"+ Add friend" in client.get(f"/u/{b}").data


def test_played_with_suggestions(accounts, client, app):
    accounts.signup(email="a@uw.edu", name="Alex Ace")
    accounts.logout()
    accounts.signup(email="b@uw.edu", name="Blake Buddy")
    a, b = _user_id(app, "a@uw.edu"), _user_id(app, "b@uw.edu")
    _played_games(app, "soccer", [a, b], count=2)
    page = client.get("/friends").data
    assert b"Suggested for you" in page and b"Alex Ace" in page and b"2 games together" in page


def test_friends_of_friends_are_suggested(accounts, client, app):
    """Mutuals: people your friends are friends with show up under "Suggested for you" with a reason."""
    ids = _people(accounts, app, "Me", "Maya", "Sam", "Riley", "Blocked", "Pending")
    _friends(app, ids["Me"], ids["Maya"], ids["Sam"])
    _friends(app, ids["Maya"], ids["Riley"], ids["Blocked"], ids["Pending"])
    _friends(app, ids["Sam"], ids["Riley"])
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, '2026-09-01 10:00')",
                   (ids["Me"], ids["Blocked"]))
        db.execute("INSERT INTO friendships (requester_id, addressee_id, status, created_at)"
                   " VALUES (?, ?, 'pending', '2026-09-01 10:00')", (ids["Me"], ids["Pending"]))
        db.commit()
    _as(accounts, "Me")
    page = client.get("/friends").data.decode()
    section = page[page.index("Suggested for you"):page.index("Your pack")]
    assert "Riley Husky" in section and "Friends with Maya + 1 more" in section   # Maya and Sam both know Riley
    assert "Blocked Husky" not in section and "Pending Husky" not in section       # blocked / already asked
    assert "Maya Husky" not in section and "Sam Husky" not in section              # already friends
    assert "Suggested for you" not in client.get("/friends?q=riley").data.decode()   # not while searching
    client.post(f"/friends/request/{ids['Riley']}", data={"next": "/friends"})
    assert "Riley Husky" not in client.get("/friends").data.decode().split("Your pack")[0].split("Suggested")[-1]


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
    assert b"Join the game to use its chat" in outside and b"Court 3" not in outside
    assert client.get(f"/events/{event_id}/chat/poll").status_code == 403
    client.post(f"/events/{event_id}/join")
    detail = client.get(f"/events/{event_id}").data
    assert f'href="/events/{event_id}/chat"'.encode() in detail and b'<span class="count-dot">1</span>' in detail
    assert b"Court 3, bring a light shirt" in client.get(f"/events/{event_id}/chat").data
    assert b'<span class="count-dot">1</span>' not in client.get(f"/events/{event_id}").data  # seen now
    client.post(f"/events/{event_id}/chat", data={"body": "on my way!"})
    msgs = client.get(f"/events/{event_id}/chat/poll?after=1").get_json()["messages"]
    assert [m["body"] for m in msgs] == ["on my way!"]


def test_blocking_takes_them_off_your_upcoming_games(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    client.post(f"/events/{event_id}/join")
    accounts.logout()
    accounts.login(email="host@uw.edu")
    client.post(f"/block/{_user_id(app, 'player@uw.edu')}")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (event_id,)).fetchone()[0] == 1


def test_game_chat_hides_people_you_blocked(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    client.post(f"/events/{event_id}/join")
    client.post(f"/events/{event_id}/chat", data={"body": "you're trash lol"})
    accounts.logout()
    accounts.login(email="host@uw.edu")
    client.post(f"/block/{_user_id(app, 'player@uw.edu')}")
    assert b"trash" not in client.get(f"/events/{event_id}/chat").data
    assert b'<span class="count-dot">' not in client.get(f"/events/{event_id}").data


# ------------------------------------------------------------ delete

def test_delete_account_needs_are_you_sure(accounts, client, app):
    accounts.signup()
    client.post("/events/new", data=event_form())
    page = client.get("/profile/delete").data.decode()
    assert "Delete your account?" in page and "No, keep my account" in page and "can't be undone" in page
    assert "upcoming game you host" in page
    wrong = client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "yes"},
                        follow_redirects=True).data
    assert b"Type DELETE" in wrong
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1   # still here
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "delete"})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


# ------------------------------------------------------------ helpers

def _befriend(client, accounts, a_email, b_email, app):
    accounts.login(email=a_email)
    client.post(f"/friends/request/{_user_id(app, b_email)}")
    accounts.logout()
    accounts.login(email=b_email)
    client.post(f"/friends/accept/{_user_id(app, a_email)}")
    accounts.logout()


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
    assert "Casual roundnet" in page and "✓</span> Verified</span>" in page and "Sign up to join" in page
    assert "No experience needed" in page and "Come to any Tuesday practice!" in page and "@uwspikeball" in page
    assert "Cap Tain" not in page                             # member names need an account


def test_club_create_validation(accounts, client):
    accounts.signup()
    assert b"https://" in client.post("/clubs/new", data={**CLUB, "contact_url": "javascript:alert(1)"}).data
    assert b"HuskyLink page" not in client.post("/clubs/new", data={**CLUB, "name": "X Club",
                                                                    "verification_url": "https://myclub.com"}).data
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
    assert "Open to all levels" in form_page and 'name="skill_level"' not in form_page
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
    for label in ("Home", "Clubs", "Create", "Profile", "Messages", "Friends", "FAQ"):
        assert f'<span class="tab-label">{label}<' in page, label
    assert '<span class="tab-label">News<' not in page                       # one thing: playing
    assert 'class="tab is-active" href="/" aria-current="page"' in page      # Home is highlighted
    assert 'aria-label="FAQ"' in page                                       # ❓ in the top bar opens the FAQ
    assert "For you" in page and "My events" in page                        # Home tabs
    menu = client.get("/create").data.decode()
    assert "Need players" in menu and "New event" in menu and "Register your club" in menu


def test_visitors_get_simple_menu(client):
    page = client.get("/").data.decode()
    assert 'class="appnav"' not in page and "/clubs" in page and "How it works" in page


def test_joining_a_game_doesnt_unlock_direct_messages_until_it_ends(accounts, client, app):
    from sportive.social import can_message
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="stranger@uw.edu")
    client.post(f"/events/{event_id}/join")
    host, stranger = _user_id(app, "host@uw.edu"), _user_id(app, "stranger@uw.edu")
    with app.app_context():
        assert not can_message(stranger, host)
        get_db().execute("UPDATE events SET starts_at = '2026-01-10 07:00', ends_at = '2026-01-10 08:00'")
        get_db().commit()
        assert can_message(stranger, host)


def test_long_chats_show_the_newest_messages(accounts, client, app):
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    me = _user_id(app, "dubs@uw.edu")
    with app.app_context():
        get_db().executemany("INSERT INTO event_messages (event_id, sender_id, body, created_at) VALUES (?, ?, ?, ?)",
                             [(event_id, me, f"msg-{i:04d}", "2026-09-01 10:00") for i in range(520)])
        get_db().commit()
    page = client.get(f"/events/{event_id}/chat").data.decode()
    assert "msg-0519" in page and "msg-0000" not in page
    assert page.index("msg-0100") < page.index("msg-0519")        # still oldest first


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
    assert "Thanks. We&#39;ll look into it" in done and "You&#39;ve also blocked them" in done
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
    assert 'aria-label="Admin' in page and "Threats or violence" in page
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
    monkeypatch.setattr(clubs, "send_email", lambda to, subject, body, **kwargs: sent.append((to, subject)))
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app)
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    queue = client.get("/admin/clubs").data.decode()
    assert "UW Spikeball Club" in queue and "instagram.com/uwspikeball" in queue   # its socials, to check it
    assert "~30 active members" in queue
    assert b"Add a short note" in client.post(f"/admin/clubs/{club}/reject", follow_redirects=True).data
    client.post(f"/admin/clubs/{club}/reject", data={"note": "That Instagram is for a different club."})
    assert sent[-1][0] == "captain@uw.edu"
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    page = client.get(f"/clubs/{club}").data.decode()
    assert "different club" in page and "Update and resubmit" in page
    client.post(f"/clubs/{club}/edit", data={**CLUB, "description": "Casual roundnet on the Quad, every Tuesday!"})
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
                                    "experience": "experienced", "dues": "$60/quarter"})
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
    assert b"Answer the club&#39;s question" in client.post(f"/clubs/{club}/join", follow_redirects=True).data
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
    # A social account or a website is required (either one, or both)...
    page = client.post("/clubs/new", data={**CLUB, "instagram": "", "contact_url": ""}).data
    assert b"Add at least one of your club" in page and b'data-error-field="instagram"' in page
    client.post("/clubs/new", data={**CLUB, "name": "Website Only Club", "instagram": "",
                                    "contact_url": "https://websiteonly.example.com"})       # a website alone is fine
    with client.application.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM clubs WHERE name = 'Website Only Club'").fetchone()[0] == 1
        get_db().execute("DELETE FROM clubs WHERE name = 'Website Only Club'")
        get_db().commit()
    # ...while a website is optional, and the HuskyLink page isn't asked at all.
    assert b'name="verification_url"' not in client.get("/clubs/new").data
    client.post("/clubs/new", data={**CLUB, "instagram": "", "tiktok": "uwspike", "contact_url": "",
                                    "verification_url": ""})
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
        "starts_in": "15", "duration": "60", "players": "3"})
    event_id = event_id_from(response)
    page = client.get(f"/events/{event_id}/chat")
    assert page.status_code == 200 and b"Need 2 more for Soccer" in page.data


def test_empty_chat_shows_a_real_empty_state(accounts, client):
    accounts.signup()
    game = event_id_from(client.post("/events/new", data=event_form()))
    page = client.get(f"/events/{game}/chat").data.decode()
    assert 'class="chat card is-empty"' in page and "No messages yet. Say hi!" in page
    client.post(f"/events/{game}/chat", data={"body": "Who's bringing a ball?"})
    assert "is-empty" not in client.get(f"/events/{game}/chat").data.decode()
    other = event_id_from(client.post("/events/new", data=event_form(title="Called off")))
    client.post(f"/events/{other}/cancel")
    closed = client.get(f"/events/{other}/chat").data.decode()
    assert "Say hi!" not in closed and "No messages." in closed      # a closed chat doesn't invite a message


def test_deleting_a_host_keeps_the_games_other_people_played(accounts, client, app):
    from sportive.timeutil import to_db
    accounts.signup(email="host@uw.edu")
    played = event_id_from(client.post("/events/new", data=event_form(title="Last week's run")))
    alone = event_id_from(client.post("/events/new", data=event_form(title="Nobody came")))
    upcoming = event_id_from(client.post("/events/new", data=event_form(title="Next week's run")))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    client.post(f"/events/{played}/join")
    client.post(f"/events/{upcoming}/join")
    with app.app_context():
        db = get_db()
        past = now_local() - timedelta(days=7)
        db.execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id IN (?, ?)",
                   (to_db(past), to_db(past + timedelta(hours=1)), played, alone))
        db.commit()
    accounts.logout()
    accounts.login(email="host@uw.edu")
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    with app.app_context():
        db = get_db()
        left = {row[0] for row in db.execute("SELECT id FROM events")}
        assert left == {played}                           # history kept; the rest goes with the account
        former = db.execute("SELECT u.email, u.verified FROM events e JOIN users u ON u.id = e.host_id").fetchone()
        assert former["email"] == "former-member@sportive.invalid" and former["verified"] == 0
    accounts.login(email="player@uw.edu")
    assert "Last week&#39;s run" in client.get("/me/events").data.decode()
    detail = client.get(f"/events/{played}").data.decode()
    assert "Former member" in detail
    with app.app_context():
        former_id = get_db().execute("SELECT host_id FROM events").fetchone()[0]
    assert f'href="/u/{former_id}"' not in detail                 # no link to a profile that doesn't exist
    assert b"Former member" not in client.get("/friends?q=Former").data


def test_only_officer_cant_delete_account(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu")
    accounts.logout()
    with app.app_context():
        get_db().execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'member', '2026-01-01 10:00')",
                         (club, _user_id(app, "fan@uw.edu")))
        get_db().commit()
    accounts.login(email="captain@uw.edu")
    assert "the only officer" in client.get("/profile/delete").data.decode()
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM users WHERE email = 'captain@uw.edu'").fetchone()[0] == 1


def test_make_officer_only_reports_success_when_it_worked(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu")
    client.post(f"/clubs/{club}/follow")               # a follower, not a member
    fan = _user_id(app, "fan@uw.edu")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    page = client.post(f"/clubs/{club}/officers/{fan}", follow_redirects=True).data.decode()
    assert "Only confirmed members can be made officers" in page and "officer now" not in page


def test_officers_can_step_down_but_one_always_stays(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu")
    client.post(f"/clubs/{club}/join", data={"message": "hi"})
    fan = _user_id(app, "fan@uw.edu")
    captain = _user_id(app, "captain@uw.edu")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    page = client.post(f"/clubs/{club}/officers/{captain}/step-down", follow_redirects=True).data.decode()
    assert "at least one officer" in page
    client.post(f"/clubs/{club}/members/{fan}/approve")
    client.post(f"/clubs/{club}/officers/{fan}")
    assert "Make regular member" in client.get(f"/clubs/{club}").data.decode()
    client.post(f"/clubs/{club}/officers/{fan}/step-down")
    with app.app_context():
        role = get_db().execute("SELECT role FROM club_members WHERE club_id = ? AND user_id = ?", (club, fan)).fetchone()[0]
    assert role == "member"


def test_pending_club_doesnt_block_deleting_the_account(accounts, client, app):
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    page = client.get("/profile/delete").data.decode()
    assert "the only officer" not in page and "deleted too" in page
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) FROM users WHERE email = 'captain@uw.edu'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM clubs").fetchone()[0] == 0


def test_signup_cant_flood_an_inbox(accounts, client):
    accounts.signup(email="target@uw.edu", verify=False)
    client.post("/logout")
    again = accounts.signup(email="target@uw.edu", verify=False).data
    assert b"We just sent a code to that email" in again


# ------------------------------------------------------------ launch-readiness checks

def test_same_names_can_be_told_apart(accounts, client, app):
    """Two Maya Chens: search by NetID finds the right one; results show clues (class, mutual friends)."""
    accounts.signup(email="mchen7@uw.edu", name="Maya Chen")
    accounts.logout()
    accounts.signup(email="mchen22@uw.edu", name="Maya Chen")
    accounts.logout()
    accounts.signup(email="friend@uw.edu", name="Fran Friend")
    fran, maya7 = _user_id(app, "friend@uw.edu"), _user_id(app, "mchen7@uw.edu")
    client.post(f"/friends/request/{maya7}")
    accounts.logout()
    accounts.login(email="mchen7@uw.edu")
    client.post(f"/friends/accept/{fran}")
    accounts.logout()
    accounts.signup(email="me@uw.edu", name="Me Myself")
    client.post(f"/friends/request/{fran}")
    accounts.logout()
    accounts.login(email="friend@uw.edu")
    client.post(f"/friends/accept/{_user_id(app, 'me@uw.edu')}")
    accounts.logout()
    accounts.login(email="me@uw.edu")
    by_name = client.get("/friends?q=maya+chen").data.decode()
    assert by_name.count("<strong>Maya Chen</strong>") == 2
    assert "1 mutual friend" in by_name                                   # the one Fran knows
    by_netid = client.get("/friends?q=mchen22").data.decode()
    assert by_netid.count("<strong>Maya Chen</strong>") == 1 and f"/u/{maya7}" not in by_netid
    assert client.get("/friends?q=mchen22@uw.edu").data.decode().count("<strong>Maya Chen</strong>") == 1
    assert "<strong>Maya Chen</strong>" not in client.get("/friends?q=mchen2").data.decode()  # whole NetIDs only
    assert "mchen22@uw.edu" not in by_netid                                 # emails stay private


def test_profile_pronouns_gender_and_socials(accounts, client, app):
    accounts.signup(name="Maya Chen")
    me = _user_id(app, "dubs@uw.edu")
    form = {"full_name": "Maya Chen", "grad_year": "2028", "bio": "", "pronouns": "she/her", "gender": "woman"}
    socials = {"sports": ["soccer"], "instagram": "@maya.hoops", "snapchat": "", "tiktok": "", "x_handle": ""}
    client.post("/profile/edit", data=form)
    client.post("/profile/edit/sports", data=socials)                 # screen 2: socials and sports
    page = client.get(f"/u/{me}").data.decode()
    assert "Class of 2028 · she/her · Woman" in page
    assert 'href="https://instagram.com/maya.hoops"' in page and "@maya.hoops" in page
    bad = client.post("/profile/edit/sports", data={**socials, "instagram": "not a handle!"}).data
    assert b"Instagram username doesn" in bad and b'value="not a handle!"' in bad   # kept, so it can be fixed
    assert b"pick an option for gender" in client.post("/profile/edit", data={**form, "gender": "robot"},
                                                          follow_redirects=True).data
    client.post("/profile/edit", data={**form, "pronouns": "", "gender": ""})
    client.post("/profile/edit/sports", data={**socials, "instagram": ""})
    page = client.get(f"/u/{me}").data.decode()
    assert "she/her" not in page and "Woman" not in page and "instagram.com" not in page   # all optional


def test_admins_give_the_tester_badge(accounts, client, app):
    accounts.signup(email="tester@uw.edu", name="Tess Tester")
    tess = _user_id(app, "tester@uw.edu")
    assert client.post(f"/admin/users/{tess}/tester/give").status_code == 404   # not an admin: no such page
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM user_badges WHERE badge = 'tester'").fetchone()[0] == 0
    accounts.logout()
    accounts.signup(email="boss@uw.edu", name="Bo Boss")
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    assert "Give Tester badge" in client.get(f"/u/{tess}").data.decode()
    client.post(f"/admin/users/{tess}/tester/give")
    with app.app_context():
        from sportive.badges import earned_badges, sync_badges
        sync_badges(tess)                                  # daily badge syncing doesn't remove it
        assert "tester" in earned_badges(tess)
    assert "Take back Tester badge" in client.get(f"/u/{tess}").data.decode()
    accounts.logout()
    accounts.login(email="tester@uw.edu")
    locker = client.get("/profile/badges").data.decode()
    assert "Tester" in locker
    accounts.logout()
    accounts.signup(email="other@uw.edu")
    still_to_earn = client.get("/profile/badges").data.decode()
    assert "Helped test Sportive Circle" not in still_to_earn   # nobody can "earn" it


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
        text = template.read_text(encoding="utf-8")
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


def test_admins_can_find_and_restore_suspended_accounts(accounts, client, app):
    accounts.signup(email="bad@uw.edu", name="Rowan Ruleb")
    bad = _user_id(app, "bad@uw.edu")
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    client.post(f"/admin/users/{bad}/suspend")
    page = client.get("/admin/reports?status=suspended").data.decode()
    assert "Suspended accounts (1)" in page and "Rowan Ruleb" in page and "Restore account" in page
    response = client.post(f"/admin/users/{bad}/restore?from=suspended")
    assert "status=suspended" in response.headers["Location"]
    assert "No suspended accounts." in client.get("/admin/reports?status=suspended").data.decode()


def test_suspended_login_says_where_to_appeal(accounts, client, app):
    accounts.signup(email="bad@uw.edu")
    accounts.logout()
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 1 WHERE email = 'bad@uw.edu'")
        get_db().commit()
    app.config["CONTACT_EMAIL"] = "help@sportive.test"
    page = accounts.login(email="bad@uw.edu").data.decode()
    assert "Email help@sportive.test from this address" in page


def test_suspending_tells_players_and_frees_their_spots(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    hosted = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="other@uw.edu")
    others_game = event_id_from(client.post("/events/new", data=event_form()))
    client.post(f"/events/{hosted}/join")
    accounts.logout()
    accounts.login(email="host@uw.edu")
    client.post(f"/events/{others_game}/join")
    host = _user_id(app, "host@uw.edu")
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    client.post(f"/admin/users/{host}/suspend")
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (others_game, host)).fetchone() is None
        other = _user_id(app, "other@uw.edu")
        assert db.execute("SELECT 1 FROM notices WHERE user_id = ? AND text LIKE '%canceled%'",
                          (other,)).fetchone() is not None


def test_error_flashes_interrupt_screen_readers(accounts, client):
    accounts.signup()
    accounts.logout()
    page = accounts.login(password="wrong-password").data.decode()
    assert '<div class="flash flash-error" role="alert">Wrong email or password.</div>' in page


def test_wrong_password_keeps_the_email_and_focuses_the_password(accounts, client):
    accounts.signup()
    accounts.logout()
    page = accounts.login(password="wrong-password").data.decode()
    assert 'value="dubs@uw.edu"' in page
    assert re.search(r'name="password"[^>]*autofocus', page)


def test_error_page_shows_the_specific_reason(client, app):
    from flask import abort

    @app.route("/expired")
    def expired():
        abort(400, "Your form expired. Go back, refresh the page and try again.")
    assert b"Your form expired" in client.get("/expired").data
    assert b"This Dawg got lost" in client.get("/no-such-page").data


def test_https_responses_tell_browsers_to_stay_on_https(client):
    assert "Strict-Transport-Security" not in client.get("/").headers      # local http: never
    secure = client.get("/", base_url="https://localhost")
    assert secure.headers["Strict-Transport-Security"].startswith("max-age=31536000")


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
    """The submitted value is always the plain level name."""
    accounts.signup()
    for page in ("/events/new", "/need-players"):
        html = client.get(page).data.decode()
        for level in ("All levels", "Casual", "Intermediate", "Competitive"):
            assert f'<option value="{level}"' in html, (page, level)


def test_dropdowns_are_alphabetical():
    from sportive.constants import LOCATIONS, SPORT_LOCATIONS, SPORTS
    labels = list(SPORTS.values())
    assert labels[:-1] == sorted(labels[:-1]) and labels[-1] == "Other"
    places = [place.removeprefix("The ") for place in LOCATIONS[:-2]]
    assert places == sorted(places) and LOCATIONS[-2:] == ["Off campus (see note)", "Online"]
    for sport, allowed in SPORT_LOCATIONS.items():
        assert allowed == sorted(allowed, key=LOCATIONS.index), sport


def test_no_gold_dot_under_the_active_tab_and_css_updates_reach_phones(accounts, client):
    """Testers: the yellow dot under the selected tab covered the tab's text on iPhones."""
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    assert ".tab-icon::after" not in css and ".tab.is-active .tab-icon::after" not in css
    accounts.signup()
    page = client.get("/").data.decode()
    # ?v= changes whenever the file changes, so Safari can't keep showing the old look
    assert re.search(r'/static/style\.css\?v=\d+', page) and re.search(r'/static/app\.js\?v=\d+', page)


def test_hidden_always_hides():
    """Fields hidden by JavaScript (like tryout spots on Casual games) must really disappear,
    even when their class sets display: grid or flex."""
    import pathlib
    assert "[hidden] { display: none !important; }" in pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")


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

        def flaky(to, subject, body, **kwargs):
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
                                                  "starts_in": "15", "duration": "60", "players": "4"})
    page = client.get(f"/events/{event_id_from(response)}/chat").data.decode()
    assert "<title>Chat · Need 3 more for Soccer" in page


def test_hidden_pill_inputs_cant_widen_the_page():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    assert ".segmented input, .chip-check input, .choice-pill input {" in css and "width: 1px; height: 1px" in css


def _css_classes_used_but_undefined(names):
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    return [name for name in names if not re.search(r"\." + re.escape(name) + r"\b", css)]


def test_fine_print_has_a_style():
    assert _css_classes_used_but_undefined(["fine-print"]) == []


def test_filtering_the_feed_keeps_need_players_posts_in_the_results(accounts, client):
    accounts.signup(email="host@uw.edu")
    client.post("/need-players", data={"sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
                                       "starts_in": "15", "duration": "60", "players": "4"})
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    unfiltered = client.get("/?scope=all").data.decode()
    assert 'id="soon-title"' in unfiltered
    filtered = client.get("/?scope=all&sport=soccer").data.decode()
    assert 'id="soon-title"' not in filtered and "No games yet" not in filtered


def test_need_players_strip_drops_games_well_under_way(accounts, client, app):
    from sportive.timeutil import to_db
    accounts.signup(email="host@uw.edu")
    client.post("/need-players", data={"sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
                                       "starts_in": "15", "duration": "120", "players": "4"})
    with app.app_context():
        db = get_db()
        now = now_local()
        db.execute("UPDATE events SET starts_at = ?, ends_at = ?",
                   (to_db(now - timedelta(hours=1)), to_db(now + timedelta(minutes=10))))
        db.commit()
    assert 'id="soon-title"' in client.get("/?scope=all").data.decode()  # the host can still find it
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    assert 'id="soon-title"' not in client.get("/?scope=all").data.decode()


def test_feed_shows_more_games_a_page_at_a_time(accounts, client, monkeypatch):
    from sportive import events
    monkeypatch.setattr(events, "FEED_PAGE_SIZE", 2)
    accounts.signup(email="host@uw.edu")
    for i in range(3):
        client.post("/events/new", data=event_form(title=f"Run number {i}",
                                                   starts_at=form_time(timedelta(days=i + 1)),
                                                   ends_at=form_time(timedelta(days=i + 1, hours=1))))
    first = client.get("/?scope=all&sport=basketball").data.decode()
    assert first.count("Run number") == 2 and "Show more games" in first
    assert "page=2" in first and "sport=basketball" in first.split("Show more games")[0].rsplit("href=", 1)[1]
    second = client.get("/?scope=all&sport=basketball&page=2").data.decode()
    assert second.count("Run number") == 3 and "Show more games" not in second
    assert client.get("/?scope=all&page=abc").status_code == 200


def test_skill_filter_includes_all_levels_games(accounts, client):
    accounts.signup(email="host@uw.edu")
    client.post("/events/new", data=event_form(title="Everyone welcome run", skill_level="All levels"))
    client.post("/events/new", data=event_form(title="Sweaty comp run", skill_level="Competitive"))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    page = client.get("/?scope=all&skill=Casual").data.decode()
    assert "Everyone welcome run" in page and "Sweaty comp run" not in page


def test_empty_feed_says_when_the_filters_are_the_reason(accounts, client):
    accounts.signup()
    page = client.get("/?scope=all&sport=soccer&when=today").data.decode()
    assert "No games match these filters." in page and "No games yet" not in page
    assert "No games yet" in client.get("/?scope=all").data.decode()


def test_a_message_that_cant_be_sent_stays_in_the_box(accounts, client):
    accounts.signup()
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    too_long = "x" * 990 + " 🐾" * 10
    page = client.post(f"/events/{event_id}/chat", data={"body": too_long}, follow_redirects=True).data.decode()
    assert "Messages can be up to 1000 characters." in page
    assert f"autofocus>{too_long[:1000]}</textarea>" in page
    assert too_long[:50] not in client.get(f"/events/{event_id}/chat").data.decode()   # only brought back once


def test_every_body_font_weight_in_the_css_is_loaded():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    base = pathlib.Path("sportive/templates/base.html").read_text(encoding="utf-8")
    low, high = map(int, re.search(r"Open\+Sans:wght@(\d+)\.\.(\d+)", base).groups())
    body_weights = {int(w) for w in re.findall(r"font-weight:\s*(\d+)", css)} - {800}   # 800 = display font
    assert all(low <= weight <= high for weight in body_weights), body_weights


def test_long_unbroken_titles_wrap_instead_of_widening_the_page():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    assert "h1, h2, h3 { line-height: 1.2; margin: 0 0 .5rem; overflow-wrap: break-word; }" in css
    for rule in (".event-title {", ".club-name {"):
        assert "overflow-wrap: anywhere" in css.split(rule, 1)[1].split("}", 1)[0], rule


def test_templates_dont_use_class_names_with_no_style():
    import pathlib
    templates = " ".join(p.read_text(encoding="utf-8") for p in pathlib.Path("sportive/templates").rglob("*.html"))
    for dead in ("is-hot", "tab-create", "feed-hello", "club-card mini"):
        assert dead not in templates, dead


def test_small_segmented_control_is_compact():
    import pathlib
    assert ".segmented.small span" in pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")


def test_wizard_moves_focus_into_the_new_step():
    import pathlib
    js = pathlib.Path("sportive/static/wizard.js").read_text(encoding="utf-8")
    assert "function focusStep()" in js
    assert re.search(r"show\(current \+ 1\);\s*focusStep\(\);", js)
    assert re.search(r"show\(current - 1\); focusStep\(\);", js)


def test_scripts_do_not_depend_on_request_submit_alone():
    # requestSubmit is Safari 16+; older iPhones need the dispatch + submit() fallback.
    import pathlib
    for name in ("app.js", "chat.js"):
        js = pathlib.Path("sportive/static", name).read_text(encoding="utf-8")
        calls = re.findall(r"(\w+(?:\.\w+)*)\.requestSubmit\(\)", js)
        for form in calls:
            assert f"if ({form}.requestSubmit)" in js, (name, form)
        assert "form.submit()" in js, name


def _contrast(a, b):
    def lum(hex_color):
        rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _theme_colors():
    """{"light": {...}, "dark": {...}} custom properties from style.css."""
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    blocks = {"light": re.search(r":root \{(.*?)\n\}", css, re.S).group(1),
              "dark": re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}', css, re.S).group(1)}
    colors = {name: dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", body)) for name, body in blocks.items()}
    colors["dark"] = {**colors["light"], **colors["dark"]}
    return colors


def test_count_badges_are_readable_in_both_themes():
    for theme, c in _theme_colors().items():
        assert _contrast(c["--danger"], c["--on-danger"]) >= 4.5, theme


def test_team_pill_stays_gold_on_purple_in_dark_mode():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    rule = re.search(r"^\.team-pill \{([^}]*)\}", css, re.M).group(1)
    assert "var(--header)" in rule and "#e8e3d3" in rule    # --purple / --gold-light flip in dark mode
    for theme, c in _theme_colors().items():
        assert _contrast(c["--header"], "#e8e3d3") >= 4.5, theme


def test_gold_text_on_the_purple_header_is_readable():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    assert ".topbar .brand-accent { color: var(--gold-on-header); }" in css
    assert ".husky-hero .gold { color: var(--gold-on-header); }" in css
    for theme, c in _theme_colors().items():
        assert _contrast(c["--header"], c["--gold-on-header"]) >= 4.5, theme


def test_register_your_club_line_has_room_below_the_grid(accounts, client, app):
    import pathlib
    _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu")
    assert 'class="center muted register-hint"' in client.get("/clubs").data.decode()
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    assert re.search(r"^\.register-hint \{[^}]*margin: 24px", css, re.M)


def test_every_dependency_has_a_version_pin():
    import pathlib
    for line in pathlib.Path("requirements.txt").read_text(encoding="utf-8").splitlines():
        package = line.split("#")[0].strip()
        if package:
            assert re.search(r"(~=|==|>=)\d", package), f"unpinned: {package}"


def test_relative_times_never_wrap_mid_phrase():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    assert re.search(r"^\.rel \{[^}]*white-space: nowrap", css, re.M)
    assert re.search(r"^\.now-tile small \{[^}]*white-space: nowrap", css, re.M)


def test_limited_badge_tag_stands_out():
    assert _css_classes_used_but_undefined(["tag-limited"]) == []


def test_need_players_create_option_is_highlighted():
    assert _css_classes_used_but_undefined(["create-gold"]) == []


def test_focus_ring_is_visible_on_the_purple_header_and_hero():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    assert ".topbar :focus-visible, .husky-hero :focus-visible { outline: 3px solid var(--gold)" in css


def test_form_fields_keep_a_focus_outline():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    assert "input:focus, select:focus, textarea:focus { outline: none" not in css
    assert "input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 2px solid" in css


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
    page = client.get("/")                        # not forced back to the "add a photo" step, and no banner
    assert page.status_code == 200 and b"photo-nudge" not in page.data


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


def test_signup_survives_the_email_service_failing(client, app, monkeypatch):
    """Brevo down or misconfigured: a clear message and an immediate retry, never a crash."""
    from sportive import auth

    def broken(*args, **kwargs):
        raise OSError("535 Authentication failed")
    monkeypatch.setattr(auth, "send_email", broken)
    app.config["CONTACT_EMAIL"] = "sportivecircle@gmail.com"
    response = client.post("/signup", data={
        "full_name": "Dubs Husky", "email": "dubs@uw.edu", "password": "purple-and-gold",
        "password2": "purple-and-gold", "birth_date": "2005-01-15"}, follow_redirects=True)
    page = response.data.decode()
    assert response.status_code == 200 and "couldn&#39;t send the email" in page and "sportivecircle@gmail.com" in page
    monkeypatch.setattr(auth, "send_email", lambda *a, **k: True)          # email works again
    page = client.post("/verify/resend", follow_redirects=True).data.decode()
    assert "We sent you a new code" in page                                # no 1-minute wait to retry


def test_forgot_password_survives_the_email_service_failing(accounts, client, monkeypatch):
    from sportive import auth
    accounts.signup()
    accounts.logout()
    monkeypatch.setattr(auth, "send_email", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert client.post("/forgot", data={"email": "dubs@uw.edu"}, follow_redirects=True).status_code == 200


def test_resend_doesnt_claim_success_when_email_fails(client, app, monkeypatch):
    from sportive import auth
    monkeypatch.setattr(auth, "send_email", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    client.post("/signup", data={"full_name": "Dubs Husky", "email": "dubs@uw.edu", "password": "purple-and-gold",
                                 "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    page = client.post("/verify/resend", follow_redirects=True).data.decode()
    assert "couldn&#39;t send the email" in page and "We sent you a new code" not in page


def test_email_failure_reasons_are_specific_and_safe():
    import smtplib
    from sportive.mail import failure_reason
    assert "rejected our login, error 535" in failure_reason(smtplib.SMTPAuthenticationError(535, b"5.7.8 bad key xsmtpsib-SECRET"))
    assert "SECRET" not in failure_reason(smtplib.SMTPAuthenticationError(535, b"xsmtpsib-SECRET"))
    assert "sender" in failure_reason(smtplib.SMTPSenderRefused(550, b"no", "a@b.c"))
    assert "can't receive" in failure_reason(smtplib.SMTPRecipientsRefused({"x@uw.edu": (550, b"no")}))
    assert "reach the email service" in failure_reason(TimeoutError())
    assert "error 452" in failure_reason(smtplib.SMTPDataError(452, b"quota"))


def test_email_settings_ignore_pasted_spaces_and_line_breaks(monkeypatch, tmp_path):
    monkeypatch.setenv("MAIL_USERNAME", "  9a1b2c001@smtp-brevo.com\n")
    monkeypatch.setenv("MAIL_PASSWORD", "xsmtpsib-key123 \r\n")
    monkeypatch.setenv("MAIL_SERVER", "smtp-relay.brevo.com ")
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "t.db")})
    assert app.config["MAIL_USERNAME"] == "9a1b2c001@smtp-brevo.com"
    assert app.config["MAIL_PASSWORD"] == "xsmtpsib-key123"
    assert app.config["MAIL_SERVER"] == "smtp-relay.brevo.com"


def test_check_email_command_explains_without_revealing_the_key(app, monkeypatch):
    import smtplib

    class RefusingSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def login(self, user, key):
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Authentication failed")

    monkeypatch.setattr(smtplib, "SMTP", RefusingSMTP)
    app.config.update(MAIL_SERVER="smtp-relay.brevo.com", MAIL_USERNAME="sportivecircle@gmail.com",
                      MAIL_PASSWORD="1bfd87-secret-part")
    output = app.test_cli_runner().invoke(args=["check-email"]).output
    assert "should end in @smtp-brevo.com" in output
    assert "doesn't start with xsmtpsib-" in output
    assert "LOGIN REFUSED: 535 5.7.8 Authentication failed" in output
    assert "secret" not in output                                  # the key itself is never printed


def test_admins_get_the_team_badge_and_label(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    accounts.signup(email="boss@uw.edu", name="Boss Husky")
    boss = _user_id(app, "boss@uw.edu")
    page = client.get(f"/u/{boss}").data.decode()
    assert "🐾 Team" in page and "Sportive Circle Team" in page         # label + badge in the showcase
    accounts.logout()
    accounts.signup(email="student@uw.edu")
    me = _user_id(app, "student@uw.edu")
    assert "🐾 Team" in client.get(f"/u/{boss}").data.decode()          # everyone sees who runs the app
    assert "🐾 Team" not in client.get(f"/u/{me}").data.decode()
    assert "Sportive Circle Team" not in client.get("/profile/badges").data.decode()   # can't be earned
    app.config["ADMIN_EMAILS"] = ""                                       # no longer an admin
    accounts.logout()
    accounts.login(email="boss@uw.edu")
    page = client.get(f"/u/{boss}").data.decode()
    assert "🐾 Team" not in page and "Sportive Circle Team" not in page


def test_suggestion_text_is_escaped_and_length_checked(accounts, client, app):
    accounts.signup()
    assert b"5 to 2000 characters" in client.post("/suggestions", data={"kind": "idea", "body": "hi"},
                                                  follow_redirects=True).data
    client.post("/suggestions", data={"kind": "bug", "body": "<script>alert(1)</script> broken"})
    app.config["ADMIN_EMAILS"] = "dubs@uw.edu"
    page = client.get("/admin/suggestions").data.decode()
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert "Something&#39;s broken" in client.get("/admin/suggestions?kind=bug").data.decode()


def test_admins_are_only_notified_about_topics_3_people_mention(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    accounts.signup(email="boss@uw.edu")
    accounts.logout()
    for i, text in enumerate(["Please add badminton!", "Badminton courts would be great", "Can we get badminton"]):
        accounts.signup(email=f"fan{i}@uw.edu")
        client.post("/suggestions", data={"kind": "idea", "body": text})
        if i == 0:
            for _ in range(3):   # one person saying something 3 times is still only 1 person
                client.post("/suggestions", data={"kind": "idea", "body": "more pickleball times"})
        accounts.logout()
        accounts.login(email="boss@uw.edu")
        page = client.get("/faq").data.decode()   # the number is on the admin (shield) icon
        shield = re.search(r'title="Admin">.*?</a>', page, re.S).group(0)
        assert ('<span class="count-dot">1</span>' in shield) == (i == 2), i   # quiet until the third person
        accounts.logout()
    accounts.login(email="boss@uw.edu")
    admin_page = client.get("/admin/suggestions").data.decode()
    assert "<strong>badminton</strong> · 3 people" in admin_page and "<strong>pickleball</strong>" not in admin_page
    shield = re.search(r'title="Admin">.*?</a>', client.get("/faq").data.decode(), re.S).group(0)
    assert "count-dot" not in shield                                                            # seen: no more
    topic_page = client.get("/admin/suggestions?topic=badminton").data.decode()
    assert "Can we get badminton" in topic_page and "more pickleball" not in topic_page
    assert "Suggestions</a>" in client.get("/terms").data.decode()      # footer link on every page


def test_keywords_ignore_filler_and_merge_similar_words():
    from sportive.feedback import keywords
    assert keywords("Please add badminton courts to the app!") == {"badminton", "court"}
    assert "notification" in keywords("the notifs are too much") and "notification" in keywords("fewer notis")
    assert keywords("The map is broken") == {"map", "bug"}


def test_code_email_is_designed_friendly_and_safe(client, app):
    client.post("/signup", data={"full_name": "Dubs Husky", "email": "dubs@uw.edu", "password": "purple-and-gold",
                                 "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    message = app.extensions["outbox"][-1]
    code = re.search(r"\d{6}", message["subject"]).group(0)
    assert message["subject"] == f"{code} is your Sportive Circle code"        # code first: phones can autofill it
    assert "Welcome to the pack, Dubs!" in message["body"] and code in message["body"]   # plain-text version
    html = message["html"]
    assert "Welcome to the pack, Dubs!" in html and code in html and "Sportive" in html
    assert "<img" not in html and "<script" not in html                       # nothing to block or distrust
    assert "not an official University of Washington service" in html


def test_emails_escape_what_people_type(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.logout()
    accounts.signup(email="sneaky@uw.edu", name="Sneaky <b>Husky</b>")
    client.post(f"/clubs/{club}/join", data={"message": '<a href="https://evil.example">click</a>'})
    html = [m for m in app.extensions["outbox"] if m["to"] == "captain@uw.edu"][-1]["html"]
    assert '<a href="https://evil.example">' not in html and "&lt;a href=" in html


def test_real_email_has_text_and_html_parts(app, monkeypatch):
    import smtplib
    sent, timeouts = [], []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            timeouts.append(kwargs.get("timeout"))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def login(self, *args):
            pass

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    app.config.update(TESTING=False, MAIL_SERVER="smtp.example.com", MAIL_USERNAME="u", MAIL_PASSWORD="p",
                      MAIL_FROM="Sportive Circle <sportivecircle@gmail.com>")
    with app.test_request_context():
        from sportive.mail import send_designed
        send_designed("dubs@uw.edu", "Hi", "Hello!", ["A line."], button=("Open", "https://x.test"))
    types = [part.get_content_type() for part in sent[0].walk()]
    assert "text/plain" in types and "text/html" in types
    assert timeouts and all(timeouts)  # a stuck mail server can't hang the page forever


def test_every_log_out_button_asks_first(accounts, client):
    accounts.signup()
    for path in ("/", "/profile/edit", "/how-it-works"):
        page = client.get(path).data.decode()
        forms = re.findall(r'<form[^>]*action="/logout"[^>]*>', page)
        assert forms and all('data-confirm="Log out of Sportive Circle?"' in form for form in forms), path


def test_check_email_can_send_a_test_to_every_admin(app, monkeypatch):
    import smtplib

    class OkSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def login(self, *args):
            pass

        def send_message(self, message):
            pass

    monkeypatch.setattr(smtplib, "SMTP", OkSMTP)
    app.config.update(MAIL_SERVER="smtp-relay.brevo.com", MAIL_USERNAME="x@smtp-brevo.com",
                      MAIL_PASSWORD="xsmtpsib-" + "a" * 81, ADMIN_EMAILS="akulog@uw.edu, teammate@uw.edu")
    output = app.test_cli_runner().invoke(args=["check-email", "--admins"]).output
    assert "LOGIN OK" in output
    assert "TEST EMAIL SENT to akulog@uw.edu" in output and "TEST EMAIL SENT to teammate@uw.edu" in output
    sent = {m["to"]: m for m in app.extensions["outbox"]}
    assert "You're an admin" in sent["teammate@uw.edu"]["body"]


# ------------------------------------------------ parties, private games, team vs team (tester feedback)

def _people(accounts, app, *names):
    """Sign up several people; returns {first name: user id}. Ends logged out."""
    ids = {}
    for name in names:
        email = f"{name.lower()}@uw.edu"
        accounts.signup(email=email, name=f"{name} Husky")
        ids[name] = _user_id(app, email)
        accounts.logout()
    return ids


def _friends(app, a, *others):
    with app.app_context():
        db = get_db()
        for other in others:
            db.execute("INSERT OR REPLACE INTO friendships (requester_id, addressee_id, status, created_at)"
                       " VALUES (?, ?, 'accepted', '2026-09-01 10:00')", (a, other))
        db.commit()


def _as(accounts, name):
    accounts.logout()
    accounts.login(email=f"{name.lower()}@uw.edu")


def test_party_up_holds_spots_for_friends(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan", "Sam", "Stranger")
    _friends(app, ids["Maya"], ids["Jordan"], ids["Sam"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(sport="tennis", location="IMA South Tennis Courts",
                                                                     players="3", title="Doubles-ish")))
    party_page = client.get(f"/events/{game}/party").data.decode()
    assert "Jordan Husky" in party_page and "Sam Husky" in party_page and "2 spots for friends" in party_page
    done = client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"], ids["Sam"]]}, follow_redirects=True)
    assert b"held for 30 minutes" in done.data
    # A stranger can't take the held spots: the game looks full to them.
    _as(accounts, "Stranger")
    assert b"Sorry, this game is full" in client.post(f"/events/{game}/join", follow_redirects=True).data
    # Jordan gets a notice and a "You down?" box, and takes his held spot.
    _as(accounts, "Jordan")
    assert "Maya wants you in Doubles-ish" in client.get("/notifications").data.decode()
    page = client.get(f"/events/{game}").data.decode()
    assert "Maya invited you. You down?" in page and "held for" in page
    assert b"You&#39;re in" in client.post(f"/events/{game}/invite/answer", data={"answer": "yes"},
                                            follow_redirects=True).data
    # Sam says no: his spot opens up, and Maya hears about both answers.
    _as(accounts, "Sam")
    client.post(f"/events/{game}/invite/answer", data={"answer": "no"})
    _as(accounts, "Stranger")
    assert b"You&#39;re in" in client.post(f"/events/{game}/join", follow_redirects=True).data
    _as(accounts, "Maya")
    bell = client.get("/notifications").data.decode()
    assert "Jordan is in for Doubles-ish" in bell and "Sam can&#39;t make Doubles-ish" in bell


def test_held_spots_open_up_after_30_minutes(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan", "Stranger")
    _friends(app, ids["Maya"], ids["Jordan"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(sport="tennis", location="IMA South Tennis Courts",
                                                                     players="2")))
    client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"]]})
    with app.app_context():
        db = get_db()
        db.execute("UPDATE invites SET expires_at = '2020-01-01 00:00'")   # time's up
        db.commit()
    _as(accounts, "Stranger")
    assert b"You&#39;re in" in client.post(f"/events/{game}/join", follow_redirects=True).data
    _as(accounts, "Jordan")                                   # the invite still works, but the spot is gone
    assert "Join if there's still room" in client.get(f"/events/{game}").data.decode()
    assert b"this game is full" in client.post(f"/events/{game}/invite/answer", data={"answer": "yes"},
                                                follow_redirects=True).data


def test_join_with_friends_is_all_or_nothing(accounts, client, app):
    ids = _people(accounts, app, "Host", "Maya", "Jordan", "Sam")
    _friends(app, ids["Maya"], ids["Jordan"], ids["Sam"])
    _as(accounts, "Host")
    game = event_id_from(client.post("/events/new", data=event_form(sport="tennis", location="IMA South Tennis Courts",
                                                                     players="3")))
    _as(accounts, "Maya")   # a non-host who isn't in yet: joins and brings friends in one go
    assert b"Join + reserve spots for friends" in client.get(f"/events/{game}").data
    too_many = client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"], ids["Sam"]]}, follow_redirects=True)
    assert b"Only 1 spot left for friends" in too_many.data
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (game,)).fetchone()[0] == 1
        assert get_db().execute("SELECT COUNT(*) FROM invites").fetchone()[0] == 0   # nothing half-done
    client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"]]})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (game,)).fetchone()[0] == 2
    assert b"You&#39;re already going" not in client.get(f"/events/{game}").data


def test_only_friends_can_be_invited(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan")
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form()))
    assert b"only invite your friends" in client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"]]},
                                                       follow_redirects=True).data
    _friends(app, ids["Maya"], ids["Jordan"])
    client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"]]})
    assert b"only invite your friends" in client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"]]},
                                                       follow_redirects=True).data   # already invited
    client.post(f"/events/{game}/invite/{ids['Jordan']}/cancel")
    with app.app_context():
        assert get_db().execute("SELECT status FROM invites").fetchone()[0] == "canceled"


def test_private_game_needs_the_password_unless_invited(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan", "Sam")
    _friends(app, ids["Maya"], ids["Jordan"])
    _as(accounts, "Maya")
    assert b"Pick a password" in client.post("/events/new", data=event_form(is_private="1", password="ab"),
                                              follow_redirects=True).data
    game = event_id_from(client.post("/events/new", data=event_form(is_private="1", password="dawgs26")))
    assert "dawgs26" in client.get(f"/events/{game}").data.decode()          # the host sees it to share it
    _as(accounts, "Sam")
    page = client.get(f"/events/{game}").data.decode()
    assert "🔒 Private" in page and "dawgs26" not in page and 'name="password"' in page
    feed = client.get("/?scope=all").data.decode()
    assert "🔒 Private" in feed and f"/events/{game}/join" not in feed       # no one-tap Join on the card
    assert b"Enter the password" in client.post(f"/events/{game}/join", follow_redirects=True).data
    assert b"not the password" in client.post(f"/events/{game}/join", data={"password": "nope"},
                                               follow_redirects=True).data
    assert b"You&#39;re in" in client.post(f"/events/{game}/join", data={"password": "dawgs26"},
                                            follow_redirects=True).data
    assert "dawgs26" in client.get(f"/events/{game}").data.decode()          # players see it too
    _as(accounts, "Maya")
    client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"]]})
    _as(accounts, "Jordan")                                                  # invited: no password needed
    assert b"You&#39;re in" in client.post(f"/events/{game}/invite/answer", data={"answer": "yes"},
                                            follow_redirects=True).data


def test_private_game_passwords_cant_be_guessed(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Sam")
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(is_private="1", password="dawgs26")))
    _as(accounts, "Sam")
    for n in range(10):
        client.post(f"/events/{game}/join", data={"password": f"guess{n}"})
    blocked = client.post(f"/events/{game}/join", data={"password": "dawgs26"}, follow_redirects=True)
    assert b"Too many wrong passwords" in blocked.data                        # even the right one, for an hour
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rsvps WHERE user_id = ?", (ids["Sam"],)).fetchone()[0] == 0


def test_team_vs_team(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Mo", "Jordan", "Jay", "Sam", "Solo")
    _friends(app, ids["Maya"], ids["Mo"])
    _friends(app, ids["Jordan"], ids["Jay"], ids["Sam"])
    _as(accounts, "Maya")
    assert b"Basketball teams can be 2v2, 3v3, 4v4, 5v5." in client.post(
        "/events/new", data=event_form(team_size="9"), follow_redirects=True).data   # no 9v9 basketball
    game = event_id_from(client.post("/events/new", data=event_form(team_size="2", title="2v2 run")))
    client.post(f"/events/{game}/party", data={"friend": [ids["Mo"]]})       # Maya brings Mo to team 1
    _as(accounts, "Mo")
    client.post(f"/events/{game}/invite/answer", data={"answer": "yes"})
    # Someone alone can't just walk into a team game.
    _as(accounts, "Solo")
    assert b"invite-only" in client.post(f"/events/{game}/join", follow_redirects=True).data
    # Jordan challenges with one friend (team size 2); too many friends doesn't fit.
    _as(accounts, "Jordan")
    page = client.get(f"/events/{game}").data.decode()
    assert "Challenge with your team" in page and "Maya&#39;s team" in page and "Challengers" in page
    assert b"Only 1 spot left" in client.post(f"/events/{game}/party", data={"friend": [ids["Jay"], ids["Sam"]]},
                                              follow_redirects=True).data
    client.post(f"/events/{game}/party", data={"friend": [ids["Jay"]]})
    _as(accounts, "Solo")                                                    # team 2 is claimed now
    assert "Teams are set" in client.get(f"/events/{game}").data.decode()
    _as(accounts, "Jay")
    client.post(f"/events/{game}/invite/answer", data={"answer": "yes"})
    with app.app_context():
        teams = dict(get_db().execute("SELECT user_id, team FROM rsvps WHERE event_id = ?", (game,)).fetchall())
    assert teams == {ids["Maya"]: 1, ids["Mo"]: 1, ids["Jordan"]: 2, ids["Jay"]: 2}


def test_team_sizes_fit_the_sport(accounts, client, app):
    """Testers: "If I pick basketball, why would I play 9v9?" And "Anyone can join" next to Private made no sense."""
    from sportive.constants import MAX_PLAYERS, SPORT_TEAM_SIZES
    for sport, sizes in SPORT_TEAM_SIZES.items():
        assert sizes and max(sizes) * 2 <= MAX_PLAYERS, sport
    accounts.signup()
    page = client.get("/events/new?sport=basketball").data.decode()
    assert "Anyone can join" not in page and ">Regular game<" in page
    assert ">5v5 team vs team<" in page and ">9v9 team vs team<" not in page
    assert "data-team-field hidden" in client.get("/events/new?sport=running").data.decode()
    run = event_form(sport="running", location="Burke-Gilman Trail", team_size="2")
    assert b"Running isn&#39;t played team vs team" in client.post("/events/new", data=run, follow_redirects=True).data
    spike = event_form(sport="spikeball", location="The Quad", team_size="2")
    assert client.post("/events/new", data=spike).status_code == 302


def test_open_spots_filter(accounts, client, app):
    _people(accounts, app, "Maya", "Me")
    _as(accounts, "Maya")
    client.post("/events/new", data=event_form(title="Big run", players="10"))
    client.post("/events/new", data=event_form(title="Small run", players="3"))
    _as(accounts, "Me")
    five = client.get("/?scope=all&open=5").data.decode()
    assert "Big run" in five and "Small run" not in five
    assert "Small run" in client.get("/?scope=all&open=2").data.decode()
    assert "Small run" in client.get("/?scope=all&open=junk").data.decode()   # nonsense = no filter
    assert "Small run" in client.get("/?scope=all&open=1").data.decode()      # "need just one more" works


def test_need_players_host_hears_when_someone_joins(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/need-players", data={
        "sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "players": "4"}))
    accounts.logout()
    accounts.signup(email="player@uw.edu", name="Pat Player")
    client.post(f"/events/{event_id}/join")
    with app.app_context():
        texts = [r[0] for r in get_db().execute("SELECT text FROM notices WHERE user_id = ?",
                                                 (_user_id(app, "host@uw.edu"),))]
    assert len(texts) == 1 and texts[0].startswith("Pat joined") and "(2 going now)" in texts[0]


def test_signup_step_counter_counts_the_photo_step(accounts, client):
    accounts.signup(photo=False)
    assert "Step 4 of 4" in client.get("/profile/photo").data.decode()   # "Step 3 of 3" when texts are off
    client.post("/profile/photo/skip")
    assert "Step 1 of 2" in client.get("/profile/edit").data.decode()


def test_times_skipped_by_daylight_saving_are_refused(accounts, client, monkeypatch):
    from datetime import datetime
    from sportive import events
    from sportive.timeutil import exists_in_seattle
    assert not exists_in_seattle(datetime(2027, 3, 14, 2, 30))
    assert exists_in_seattle(datetime(2027, 3, 14, 3, 30)) and exists_in_seattle(datetime(2027, 11, 7, 1, 30))
    monkeypatch.setattr(events, "now_local", lambda: datetime(2027, 3, 1, 12, 0))
    accounts.signup()
    page = client.post("/events/new", data=event_form(starts_at="2027-03-14T02:30", ends_at="2027-03-14T04:00")).data
    assert b"2:30 AM doesn&#39;t exist on Mar 14" in page


def test_one_account_per_uw_inbox(accounts, client):
    accounts.signup(email="dubs@uw.edu")
    accounts.logout()
    plus = accounts.signup(email="dubs+2@uw.edu", verify=False).data.decode()
    assert "without a +tag" in plus
    alias = accounts.signup(email="dubs@u.washington.edu", verify=False).data.decode()
    assert "You already have an account as dubs@uw.edu" in alias


def test_names_cant_be_invisible_or_flipped(accounts, client, app):
    blank = accounts.signup(email="ghost@uw.edu", name="\u200b\u200b", verify=False).data.decode()
    assert "Full name cannot be empty." in blank
    dots = accounts.signup(email="dots@uw.edu", name="...", verify=False).data.decode()
    assert "Please use your real name" in dots
    accounts.signup(email="maya@uw.edu", name="Ma\u202eya Chen")
    with app.app_context():
        assert get_db().execute("SELECT full_name FROM users WHERE email = 'maya@uw.edu'").fetchone()[0] == "Maya Chen"


def test_blocked_people_are_listed_in_settings_and_can_be_unblocked(accounts, client, app):
    accounts.signup(email="pest@uw.edu", name="Pesky Pete")
    pest = _user_id(app, "pest@uw.edu")
    accounts.logout()
    accounts.signup()
    assert "You haven't blocked anyone." in client.get("/settings/blocked").data.decode()
    assert "/settings/blocked" in client.get("/settings").data.decode()
    client.post(f"/block/{pest}")
    assert "Pesky Pete" in client.get("/settings/blocked").data.decode()
    response = client.post(f"/unblock/{pest}", data={"from": "blocked"})
    assert response.headers["Location"].endswith("/settings/blocked")
    assert "You haven't blocked anyone." in client.get("/settings/blocked").data.decode()


def test_leaving_a_game_asks_first(accounts, client):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form(players="2")))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    client.post(f"/events/{event_id}/join")
    page = client.get(f"/events/{event_id}").data.decode()
    assert 'data-confirm="Leave this game? It\'s full, so someone else may take your spot."' in page


def test_someone_the_host_removed_cant_just_rejoin(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    client.post(f"/events/{event_id}/join")
    player = _user_id(app, "player@uw.edu")
    accounts.logout()
    accounts.login(email="host@uw.edu")
    client.post(f"/events/{event_id}/players/{player}/remove")
    accounts.logout()
    accounts.login(email="player@uw.edu")
    page = client.post(f"/events/{event_id}/join", follow_redirects=True).data.decode()
    assert "can&#39;t rejoin it" in page
    assert client.post(f"/events/{event_id}/party", data={}, follow_redirects=True).status_code == 200
    with app.app_context():
        assert get_db().execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (event_id, player)).fetchone() is None


def test_cancel_notice_links_to_the_game(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    client.post(f"/events/{event_id}/join")
    accounts.logout()
    accounts.login(email="host@uw.edu")
    client.post(f"/events/{event_id}/cancel")
    with app.app_context():
        url = get_db().execute("SELECT url FROM notices WHERE user_id = ?", (_user_id(app, "player@uw.edu"),)).fetchone()[0]
    assert url == f"/events/{event_id}"
    accounts.logout()
    accounts.login(email="player@uw.edu")
    assert client.get(url).status_code == 200


def test_need_players_cant_be_double_posted_or_spammed(accounts, client, app):
    accounts.signup()
    post = lambda sport, place: client.post("/need-players", data={
        "sport": sport, "location": place, "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "players": "4"})
    first = event_id_from(post("soccer", "Denny Field"))
    again = post("soccer", "Denny Field")
    assert again.headers["Location"].endswith(f"/events/{first}")
    for sport, place in (("basketball", "IMA (Intramural Activities Building)"), ("spikeball", "The Quad"),
                         ("ultimate", "Denny Field")):
        post(sport, place)
    page = post("volleyball", "IMA (Intramural Activities Building)").data.decode()
    assert "a lot of Need players posts" in page
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM events WHERE is_quick = 1").fetchone()[0] == 4


def test_nonsense_filter_values_dont_count_as_filters(accounts, client):
    accounts.signup()
    page = client.get("/?scope=all&sport=zzz&location=Mars&skill=Pro&when=never&open=99").data.decode()
    assert "Filters ·" not in page and "Clear filters" not in page and "No games yet" in page


def test_open_spots_filter_skips_games_a_group_cant_just_join(accounts, client, app):
    _people(accounts, app, "Maya", "Me")
    _as(accounts, "Maya")
    client.post("/events/new", data=event_form(title="Secret run", players="12", is_private="1", password="hoops"))
    client.post("/events/new", data=event_form(title="Team clash", players="10", team_size="5"))
    client.post("/events/new", data=event_form(title="Open run", players="12"))
    _as(accounts, "Me")
    five = client.get("/?scope=all&open=5").data.decode()
    assert "Open run" in five and "Secret run" not in five and "Team clash" not in five
    everything = client.get("/?scope=all").data.decode()
    assert "Secret run" in everything and "Team clash" in everything


def test_full_games_have_their_own_tab(accounts, client, app):
    """Nobody can join a full game, so the feed hides it; the Full tab still shows them."""
    _people(accounts, app, "Maya", "Me", "Sam")
    _as(accounts, "Maya")
    full_id = event_id_from(client.post("/events/new", data=event_form(title="Packed run", players="2")))
    client.post("/events/new", data=event_form(title="Roomy run", players="10"))
    _as(accounts, "Sam")
    client.post(f"/events/{full_id}/join")                        # Maya + Sam = 2 of 2: full
    feed = client.get("/?scope=all").data.decode()
    assert "Packed run" in feed and ">Full</span>" in feed           # Sam is in it: his own games always show
    assert "Packed run" not in client.get("/?scope=full").data.decode()
    _as(accounts, "Me")
    feed = client.get("/?scope=all").data.decode()
    assert "Roomy run" in feed and "Packed run" not in feed          # full: hidden from everyone else
    full = client.get("/?scope=full").data.decode()
    assert "Packed run" in full and "Roomy run" not in full and "Full games" in full


def test_blocked_people_cant_party_into_your_game(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan")
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form()))
    client.post(f"/block/{ids['Jordan']}")
    _as(accounts, "Jordan")
    assert b"can&#39;t join" in client.get(f"/events/{game}/party", follow_redirects=True).data
    assert b"Join + reserve spots for friends" not in client.get(f"/events/{game}").data


def test_private_game_host_approves_friends_players_bring(accounts, client, app):
    """Testers: "If you want to bring your friend, you make the request to the host, with a note.
    Otherwise, who's John?" Only in private games; the host says yes first."""
    ids = _people(accounts, app, "Maya", "Sam", "John", "Kim")
    _friends(app, ids["Sam"], ids["John"], ids["Kim"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(is_private="1", password="dawgs26",
                                                                     title="Hoops")))
    _as(accounts, "Sam")
    client.post(f"/events/{game}/join", data={"password": "dawgs26"})
    party = client.get(f"/events/{game}/party").data.decode()
    assert 'name="note"' in party and "Ask Maya" in party
    done = client.post(f"/events/{game}/party", data={"friend": [ids["John"], ids["Kim"]], "note": "My roommates"},
                       follow_redirects=True).data.decode()
    assert "Asked Maya" in done and "Waiting for Maya" in done
    _as(accounts, "John")                                   # nothing to answer until Maya says yes
    assert "You down?" not in client.get(f"/events/{game}").data.decode()
    _as(accounts, "Maya")
    assert "Sam wants to bring John, Kim to Hoops: “My roommates”" in client.get("/notifications").data.decode()
    page = client.get(f"/events/{game}").data.decode()
    assert "Requests" in page and "My roommates" in page
    client.post(f"/events/{game}/requests/{ids['John']}/approve")
    client.post(f"/events/{game}/requests/{ids['Kim']}/decline")
    _as(accounts, "John")                                   # approved: invite, held spot, no password needed
    assert "Sam invited you. You down?" in client.get(f"/events/{game}").data.decode()
    assert b"You&#39;re in" in client.post(f"/events/{game}/invite/answer", data={"answer": "yes"},
                                            follow_redirects=True).data
    _as(accounts, "Kim")
    assert "You down?" not in client.get(f"/events/{game}").data.decode()
    _as(accounts, "Sam")
    bell = client.get("/notifications").data.decode()
    # About John: "Maya said yes" was replaced by the newer "John is in" (one line per person, no repeats).
    assert "John is in for Hoops" in bell and "Maya said yes to John" not in bell
    assert "Maya can&#39;t fit Kim into Hoops" in bell
    _as(accounts, "Kim")                                    # only the host answers requests
    assert client.post(f"/events/{game}/requests/{ids['Kim']}/approve").status_code == 403


def test_team_invites_go_to_the_right_team_and_private_games_arent_team_games(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Mo", "Max", "Solo")
    _friends(app, ids["Maya"], ids["Mo"])
    _friends(app, ids["Mo"], ids["Max"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(team_size="3", title="3v3")))
    client.post(f"/events/{game}/party", data={"friend": [ids["Mo"]]})
    _as(accounts, "Mo")          # invited to Maya's team: joining with a friend puts both on team 1, not team 2
    client.post(f"/events/{game}/party", data={"friend": [ids["Max"]]})
    _as(accounts, "Max")
    client.post(f"/events/{game}/invite/answer", data={"answer": "yes"})
    with app.app_context():
        teams = dict(get_db().execute("SELECT user_id, team FROM rsvps WHERE event_id = ?", (game,)).fetchall())
    assert teams == {ids["Maya"]: 1, ids["Mo"]: 1, ids["Max"]: 1}
    _as(accounts, "Maya")   # private + team vs team made no sense (nobody could be the other team)
    private_team = client.post("/events/new", data=event_form(team_size="2", is_private="1", password="secret1",
                                                               title="Private 2v2"), follow_redirects=True).data
    assert b"Team vs team is for games anyone can join" in private_team


def test_host_reserves_spots_while_creating_a_game(accounts, client, app):
    """"Where is the reserve spot part?" Both create forms let the host reserve spots for friends."""
    ids = _people(accounts, app, "Maya", "Jordan", "Sam", "Stranger")
    _friends(app, ids["Maya"], ids["Jordan"], ids["Sam"])
    _as(accounts, "Maya")
    for page in ("/events/new", "/need-players"):
        html = client.get(page).data.decode()
        assert "Who&#39;s coming?" in html or "Who's coming?" in html
        assert "held for 30 min" in html and "Jordan Husky" in html and 'name="is_private"' in html
        assert 'name="team_size"' in html
    # New event: tennis for 3, two friends reserved = full for strangers.
    game = event_id_from(client.post("/events/new", data=event_form(
        sport="tennis", location="IMA South Tennis Courts", players="3", title="Doubles",
        reserve=[ids["Jordan"], ids["Sam"]])))
    _as(accounts, "Stranger")
    assert b"this game is full" in client.post(f"/events/{game}/join", follow_redirects=True).data
    _as(accounts, "Jordan")
    assert "Maya wants you in Doubles" in client.get("/notifications").data.decode()
    assert b"You&#39;re in" in client.post(f"/events/{game}/invite/answer", data={"answer": "yes"},
                                            follow_redirects=True).data
    # Need players: "need 2", one reserved for Sam, so the post says Need 1 more.
    _as(accounts, "Maya")
    quick = client.post("/need-players", data={"sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
                                               "starts_in": "15", "duration": "60", "players": "3",
                                               "reserve": [ids["Sam"]]})
    quick_id = event_id_from(quick)
    assert "Need 1 more for Soccer" in client.get(f"/events/{quick_id}").data.decode()
    # Can't reserve more than there's room for, or for people who aren't friends.
    too_many = client.post("/need-players", data={"sport": "soccer", "location": "Denny Field",
                                                  "skill_level": "All levels", "starts_in": "15", "duration": "60",
                                                  "players": "2", "reserve": [ids["Jordan"], ids["Sam"]]},
                           follow_redirects=True)
    assert b"only room to reserve 1 spot" in too_many.data
    stranger = client.post("/events/new", data=event_form(title="Other", reserve=[ids["Stranger"]]),
                           follow_redirects=True)
    assert b"only reserve spots for your friends" in stranger.data


def test_need_players_can_be_private_or_team_vs_team(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Mo", "Sam")
    _friends(app, ids["Maya"], ids["Mo"])
    _as(accounts, "Maya")
    base = {"sport": "basketball", "location": "IMA (Intramural Activities Building)", "skill_level": "All levels",
            "starts_in": "15", "duration": "60", "players": "3"}
    private = event_id_from(client.post("/need-players", data={**base, "is_private": "1", "password": "hoops4"}))
    team = event_id_from(client.post("/need-players", data={**base, "team_size": "3", "reserve": [ids["Mo"]]}))
    _as(accounts, "Sam")
    assert b"Enter the password" in client.post(f"/events/{private}/join", follow_redirects=True).data
    page = client.get(f"/events/{team}").data.decode()
    assert "Basketball 3v3: challenge us" in page and "Challenge with your team" in page
    with app.app_context():
        row = get_db().execute("SELECT max_players, extra_players, team_size FROM events WHERE id = ?", (team,)).fetchone()
        assert tuple(row) == (6, 0, 3)
        assert get_db().execute("SELECT team FROM invites WHERE guest_id = ?", (ids["Mo"],)).fetchone()[0] == 1
    _as(accounts, "Maya")
    bad = client.post("/need-players", data={**base, "team_size": "9"}, follow_redirects=True).data
    assert b"Basketball teams can be 2v2, 3v3, 4v4, 5v5." in bad


def test_players_and_hosts_both_see_reserve_spots(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan", "Sam")
    _friends(app, ids["Jordan"], ids["Sam"])
    _friends(app, ids["Maya"], ids["Sam"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form()))
    assert ">Reserve spots</a>" in client.get(f"/events/{game}").data.decode()        # the host
    _as(accounts, "Jordan")
    assert "Join + reserve spots for friends" in client.get(f"/events/{game}").data.decode()  # not in yet
    client.post(f"/events/{game}/join")
    assert ">Reserve spots</a>" in client.get(f"/events/{game}").data.decode()        # a player


def test_create_page_only_shows_what_makes_sense(accounts, client, app):
    """Feedback: "why do I need Reserve spots or 'We have' for a private game?" Private hides them."""
    ids = _people(accounts, app, "Maya", "Jordan", "Sam")
    _friends(app, ids["Maya"], ids["Jordan"])
    _as(accounts, "Maya")
    for page in ("/events/new", "/need-players"):
        html = client.get(page).data.decode()
        assert "Who can join?" in html and ">Anyone<" in html and "🔒 Private" in html
        assert re.search(r'name="password"[^>]*disabled|value="dawgs\d{4}"', html)   # ready-made, off until Private
        assert 'data-show="private"' in html and "get an invite, no password needed" in html
        assert 'name="players"' in html and "We have" not in html and "Max players" not in html
    # A private Need players post: no "we have / we need" or skill level sent, and that's fine.
    game = event_id_from(client.post("/need-players", data={
        "sport": "soccer", "location": "Denny Field", "starts_in": "15", "duration": "60",
        "is_private": "1", "password": "dawgs1234", "reserve": [ids["Jordan"]]}))
    with app.app_context():
        row = get_db().execute("SELECT max_players, extra_players, skill_level FROM events WHERE id = ?", (game,)).fetchone()
        assert tuple(row) == (14, 0, "All levels")                               # soccer's usual size
    page = client.get(f"/events/{game}").data.decode()
    assert "Private soccer game" in page and "Send invite link" in page and "dawgs1234" in page  # host sees the password
    # Not a call to everyone: strangers don't get it up top or as a Need players notification.
    _as(accounts, "Sam")
    feed = client.get("/?scope=all").data.decode()
    happening_soon = feed.split('id="now"')[1].split("</nav>")[0] if 'id="now"' in feed else ""
    assert f"/events/{game}" not in happening_soon
    assert f"/events/{game}" in feed and "🔒 Private" in feed                           # listed, with a lock
    assert "Need players" not in client.get("/notifications").data.decode()
    assert "Send invite link" not in client.get(f"/events/{game}").data.decode()          # not a player
    # Jordan was invited: joins with one tap, no password.
    _as(accounts, "Jordan")
    assert b"You&#39;re in" in client.post(f"/events/{game}/invite/answer", data={"answer": "yes"},
                                            follow_redirects=True).data


def test_new_private_event_needs_no_skill_level(accounts, client):
    accounts.signup()
    data = event_form(is_private="1", password="dawgs1234")
    del data["skill_level"]                     # hidden (and switched off) for private games
    response = client.post("/events/new", data=data, follow_redirects=True).data.decode()
    assert "Your private game is up!" in response and "Send invite link" in response


def test_picking_friends_counts_them_once_not_as_extra_spots(accounts, client, app):
    """Feedback: with "We have 2 / We need 8" plus reserving your friend, the friend got an EXTRA spot.
    Now: Players = 10 (5v5), tick your friend, and it's "need 8 more" with the friend inside the 10."""
    ids = _people(accounts, app, "Maya", "Jordan", "Stranger")
    _friends(app, ids["Maya"], ids["Jordan"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/need-players", data={
        "sport": "basketball", "location": "IMA (Intramural Activities Building)", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "players": "10", "reserve": [ids["Jordan"]]}))
    with app.app_context():
        row = get_db().execute("SELECT max_players, extra_players FROM events WHERE id = ?", (game,)).fetchone()
        assert tuple(row) == (10, 0)                             # still 10 players, nothing added on top
    page = client.get(f"/events/{game}").data.decode()
    assert "Need 8 more for Basketball" in page and "8 spots left" in page
    # Players 3 = you + your app friend + 1 more.
    small = event_id_from(client.post("/need-players", data={
        "sport": "tennis", "location": "IMA South Tennis Courts", "skill_level": "All levels",
        "starts_in": "30", "duration": "60", "players": "3", "reserve": [ids["Jordan"]]}))
    assert "Need 1 more for Tennis" in client.get(f"/events/{small}").data.decode()
    # Everyone already coming: nothing to post.
    full = client.post("/need-players", data={
        "sport": "tennis", "location": "IMA South Tennis Courts", "skill_level": "All levels",
        "starts_in": "30", "duration": "60", "players": "2", "reserve": [ids["Jordan"]]}, follow_redirects=True)
    assert b"Everyone&#39;s already coming" in full.data


def test_players_start_at_the_sports_usual_size(accounts, client):
    accounts.signup()
    page = client.get("/events/new?sport=basketball").data.decode()
    assert re.search(r'name="players" type="number"[^>]*value="10"', page)   # 5v5 suggested, any number allowed
    assert '"default": 10' in page                             # forms.js suggests each sport's usual size


def _set_gender(app, user_id, gender):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET gender = ? WHERE id = ?", (gender, user_id))
        db.commit()


def test_games_can_be_open_to_a_group_like_uw_rec_hours(accounts, client, app):
    """Feedback: gym buddies might not want to match across genders, without being offensive about it."""
    ids = _people(accounts, app, "Maya", "Mo", "Kai", "Blank")
    _set_gender(app, ids["Maya"], "woman")
    _set_gender(app, ids["Mo"], "man")
    _set_gender(app, ids["Kai"], "nonbinary")
    _as(accounts, "Maya")
    gym = dict(sport="gym", location="IMA (Intramural Activities Building)", title="Leg day buddy", players="2")
    women = event_id_from(client.post("/events/new", data=event_form(open_to="women", **gym)))
    nonbinary = event_id_from(client.post("/events/new", data=event_form(open_to="nonbinary", **{**gym, "title": "Lift"})))
    assert "Women only" in client.get(f"/events/{women}").data.decode()
    assert "Nonbinary only" in client.get(f"/events/{nonbinary}").data.decode()
    form = client.get("/events/new").data.decode()
    assert ">Nonbinary</option>" in form and "Women &amp; nonbinary" not in form   # the old choice isn't offered
    # Mo said "man" on his profile: these aren't in his feed, and he can't join.
    _as(accounts, "Mo")
    feed = client.get("/?scope=all").data.decode()
    assert "Leg day buddy" not in feed and "Lift" not in feed
    assert b"This game is for women." in client.post(f"/events/{women}/join", follow_redirects=True).data
    # Kai (nonbinary): not the women-only one, yes the nonbinary one.
    _as(accounts, "Kai")
    assert b"This game is for women." in client.post(f"/events/{women}/join", follow_redirects=True).data
    assert b"You&#39;re in" in client.post(f"/events/{nonbinary}/join", follow_redirects=True).data
    # ...and the nonbinary one isn't for Mo.
    _as(accounts, "Mo")
    assert b"This game is for nonbinary players." in client.post(f"/events/{nonbinary}/join",
                                                                  follow_redirects=True).data
    # A game made earlier as "Women & nonbinary" keeps working the way it was made.
    with app.app_context():
        get_db().execute("UPDATE events SET open_to = 'women_nb' WHERE id = ?", (nonbinary,))
        get_db().commit()
    assert "Women &amp; nonbinary" in client.get(f"/events/{nonbinary}").data.decode()
    assert b"This game is for women &amp; nonbinary players." in client.post(f"/events/{nonbinary}/join",
                                                                            follow_redirects=True).data
    # Left gender blank (it's optional): nothing is assumed; the Join button just asks to confirm.
    _as(accounts, "Blank")
    page = client.get(f"/events/{women}").data.decode()
    assert 'data-confirm="This game is for women. Join?"' in page
    assert b"You&#39;re in" in client.post(f"/events/{women}/join", follow_redirects=True).data
    # The host can take someone off their game; they get a notice.
    _as(accounts, "Maya")
    client.post(f"/events/{women}/players/{ids['Blank']}/remove")
    _as(accounts, "Blank")
    assert "Maya took you off Leg day buddy" in client.get("/notifications").data.decode()
    assert client.post(f"/events/{women}/players/{ids['Maya']}/remove").status_code == 403   # only the host


def test_canceling_a_game_tells_invited_friends_and_closes_invites(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan")
    _friends(app, ids["Maya"], ids["Jordan"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Doubles")))
    client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"]]})
    client.post(f"/events/{game}/cancel")
    _as(accounts, "Jordan")
    assert "Maya canceled Doubles" in client.get("/notifications").data.decode()
    with app.app_context():
        assert get_db().execute("SELECT status FROM invites").fetchone()[0] == "canceled"


def test_party_up_cant_get_around_who_a_game_is_for(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Mo", "Pal")
    _set_gender(app, ids["Maya"], "woman")
    _set_gender(app, ids["Mo"], "man")
    _friends(app, ids["Mo"], ids["Pal"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(
        open_to="women", sport="gym", location="IMA (Intramural Activities Building)", players="4")))
    _as(accounts, "Mo")
    assert b"This game is for women." in client.get(f"/events/{game}/party", follow_redirects=True).data
    client.post(f"/events/{game}/party", data={"friend": [ids["Pal"]]})
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (game, ids["Mo"])).fetchone() is None
        assert db.execute("SELECT COUNT(*) FROM invites WHERE event_id = ?", (game,)).fetchone()[0] == 0


def test_private_game_insides_are_only_for_players(accounts, client, app):
    ids = _people(accounts, app, "Hana", "Stella", "Pat")
    _as(accounts, "Hana")
    game = event_id_from(client.post("/events/new", data=event_form(
        is_private="1", password="dawgs26", title="Secret hoops", note="Court 3, back entrance")))
    _as(accounts, "Pat")
    client.post(f"/events/{game}/join", data={"password": "dawgs26"})
    _as(accounts, "Stella")
    page = client.get(f"/events/{game}").data.decode()
    assert "Court 3" not in page and "Pat Husky" not in page and "Only players and invited friends" in page
    assert client.get(f"/events/{game}/calendar.ics").status_code == 404
    assert "Secret hoops" not in client.get(f"/u/{ids['Hana']}").data.decode()
    _as(accounts, "Pat")
    page = client.get(f"/events/{game}").data.decode()
    assert "Court 3" in page and "Pat Husky" in page
    assert client.get(f"/events/{game}/calendar.ics").status_code == 200


def test_private_games_are_open_to_whoever_the_host_invites(accounts, client, app):
    accounts.signup()
    game = event_id_from(client.post("/events/new", data=event_form(is_private="1", password="dawgs1234",
                                                                     open_to="men")))
    with app.app_context():
        assert get_db().execute("SELECT open_to FROM events WHERE id = ?", (game,)).fetchone()[0] == "everyone"
    assert b"pick who the game is open to" in client.post("/events/new", data=event_form(
        title="Weird", open_to="aliens"), follow_redirects=True).data


def test_a_game_without_a_name_gets_one(accounts, client, app):
    accounts.signup()
    game = event_id_from(client.post("/events/new", data=event_form(title="")))
    assert "Basketball at the IMA" in client.get(f"/events/{game}").data.decode()
    with app.app_context():
        from sportive.events import default_title
        assert default_title("soccer", "Denny Field") == "Soccer at Denny Field"
        assert default_title("esports", "Online") == "Esports online"
        assert default_title("hiking", "Off campus (see note)") == "Hiking off campus"


# ------------------------------------------------ clubs, for real club officers

def _club_with_member(accounts, client, app):
    """An approved club run by captain@uw.edu, with member@uw.edu confirmed and fan@uw.edu following."""
    club = _approved_club(accounts, client, app)
    accounts.signup(email="member@uw.edu", name="Mem Ber")
    client.post(f"/clubs/{club}/join", data={"message": "Yes!"})
    accounts.logout()
    accounts.signup(email="fan@uw.edu", name="Fan Follower")
    client.post(f"/clubs/{club}/follow")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    client.post(f"/clubs/{club}/members/{_user_id(app, 'member@uw.edu')}/approve")
    return club


def test_officers_add_their_club_logo(accounts, client, app):
    club = _club_with_member(accounts, client, app)
    assert "Add logo" in client.get(f"/clubs/{club}").data.decode()
    client.post(f"/clubs/{club}/logo/edit", data={"logo": (BytesIO(make_image()), "logo.png")},
                content_type="multipart/form-data")
    page = client.get(f"/clubs/{club}").data.decode()
    logo_url = re.search(r'src="(/clubs/\d+/logo\?v=[^"]+)"', page).group(1)
    image = client.get(logo_url)
    assert image.status_code == 200 and image.mimetype == "image/jpeg"
    assert logo_url in client.get("/clubs").data.decode()               # in the club list too
    accounts.logout()
    accounts.login(email="member@uw.edu")
    assert client.get(f"/clubs/{club}/logo/edit").status_code == 403   # only officers


def test_club_share_page_has_a_qr_code_for_flyers(accounts, client, app):
    club = _club_with_member(accounts, client, app)
    page = client.get(f"/clubs/{club}/share").data.decode()
    assert f"/clubs/{club}/qr.svg" in page and "Scan to join" in page and "data-print" in page
    qr = client.get(f"/clubs/{club}/qr.svg")
    assert qr.status_code == 200 and qr.data.startswith(b'<svg xmlns="http://www.w3.org/2000/svg"')
    client.post("/clubs/new", data={**CLUB, "name": "Pending Club"})
    assert client.get(f"/clubs/{_club_id(app, 'Pending Club')}/share").status_code == 404   # not verified yet


def test_weekly_practices_in_one_go_and_followers_hear_about_it(accounts, client, app):
    club = _club_with_member(accounts, client, app)
    form = event_form(title="Tuesday practice", sport="spikeball", location="The Quad", repeat="4", club=str(club))
    first = event_id_from(client.post(f"/events/new?club={club}", data=form))
    with app.app_context():
        rows = get_db().execute("SELECT starts_at FROM events WHERE club_id = ? ORDER BY starts_at", (club,)).fetchall()
        post = get_db().execute("SELECT body, event_id FROM club_posts WHERE club_id = ?", (club,)).fetchone()
    from sportive.timeutil import from_db
    days = [from_db(row["starts_at"]) for row in rows]
    assert len(days) == 4 and all((b - a).days == 7 for a, b in zip(days, days[1:]))
    assert post["event_id"] == first and "for 4 weeks" in post["body"]
    accounts.logout()
    accounts.login(email="fan@uw.edu")
    updates = client.get("/clubs/updates").data.decode()
    assert "Tuesday practice" in updates and f"/events/{first}" in updates
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    assert b"up to 12 weeks" in client.post(f"/events/new?club={club}", data={**form, "repeat": "40"},
                                            follow_redirects=True).data


def test_members_only_club_events(accounts, client, app):
    club = _club_with_member(accounts, client, app)
    event = event_id_from(client.post(f"/events/new?club={club}", data=event_form(
        title="Members scrimmage", sport="spikeball", location="The Quad", is_private="members", club=str(club))))
    accounts.logout()
    accounts.login(email="fan@uw.edu")                     # following isn't membership
    assert "Members scrimmage" not in client.get("/?scope=all").data.decode()
    page = client.get(f"/events/{event}").data.decode()
    assert "Members only" in page and "Join the club" in page
    assert b"is for UW Spikeball Club members" in client.post(f"/events/{event}/join", follow_redirects=True).data
    accounts.logout()
    accounts.login(email="member@uw.edu")
    assert "Members scrimmage" in client.get("/?scope=all").data.decode()
    assert b"You&#39;re in" in client.post(f"/events/{event}/join", follow_redirects=True).data


def test_officers_get_a_roster_members_dont(accounts, client, app):
    club = _club_with_member(accounts, client, app)
    page = client.get(f"/clubs/{club}").data.decode()
    assert "member@uw.edu" in page and "Copy all emails" in page and "Download roster" in page
    csv_file = client.get(f"/clubs/{club}/roster.csv")
    assert csv_file.mimetype == "text/csv" and b"Mem Ber,member@uw.edu" in csv_file.data
    assert "uw-spikeball-club-roster.csv" in csv_file.headers["Content-Disposition"]
    accounts.logout()
    accounts.login(email="member@uw.edu")
    page = client.get(f"/clubs/{club}").data.decode()
    assert "captain@uw.edu" not in page and "Copy all emails" not in page
    assert client.get(f"/clubs/{club}/roster.csv").status_code == 403


def test_roster_names_cant_become_spreadsheet_formulas():
    from sportive.clubs import spreadsheet_safe
    assert spreadsheet_safe('=HYPERLINK("http://evil","x")').startswith("'=")
    assert spreadsheet_safe("+1 234") == "'+1 234" and spreadsheet_safe("@me") == "'@me"
    assert spreadsheet_safe("Mem Ber") == "Mem Ber"


def test_search_engines_and_link_previews(client, app):
    """So "sportive circle" can be found on Google, and shared links show a card in iMessage."""
    app.config["PUBLIC_URL"] = "https://sportivecircle.com"
    page = client.get("/").data.decode()
    assert '<link rel="canonical" href="https://sportivecircle.com/">' in page
    assert 'property="og:image" content="https://sportivecircle.com/static/share-card.png' in page
    robots = client.get("/robots.txt").data.decode()
    assert "Disallow: /messages" in robots and "Sitemap: https://sportivecircle.com/sitemap.xml" in robots
    sitemap = client.get("/sitemap.xml")
    assert sitemap.mimetype == "application/xml"
    assert b"<loc>https://sportivecircle.com/clubs</loc>" in sitemap.data and b"/faq</loc>" in sitemap.data


def test_public_address_is_our_domain_on_render(tmp_path, monkeypatch):
    """Links in emails, shares and the canonical tag use sportivecircle.com, not the onrender.com address."""
    def address():
        return create_app({"TESTING": True, "DATABASE": str(tmp_path / "a.db")}).config["PUBLIC_URL"]

    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    assert address() == "http://localhost:5050"
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://sportive-circle.onrender.com")
    assert address() == "https://sportivecircle.com"
    monkeypatch.setenv("PUBLIC_URL", " https://example.org \n")
    assert address() == "https://example.org"


def test_settings_page_is_separate_from_edit_profile(accounts, client, app):
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    assert ">Settings</a>" in client.get(f"/u/{me}").data.decode()
    page = client.get("/settings").data.decode()
    for part in ("Notifications", "Change password", "Look", "Email me an hour before", "Log out",
                 "Delete my account"):
        assert part in page, part
    assert "/profile/edit" not in page                                 # Edit profile lives on the profile page
    edit = client.get("/profile/edit").data.decode()
    assert "Change password" not in edit and "email_reminders" not in edit and "Delete my account" not in edit
    client.post("/settings/reminders", data={})                       # switch reminder emails off
    client.post("/profile/edit", data={"full_name": "Dubs Husky"})    # editing the profile doesn't touch them
    with app.app_context():
        assert get_db().execute("SELECT email_reminders FROM users WHERE id = ?", (me,)).fetchone()[0] == 0
    assert client.get("/profile/notifications").headers["Location"].endswith("/settings/notifications")


def test_dark_mode_from_sign_up_and_settings(accounts, client, app):
    accounts.signup(verify=False)
    page = client.get("/signup/sports").data.decode()                 # sign-up screen 2
    assert 'name="theme" value="dark"' in page and "Match my phone" in page
    client.post("/verify", data={"code": accounts.code_for("dubs@uw.edu")})
    accounts.upload_photo()                                       # signed up with the default look
    assert 'data-theme="light"' in client.get("/").data.decode()
    client.post("/settings/look", data={"theme": "dark"})
    assert 'data-theme="dark"' in client.get("/").data.decode()
    client.post("/settings/look", data={"theme": "neon"})   # nonsense is ignored
    assert 'data-theme="dark"' in client.get("/").data.decode()
    accounts.logout()
    client.post("/signup", data={"full_name": "Night Owl", "email": "owl@uw.edu", "password": "purple-and-gold",
                                 "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    client.post("/signup/sports", data={"theme": "system"})
    with app.app_context():
        assert get_db().execute("SELECT theme FROM users WHERE email = 'owl@uw.edu'").fetchone()[0] == "system"
    assert 'data-theme="system"' in client.get("/verify").data.decode()   # the code page already matches


def test_each_notification_shows_in_one_place(accounts, client, app):
    """Feedback: notifications repeated (a message on the Messages icon AND in the bell)."""
    from sportive.notifications import KINDS
    places = {kind.key: kind.place for kind in KINDS}
    assert places["messages"] == "messages" and places["friend_requests"] == "friends"
    assert places["invites"] == "bell" and places["club_updates"] == "clubs"
    accounts.signup()
    settings = client.get("/settings/notifications").data.decode()
    assert settings.count('class="switch"') == 9          # club requests (officers) and trends (admins) hidden
    assert settings.count("In the bell") == 1 and "On the messages icon" in settings   # one heading per place


def _invite_path(page):
    return re.search(r'data-share-url="https?://[^/"]+(/join/[^"]+)"', page).group(1)


def test_invite_link_signs_up_a_new_friend_and_puts_them_in_the_game(accounts, client, app):
    """Feedback: 'AB wants you in their game. Click here to sign up', and after signing up you're in the game."""
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    game = event_id_from(client.post("/events/new", data=event_form(title="Friday hoops", is_private="1",
                                                                     password="dawgs1234")))
    page = client.get(f"/events/{game}").data.decode()
    assert "Maya wants you in their Sportive Circle game: Friday hoops" in page
    link = _invite_path(page)
    accounts.logout()
    landing = client.get(link).data.decode()
    assert "Maya wants you in their game" in landing and "Friday hoops" in landing and "Sign up and join" in landing
    client.post("/signup", data={"full_name": "New Friend", "email": "new@uw.edu", "password": "purple-and-gold",
                                 "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    done = client.post("/verify", data={"code": accounts.code_for("new@uw.edu")})
    assert done.headers["Location"] == f"/events/{game}"
    new = _user_id(app, "new@uw.edu")
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (game, new)).fetchone()  # in!
        assert db.execute("SELECT status FROM friendships").fetchone()[0] == "accepted"
    accounts.upload_photo()                                   # the photo step, then back to the game
    assert "You're going" in client.get(f"/events/{game}").data.decode()
    accounts.logout()
    accounts.login(email="maya@uw.edu")
    assert "New joined from your link and is in Friday hoops" in client.get("/notifications").data.decode()


def test_invite_link_for_people_who_already_have_an_account(accounts, client, app):
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    link = _invite_path(client.get(f"/events/{game}").data.decode())
    accounts.logout()
    accounts.signup(email="old@uw.edu", name="Old Timer")        # logged in: opening the link asks first
    old = _user_id(app, "old@uw.edu")
    assert b"Join the game" in client.get(link).data
    with app.app_context():
        assert not get_db().execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (game, old)).fetchone()
        assert not get_db().execute("SELECT 1 FROM friendships").fetchone()
    assert client.post(link).headers["Location"] == f"/events/{game}"
    with app.app_context():
        assert get_db().execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (game, old)).fetchone()
    accounts.logout()
    accounts.signup(email="later@uw.edu", name="Later Gator")
    accounts.logout()
    client.get(link)                                              # logged out: "I have an account" -> log in
    assert accounts.login(email="later@uw.edu").headers["Location"] == f"/events/{game}"
    # A made-up or edited link does nothing.
    assert b"doesn&#39;t work anymore" in client.get("/join/WzEsIDJd.forged", follow_redirects=True).data


def test_a_players_link_to_a_private_game_needs_the_hosts_ok(accounts, client, app):
    ids = _people(accounts, app, "Hana", "Pat", "Solo")
    _as(accounts, "Hana")
    game = event_id_from(client.post("/events/new", data=event_form(is_private="1", password="dawgs26", title="Hoops")))
    _as(accounts, "Pat")
    client.post(f"/events/{game}/join", data={"password": "dawgs26"})
    link = _invite_path(client.get(f"/events/{game}").data.decode())
    _as(accounts, "Solo")
    assert b"Asked Hana" in client.post(link, follow_redirects=True).data
    with app.app_context():
        db = get_db()
        assert not db.execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (game, ids["Solo"])).fetchone()
        assert db.execute("SELECT status FROM invites WHERE guest_id = ?", (ids["Solo"],)).fetchone()[0] == "requested"
    _as(accounts, "Hana")
    assert "Pat wants to bring Solo to Hoops" in client.get("/notifications").data.decode()


def test_invite_links_expire(accounts, client, app, monkeypatch):
    from datetime import timedelta as td
    from sportive import parties
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    link = _invite_path(client.get(f"/events/{game}").data.decode())
    accounts.logout()
    assert b"Maya wants you in their game" in client.get(link).data
    monkeypatch.setattr(parties, "LINK_MAX_AGE", td(seconds=-1))
    assert b"doesn&#39;t work anymore" in client.get(link, follow_redirects=True).data


def test_invite_friends_to_the_app_makes_you_friends(accounts, client, app):
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    link = _invite_path(client.get("/friends").data.decode())
    assert "Invite friends to Sportive Circle" in client.get("/friends").data.decode()
    accounts.logout()
    assert "Maya wants you on Sportive Circle" in client.get(link).data.decode()
    client.post("/signup", data={"full_name": "Pal Friend", "email": "pal@uw.edu", "password": "purple-and-gold",
                                 "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    client.post("/verify", data={"code": accounts.code_for("pal@uw.edu")})
    with app.app_context():
        assert get_db().execute("SELECT status FROM friendships").fetchone()[0] == "accepted"


def test_sign_up_is_short_screens(client, app):
    """Screen 1 checks the details (and emails the code); screen 2 is sports; screen 3 (optional) is texts."""
    page = client.get("/signup").data.decode()
    assert "Step 1 of 4" in page and 'name="sports"' not in page and ">Next</button>" in page   # (3 without texts)
    bad = client.post("/signup", data={"full_name": "Dubs Husky", "email": "dubs@gmail.com", "password": "purple-and-gold",
                                       "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    assert bad.status_code == 200 and b"Please use your UW email" in bad.data  # Next still checks everything
    assert client.get("/signup/sports").headers["Location"] == "/signup"      # can't skip screen 1
    step1 = client.post("/signup", data={"full_name": "Dubs Husky", "email": "dubs@uw.edu", "password": "purple-and-gold",
                                         "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    assert step1.headers["Location"] == "/signup/sports"
    page = client.get("/signup/sports").data.decode()
    assert "Step 2 of 4" in page and 'value="soccer"' in page
    assert client.post("/signup/sports", data={"sports": ["soccer", "tennis", "made-up"]}).headers["Location"] == "/signup/texts"
    assert client.post("/signup/texts", data={"phone": ""}).headers["Location"] == "/verify"   # skipping is fine
    with app.app_context():
        sports = {r[0] for r in get_db().execute("SELECT sport FROM user_sports")}
    assert sports == {"soccer", "tennis"}


def test_logged_in_people_skip_login_and_signup(accounts, client):
    accounts.signup()
    assert client.get("/login").headers["Location"] == "/"
    assert client.get("/signup?next=/me/events").headers["Location"] == "/me/events"


def test_remember_me(accounts, client):
    accounts.signup()
    accounts.logout()
    assert b'name="remember" value="1" checked' in client.get("/login").data
    client.post("/login", data={"email": "dubs@uw.edu", "password": "purple-and-gold", "remember": "1"})
    cookie = client.get_cookie("session")
    assert cookie.expires is not None  # stays logged in after the browser closes
    accounts.logout()
    client.post("/login", data={"email": "dubs@uw.edu", "password": "purple-and-gold"})  # box unticked
    cookie = client.get_cookie("session")
    assert cookie.expires is None and client.get("/settings").status_code == 200  # logged in until the browser closes


def test_help_bubble_can_be_closed(accounts, client):
    """A small "Help?" bubble links to the FAQ and has an × (app.js remembers it's closed)."""
    home = client.get("/").data.decode()
    assert "data-help-bubble" in home and "<span>Help?</span>" in home and "data-help-close" in home
    for page in ("/login", "/signup", "/faq"):  # not on sign-up screens or the help page itself
        assert "data-help-bubble" not in client.get(page).data.decode()
    accounts.signup()
    assert "data-help-bubble" in client.get("/clubs").data.decode()


def test_admin_pages_have_no_help_bubble_and_say_to_check_socials(accounts, client, app):
    """The bubble covered the Send back button, and the page still said to check the "official page"."""
    app.config["ADMIN_EMAILS"] = "dubs@uw.edu"
    accounts.signup()
    for page in ("/admin/clubs", "/admin/reports", "/admin/suggestions"):
        assert "data-help-bubble" not in client.get(page).data.decode(), page
    assert "Open the club's social accounts or website" in client.get("/admin/clubs").data.decode()


def test_linkedin_on_profiles(accounts, client, app):
    """People can add LinkedIn like the other socials; a pasted profile link works too."""
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    assert 'name="linkedin"' in client.get("/profile/edit/sports").data.decode()
    client.post("/profile/edit/sports", data={"linkedin": "https://www.linkedin.com/in/dubs-husky/?trk=x"})
    page = client.get(f"/u/{me}").data.decode()
    assert 'href="https://www.linkedin.com/in/dubs-husky"' in page and "in/dubs-husky" in page
    client.post("/profile/edit/sports", data={"linkedin": "dubs-husky-2"})       # just the name works too
    assert 'linkedin.com/in/dubs-husky-2"' in client.get(f"/u/{me}").data.decode()
    bad = client.post("/profile/edit/sports", data={"linkedin": "<script>"}).data
    assert b"That LinkedIn doesn" in bad


def test_players_pick_when_their_reminder_comes(accounts, client, app, monkeypatch):
    """After joining: an hour before (default), 30 min before, or no reminder."""
    from sportive import reminders
    sent = []
    monkeypatch.setattr(reminders, "send_email", lambda to, subject, body, **kwargs: sent.append(to))
    _reminder_setup(accounts, client, app, joined_minutes_before=120)   # game starts in ~40 min; player logged in
    page = client.get("/events/1").data.decode()
    assert "Email reminder" in page and '<option value="60" selected>1 hour before</option>' in page
    client.post("/events/1/reminder", data={"remind": "30"})
    assert '<option value="30" selected>30 min before</option>' in client.get("/events/1").data.decode()
    with app.app_context():
        reminders.send_due_reminders()
    assert sent == ["host@uw.edu"]                  # 40 min away: the host (1 hour) gets it, the player not yet
    with app.app_context():
        get_db().execute("UPDATE events SET starts_at = ?", (reminders.to_db(now_local() + timedelta(minutes=25)),))
        get_db().commit()
        reminders.send_due_reminders()
    assert sorted(sent) == ["host@uw.edu", "player@uw.edu"]      # now within 30 min
    client.post("/events/1/reminder", data={"remind": "0"})
    assert client.post("/events/1/reminder", data={"remind": "45"}).status_code == 400   # only the listed choices


def test_tap_someones_photo_to_see_it_big(accounts, client, app):
    """Like Instagram: on someone else's profile their photo opens big (and closes again); yours opens the editor."""
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    maya = _user_id(app, "maya@uw.edu")
    mine = client.get(f"/u/{maya}").data.decode()
    assert 'data-zoom="photo-big"' not in mine and "/profile/photo" in mine
    accounts.logout()
    accounts.signup(email="me@uw.edu")
    page = client.get(f"/u/{maya}").data.decode()
    assert 'data-zoom="photo-big"' in page and '<dialog id="photo-big" class="photo-lightbox"' in page
    assert f'/u/{maya}/photo?v=' in page and 'width="640"' in page


def test_a_game_full_because_of_a_reserved_spot_is_hidden(accounts, client, app):
    """The user: "if an event is full (even for the 30 min a spot is reserved) you can't see it"."""
    ids = _people(accounts, app, "Maya", "Friend", "Stranger")
    _friends(app, ids["Maya"], ids["Friend"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Held run", players="2",
                                                                     reserve=[str(ids["Friend"])])))
    assert "Held run" in client.get("/?scope=all").data.decode()               # the host still sees it
    _as(accounts, "Stranger")
    assert "Held run" not in client.get("/?scope=all").data.decode()           # Maya + 1 held spot = 2 of 2
    assert "Held run" not in client.get(f"/u/{ids['Maya']}").data.decode()     # not on Maya's profile either
    assert "Held run" in client.get("/?scope=full").data.decode()              # only in the Full tab
    assert b"Sorry, this game is full." in client.post(f"/events/{game}/join", follow_redirects=True).data
    _as(accounts, "Friend")
    assert "Held run" in client.get("/?scope=all").data.decode()               # the friend it's held for sees it
    with app.app_context():                                                    # 30 minutes later the hold is over:
        get_db().execute("UPDATE invites SET expires_at = '2000-01-01 00:00'")
        get_db().commit()
    _as(accounts, "Stranger")
    assert "Held run" in client.get("/?scope=all").data.decode()               # open again for everyone


def test_reserve_spots_on_a_full_game_says_why(accounts, client, app):
    """Tester: "I tried reserving a spot for a full game I'm going to. It should say why I can't." """
    _people(accounts, app, "Maya", "Me")
    _as(accounts, "Maya")
    full_id = event_id_from(client.post("/events/new", data=event_form(title="Packed run", players="2")))
    _as(accounts, "Me")
    client.post(f"/events/{full_id}/join")                          # 2 of 2: full, and I'm going
    assert f"/events/{full_id}/party" not in client.get(f"/events/{full_id}").data.decode()  # no Reserve button
    page = client.get(f"/events/{full_id}/party", follow_redirects=True).data.decode()
    assert "This game is full, so there&#39;s no spot to reserve" in page


def test_no_huskylink_wording_left_for_clubs(accounts, client):
    """HuskyLink isn't asked for anymore, so it shouldn't show up in the club form or on the home page."""
    assert "HuskyLink" not in client.get("/").data.decode()
    accounts.signup()
    form = client.get("/clubs/new").data.decode()
    assert "HuskyLink" not in form and "Registered Student Organization" in form


def test_top_dawgs_has_ten_spots():
    from sportive import spirit
    assert spirit.TOP_DAWGS == 10 and spirit.top_dawgs.__defaults__[0] == 10


def test_club_review_goes_to_the_bell_too(accounts, client, app, monkeypatch):
    """Officers got the "sent back" note by email only; now it's in their notifications too, and so is
    "approved" (which also shows confetti when they open the club)."""
    from sportive import clubs
    monkeypatch.setattr(clubs, "send_email", lambda *args, **kwargs: None)
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app)
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    client.post(f"/admin/clubs/{club}/reject", data={"note": "Add your club's Instagram."})
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    bell = client.get("/notifications").data.decode()
    assert "UW Spikeball Club was sent back: “Add your club&#39;s Instagram.” Update it and resend." in bell
    # Resending it exactly as it was isn't allowed: something has to change.
    form = client.get(f"/clubs/{club}/edit").data.decode()
    assert "data-must-change" in form and "Resend for review" in form
    page = client.post(f"/clubs/{club}/edit", data=CLUB).data.decode()
    assert 'role="status" >No changes were made.' in page                              # the caption shows
    with app.app_context():
        assert get_db().execute("SELECT status FROM clubs").fetchone()[0] == "rejected"   # not resent
    client.post(f"/clubs/{club}/edit", data={**CLUB, "instagram": "uwspikeball2"})     # a real change
    with app.app_context():
        assert get_db().execute("SELECT status FROM clubs").fetchone()[0] == "pending"
    accounts.logout()
    accounts.login(email="admin@uw.edu")
    client.post(f"/admin/clubs/{club}/approve")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    bell = client.get("/notifications").data.decode()
    assert "UW Spikeball Club is verified and live!" in bell and "sent back" not in bell   # replaces the old one
    assert f"/clubs/{club}?approved=1" in bell
    page = client.get(f"/clubs/{club}?approved=1").data.decode()
    assert "flash-celebrate" in page and "is verified!" in page                            # confetti


def test_open_to_anyone_or_other(accounts, client, app):
    """Hosts pick Anyone, Women, Men, Nonbinary or Other; profiles offer Other too."""
    ids = _people(accounts, app, "Host", "Wren", "Olly")
    _set_gender(app, ids["Wren"], "woman")
    _set_gender(app, ids["Olly"], "other")
    _as(accounts, "Host")
    form = client.get("/events/new").data.decode()
    for label in (">Anyone</option>", ">Women</option>", ">Men</option>", ">Nonbinary</option>", ">Other</option>"):
        assert label in form, label
    assert ">Other</option>" in client.get("/profile/edit").data.decode()
    game = event_id_from(client.post("/events/new", data=event_form(open_to="other", title="Other run")))
    assert "Other only" in client.get(f"/events/{game}").data.decode()
    _as(accounts, "Wren")
    assert b"This game is for people who chose Other." in client.post(f"/events/{game}/join", follow_redirects=True).data
    _as(accounts, "Olly")
    assert b"You&#39;re in" in client.post(f"/events/{game}/join", follow_redirects=True).data
    accounts.logout()
    accounts.signup(email="officer@uw.edu")
    assert ">Anyone</span>" in client.get("/clubs/new").data.decode()


# ---------------------------------------------------------------- texts (SMS)

def _texts(monkeypatch):
    """Capture texts instead of sending them."""
    from sportive import sms
    sent = []
    monkeypatch.setattr(sms, "send_sms", lambda to, body: sent.append((to, body)) or True)
    return sent


def test_phone_numbers_are_cleaned_up():
    from sportive.sms import normalize_phone, pretty_phone
    assert normalize_phone("(206) 555-0142") == normalize_phone("206.555.0142") == "+12065550142"
    assert normalize_phone("+1 206 555 0142") == normalize_phone("1-206-555-0142") == "+12065550142"
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"
    assert normalize_phone("555-0142") is None and normalize_phone("hello") is None and normalize_phone("") is None
    assert pretty_phone("+12065550142") == "(206) 555-0142"


def test_sign_up_with_texts(client, app, monkeypatch):
    """Optional step 3: a phone number with permission, confirmed with a texted code on the same code page."""
    sent = _texts(monkeypatch)
    client.post("/signup", data={"full_name": "Dubs Husky", "email": "dubs@uw.edu", "password": "purple-and-gold",
                                 "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    client.post("/signup/sports", data={"sports": ["soccer"]})
    page = client.get("/signup/texts").data.decode()
    assert "Step 3 of 4" in page and "Reply STOP" in page and 'name="consent"' in page
    assert b"Tick the box" in client.post("/signup/texts", data={"phone": "206-555-0142"}).data   # permission first
    assert b"doesn&#39;t look like a phone number" in client.post("/signup/texts",
                                                                  data={"phone": "12", "consent": "1"}).data
    assert client.post("/signup/texts", data={"phone": "206-555-0142", "consent": "1"}).headers["Location"] == "/verify"
    assert sent[-1][0] == "+12065550142" and "Sportive Circle code:" in sent[-1][1]
    page = client.get("/verify").data.decode()
    assert "Code we texted to (•••) •••-0142" in page and "Code from your email" in page
    with app.app_context():
        row = get_db().execute("SELECT verify_code, sms_code FROM users").fetchone()
    client.post("/verify", data={"code": row["verify_code"], "phone_code": row["sms_code"]})
    with app.app_context():
        user = get_db().execute("SELECT verified, phone_verified, sms_updates, sms_consent_at FROM users").fetchone()
    assert user["verified"] == 1 and user["phone_verified"] == 1 and user["sms_updates"] == 1 and user["sms_consent_at"]


def test_texts_only_go_to_confirmed_opted_in_numbers(accounts, client, app, monkeypatch):
    from sportive import sms
    sent = _texts(monkeypatch)
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    with app.app_context():
        assert sms.text_user(me, "hi") is False                                   # no number
    client.post("/settings/texts", data={"action": "send", "phone": "(206) 555-0142", "consent": "1"})
    with app.app_context():
        assert sms.text_user(me, "hi") is False                                   # not confirmed yet
        code = get_db().execute("SELECT sms_code FROM users WHERE id = ?", (me,)).fetchone()[0]
    assert b"isn&#39;t right" in client.post("/settings/texts", data={"action": "confirm", "code": "000000"},
                                             follow_redirects=True).data
    client.post("/settings/texts", data={"action": "confirm", "code": code})
    assert "(206) 555-0142" in client.get("/settings/texts").data.decode()
    with app.app_context():
        assert sms.text_user(me, "Game at 5") is True and sent[-1] == ("+12065550142", "Sportive Circle: Game at 5")
    client.post("/settings/texts", data={"action": "toggle"})                     # switched off
    with app.app_context():
        assert sms.text_user(me, "hi") is False
    client.post("/settings/texts", data={"action": "toggle", "sms_updates": "1"})
    client.post("/settings/texts", data={"action": "remove"})
    with app.app_context():
        assert sms.text_user(me, "hi") is False
        assert get_db().execute("SELECT phone FROM users WHERE id = ?", (me,)).fetchone()[0] == ""


def test_replying_stop_turns_texts_off(accounts, client, app, monkeypatch):
    from sportive import sms
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    with app.app_context():
        get_db().execute("UPDATE users SET phone = '+12065550142', phone_verified = 1, sms_updates = 1")
        get_db().commit()

        def opted_out(to, body):
            raise sms.SmsError(sms.OPTED_OUT, "unsubscribed")
        monkeypatch.setattr(sms, "send_sms", opted_out)
        assert sms.text_user(me, "hi") is False
        assert get_db().execute("SELECT sms_updates FROM users").fetchone()[0] == 0


def test_code_texts_are_limited(accounts, client, app, monkeypatch):
    from sportive import sms
    _texts(monkeypatch)
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    with app.app_context():
        for n in range(sms.MAX_CODES_PER_DAY):
            get_db().execute("UPDATE users SET sms_sent_at = NULL")
            assert sms.start_phone_check(me, f"+1206555010{n}") is None
        get_db().execute("UPDATE users SET sms_sent_at = NULL")
        assert "a lot of codes" in sms.start_phone_check(me, "+12065550199")


def test_reminders_and_invites_are_texted_too(accounts, client, app, monkeypatch):
    from sportive import reminders
    sent = _texts(monkeypatch)
    monkeypatch.setattr(reminders, "send_email", lambda *args, **kwargs: None)
    _reminder_setup(accounts, client, app, joined_minutes_before=120)   # player is logged in
    with app.app_context():
        get_db().execute("UPDATE users SET phone = '+12065550142', phone_verified = 1, sms_updates = 1,"
                         " email_reminders = 0 WHERE email = 'player@uw.edu'")
        get_db().commit()
        reminders.send_due_reminders()
    assert any(to == "+12065550142" and "Evening hoops starts at" in body for to, body in sent)
    # an invite (spot held) is texted after it's saved
    ids = {"player": _user_id(app, "player@uw.edu"), "host": _user_id(app, "host@uw.edu")}
    _friends(app, ids["player"], ids["host"])
    game = event_id_from(client.post("/events/new", data=event_form(title="Texted run", players="6")))
    client.post(f"/events/{game}/party", data={"friend": str(ids["host"])})
    with app.app_context():
        get_db().execute("UPDATE users SET phone = '+12065550199', phone_verified = 1, sms_updates = 1"
                         " WHERE email = 'host@uw.edu'")
        get_db().commit()
    game2 = event_id_from(client.post("/events/new", data=event_form(title="Second run", players="6")))
    client.post(f"/events/{game2}/party", data={"friend": str(ids["host"])})
    assert any(to == "+12065550199" and "Second run" in body and "held for 30 min" in body for to, body in sent)


def test_password_reset_code_is_texted_to_confirmed_numbers(accounts, client, app, monkeypatch):
    sent = _texts(monkeypatch)
    accounts.signup()
    accounts.logout()
    with app.app_context():
        get_db().execute("UPDATE users SET phone = '+12065550142', phone_verified = 1, verify_sent_at = NULL")
        get_db().commit()
    client.post("/forgot", data={"email": "dubs@uw.edu"})
    assert sent and sent[-1][0] == "+12065550142" and "password reset code" in sent[-1][1]


def test_notifications_show_when_they_happened(accounts, client, app):
    """Not "happening now": each notice says how long ago it came in."""
    from datetime import timedelta
    from sportive.notifications import notify
    from sportive.timeutil import fmt_ago, now_local, to_db
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    now = now_local()
    assert fmt_ago(to_db(now)) == "Just now"
    assert fmt_ago(to_db(now - timedelta(minutes=12))) == "12 min ago"
    assert fmt_ago(to_db(now - timedelta(days=1))).startswith("Yesterday, ")
    assert fmt_ago(to_db(now - timedelta(days=30))) == f"{(now - timedelta(days=30)).strftime('%b')} {(now - timedelta(days=30)).day}"
    with app.app_context():
        notify(me, "account", "Hello there", "/")
        get_db().execute("UPDATE notices SET created_at = ?", (to_db(now - timedelta(minutes=5)),))
        get_db().commit()
    home = client.get("/").data.decode()
    assert 'class="bell-link"' in home and '<span class="count-dot">1</span>' in home     # the number on the bell
    page = client.get("/notifications").data.decode()
    assert "5 min ago" in page and "happening now" not in page


def test_a_reserved_spot_is_texted(accounts, client, app, monkeypatch):
    """Whenever a spot is held for you (reserved when a game is made, with Reserve spots, or a host saying yes
    to a friend in a private game), people who turned texts on get a text."""
    sent = _texts(monkeypatch)
    ids = _people(accounts, app, "Maya", "Kai", "Lee")
    _friends(app, ids["Maya"], ids["Kai"], ids["Lee"])
    _friends(app, ids["Kai"], ids["Lee"])
    with app.app_context():
        get_db().execute("UPDATE users SET phone = '+1206555' || printf('%04d', id), phone_verified = 1, sms_updates = 1")
        get_db().commit()
        phone = {name: get_db().execute("SELECT phone FROM users WHERE id = ?", (uid,)).fetchone()[0]
                 for name, uid in ids.items()}
    _as(accounts, "Maya")
    client.post("/events/new", data=event_form(title="Made with Kai", players="6", reserve=[str(ids["Kai"])]))
    assert any(to == phone["Kai"] and "Made with Kai" in body and "held for 30 min" in body for to, body in sent)
    game = event_id_from(client.post("/events/new", data=event_form(title="Private run", players="6",
                                                                     is_private="1", password="dawgs1234")))
    _as(accounts, "Kai")
    client.post(f"/events/{game}/join", data={"password": "dawgs1234"})
    client.post(f"/events/{game}/party", data={"friend": str(ids["Lee"]), "note": "my roommate"})   # asks Maya
    assert not any(to == phone["Lee"] for to, body in sent)                     # nothing held yet
    _as(accounts, "Maya")
    client.post(f"/events/{game}/requests/{ids['Lee']}/approve")
    assert any(to == phone["Lee"] and "held for 30 min" in body for to, body in sent)
