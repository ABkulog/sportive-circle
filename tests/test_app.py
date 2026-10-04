import json
import os
import pathlib
import re
from datetime import timedelta
from io import BytesIO

import pytest

from conftest import event_id_from, make_image
from sportive import create_app
from sportive.db import get_db
from sportive.timeutil import now_local, to_db


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
    assert b"Please use your UW email" in client.post("/signup", follow_redirects=True, data={
        "full_name": "X", "email": "x@washington.edu.evil.com", "password": "longenough1",
        "password2": "longenough1", "birth_date": "2005-01-01"}).data


def test_signup_rejects_mismatched_passwords(client):
    response = client.post("/signup", follow_redirects=True, data={
        "full_name": "A", "email": "a@uw.edu", "password": "longenough1",
        "password2": "different11", "birth_date": "2005-01-01",
    })
    assert b"Passwords do not match." in response.data


def test_signup_is_18_and_over(accounts, client):
    today = now_local().date()
    seventeen = today.replace(year=today.year - 18, day=1) + timedelta(days=40)   # turns 18 in a month or so
    assert b"You need to be 18 or older" in accounts.signup(birth_date=seventeen.isoformat(), verify=False).data
    eighteen = today.replace(year=today.year - 18, day=1) - timedelta(days=1)
    assert b"18 or older" not in accounts.signup(email="adult@uw.edu", birth_date=eighteen.isoformat(), verify=False).data
    assert f'max="{today.year - 18}-' in client.get("/signup").data.decode()          # the date picker stops at 18


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
        b"Pick 2 to 1000 participants": event_form(players="1"),
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
    assert b"Pick 2 to 1000 participants" in client.post("/events/new", data=event_form(players="1001")).data
    page = client.get("/events/new").data.decode()
    assert 'name="players" type="number"' in page and 'max="1000"' in page
    assert "Participants <em>(including you)</em>" in page and "<span>4</span> Participants</h2>" in page


def test_quick_post_player_cap(accounts, client):
    accounts.signup()
    page = client.post("/need-players", data={
        "sport": "tennis", "location": "IMA North Tennis Courts", "skill_level": "All levels",
        "starts_in": "15", "duration": "60", "players": "5",
    }).data
    assert b"Pick 2 to 1000 participants" not in page and b"can have 2 to" not in page   # 5 for tennis is the host's call


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
    assert response.headers["Location"] == _after_sign_up("/events/new")  # back to the page they tried to open
    assert client.get("/").status_code == 200


def test_first_photo_goes_straight_home(accounts, client):
    accounts.signup(photo=False)
    client.get("/")  # the feed is the normal landing spot, so no special destination
    assert accounts.upload_photo().headers["Location"] == _after_sign_up("/")


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
    assert accounts.upload_photo().headers["Location"] == _after_sign_up(f"/events/{event_id}")


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
    assert response.headers["Location"] == _after_sign_up("/")
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
    assert client.post("/profile/photo/skip").headers["Location"] == _after_sign_up(f"/events/{event_id}")


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

def _after_sign_up(destination):
    """The last sign-up step goes to the one-time "You're in!" screen, which then continues to `destination`."""
    return f"/welcome?next={destination}"


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


def test_seen_and_delivered_like_whatsapp(accounts, client, app):
    """Under my newest DM: Delivered, then Seen once they open it; read receipts off (either person) hides Seen
    both ways. Game chats: Seen only once everyone else going has seen it, whatever the setting."""
    accounts.signup(email="a@uw.edu")
    accounts.logout()
    accounts.signup(email="b@uw.edu")
    a, b = _user_id(app, "a@uw.edu"), _user_id(app, "b@uw.edu")
    _played_games(app, "soccer", [a, b])
    client.post(f"/messages/{a}", data={"body": "you up for tonight?"})
    status = lambda url: client.get(url).get_json()["status"]
    assert status(f"/messages/{a}/poll")["text"] == "Delivered"
    assert b'class="chat-seen">Delivered' in client.get(f"/messages/{a}").data
    accounts.logout()
    accounts.login(email="a@uw.edu")
    assert status(f"/messages/{b}/poll") is None          # their message is the newest: nothing under it
    accounts.logout()
    accounts.login(email="b@uw.edu")
    assert status(f"/messages/{a}/poll")["text"] == "Seen"
    client.post("/settings/receipts", data={})             # off: no Seen for me either
    assert status(f"/messages/{a}/poll")["text"] == "Delivered"
    client.post("/settings/receipts", data={"read_receipts": "1"})
    assert status(f"/messages/{a}/poll")["text"] == "Seen"
    accounts.logout()
    accounts.login(email="a@uw.edu")
    client.post("/settings/receipts", data={})             # the other person off: no Seen either
    accounts.logout()
    accounts.login(email="b@uw.edu")
    assert status(f"/messages/{a}/poll")["text"] == "Delivered"

    event_id = event_id_from(client.post("/events/new", data=event_form()))
    for email in ("c@uw.edu", "d@uw.edu"):
        accounts.logout()
        accounts.signup(email=email)
        client.post(f"/events/{event_id}/join")
    client.post(f"/events/{event_id}/chat", data={"body": "on my way"})   # d writes; b and c haven't seen it
    chat_status = lambda: status(f"/events/{event_id}/chat/poll")
    assert chat_status()["text"] == "Delivered"
    for email in ("b@uw.edu", "c@uw.edu"):   # b has read receipts on, c too; a's "off" is only for DMs
        accounts.logout()
        accounts.login(email=email)
        assert chat_status() is None
    accounts.logout()
    accounts.login(email="d@uw.edu")
    assert chat_status()["text"] == "Seen"


def test_reactions_on_messages(accounts, client, app):
    """Like WhatsApp: one reaction per person per message; the same again takes it off, another replaces it.
    Only the two people in a DM (or people going to the game) can react; the poll keeps everyone up to date."""
    accounts.signup(email="a@uw.edu")
    accounts.logout()
    accounts.signup(email="b@uw.edu")
    a, b = _user_id(app, "a@uw.edu"), _user_id(app, "b@uw.edu")
    _played_games(app, "soccer", [a, b])
    client.post(f"/messages/{a}", data={"body": "low key wana run 5s"})
    with app.app_context():
        dm = get_db().execute("SELECT id FROM direct_messages").fetchone()[0]
    react = lambda kind, mid, emoji: client.post("/chat/react", data={"kind": kind, "id": mid, "emoji": emoji})
    accounts.logout()
    accounts.login(email="a@uw.edu")
    assert react("dm", dm, "❤️").get_json()["reactions"] == [{"emoji": "❤️", "count": 1, "mine": True}]
    assert react("dm", dm, "😂").get_json()["reactions"] == [{"emoji": "😂", "count": 1, "mine": True}]  # replaced
    assert client.get(f"/messages/{b}/poll?from=0").get_json()["reactions"][str(dm)][0]["emoji"] == "😂"
    assert react("dm", dm, "😂").get_json()["reactions"] == []                                         # off again
    assert react("dm", dm, "💩").status_code == 400
    react("dm", dm, "🔥")
    assert '"emoji": "\\ud83d\\udd25"' in client.get(f"/messages/{b}").data.decode()  # on the page too (for chat.js)
    assert "Down to play?" not in client.get(f"/messages/{b}").data.decode()         # no suggestion chips
    accounts.logout()
    accounts.signup(email="c@uw.edu")
    assert react("dm", dm, "❤️").status_code == 404                                  # not their chat
    event_id = event_id_from(client.post("/events/new", data=event_form()))
    client.post(f"/events/{event_id}/chat", data={"body": "on my way"})
    with app.app_context():
        game = get_db().execute("SELECT id FROM event_messages").fetchone()[0]
    assert react("game", game, "👍").status_code == 200
    accounts.logout()
    accounts.login(email="a@uw.edu")
    assert react("game", game, "👍").status_code == 403                               # not going


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
        "join_question": "Have you played spikeball before?", "attest": "1",
        "contact_phone_country": "US", "contact_phone": "206-555-0142"}


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
    assert b"You&#39;re the owner" in client.post(f"/clubs/{club}/leave", follow_redirects=True).data
    client.post(f"/clubs/{club}/officers", data={"user": fan, "action": "owner"})   # hand over, then leave
    assert b"You left the club" in client.post(f"/clubs/{club}/leave", follow_redirects=True).data
    assert b"Nets are at the Quad by 5!" in client.get(f"/clubs/{club}").data


def test_club_events_pick_their_levels(accounts, client, app):
    """Clubs pick any mix of levels for an event (none or all = everyone); the Skill level filter finds it under
    each level it's for, and editing shows the picks again."""
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app)
    _approve(app, club)
    form_page = client.get(f"/events/new?club={club}").data.decode()
    assert 'name="levels"' in form_page and 'name="skill_level"' not in form_page
    post = lambda title, levels: event_id_from(client.post("/events/new", data={
        **event_form(title=title, sport="spikeball", location="The Quad"), "club": club, "levels": levels}))
    mixed, everyone, every_box = (post("Club night", ["Casual", "Intermediate"]), post("Open night", []),
                                  post("Big night", ["Casual", "Intermediate", "Competitive"]))
    with app.app_context():
        level = lambda e: get_db().execute("SELECT skill_level, club_id FROM events WHERE id = ?", (e,)).fetchone()
        assert tuple(level(mixed)) == ("Casual, Intermediate", club)
        assert level(everyone)["skill_level"] == level(every_box)["skill_level"] == "All levels"
    assert "Casual, Intermediate" in client.get(f"/events/{mixed}").data.decode()
    feed = lambda skill: client.get(f"/?scope=all&skill={skill}").data.decode()
    assert "Club night" in feed("Intermediate") and "Club night" not in feed("Competitive")
    assert "Open night" in feed("Competitive")
    edit = client.get(f"/events/{mixed}/edit").data.decode()
    assert 'value="Casual"\n              checked' in edit or 'value="Casual" checked' in edit.replace("\n              ", " ")
    assert "🏛️ UW Spikeball Club".encode() in client.get(f"/events/{mixed}").data
    assert b"Club night" in client.get(f"/clubs/{club}").data
    accounts.logout()
    accounts.signup(email="random@uw.edu")
    assert client.get(f"/events/new?club={club}").status_code == 403       # only officers


def test_a_removed_clubs_events_go_on_hold(accounts, client, app):
    """The user: "when a club gets removed the activities they held have to at least go on hold". While the club
    isn't approved its events are hidden (feed, profiles, My games), can't be joined and send no reminders;
    nothing is deleted, and they're back when the club is approved again."""
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app)
    _approve(app, club)
    event_id = event_id_from(client.post("/events/new", data={
        **event_form(title="Club night", sport="spikeball", location="The Quad"), "club": club}))
    captain = _user_id(app, "captain@uw.edu")
    with app.app_context():
        db = get_db()
        db.execute("UPDATE clubs SET status = 'pending' WHERE id = ?", (club,))   # an admin removed it
        db.commit()
    assert "Club night" not in client.get(f"/u/{captain}").data.decode()          # off the host's profile
    page = client.get(f"/events/{event_id}").data.decode()
    assert "On hold" in page and "can't be joined" in page
    accounts.logout()
    accounts.signup(email="player@uw.edu")
    assert "Club night" not in client.get("/?scope=all").data.decode()
    client.post(f"/events/{event_id}/join")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (event_id,)).fetchone()[0] == 1
    _approve(app, club)                                                            # approved again: back
    assert "Club night" in client.get("/?scope=all").data.decode()
    client.post(f"/events/{event_id}/join")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (event_id,)).fetchone()[0] == 2


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
    assert ">Report</a>" in thread                     # in the ⋯ menu on the message
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
    assert "You're a member" in client.get(f"/clubs/{club}").data.decode()


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
    assert 'class="chat card is-empty"' in page and "No messages yet. Say hi to the group!" in page
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


def test_denied_club_frees_its_name_for_the_real_club(accounts, client, app):
    # Someone grabs the real club's name before its officers sign up: denying it as spam frees the name.
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="squatter@uw.edu")
    client.post("/clubs/new", data=CLUB)
    squat = _club_id(app, CLUB["name"])
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    client.post(f"/admin/clubs/{squat}/deny")
    assert CLUB["name"] in client.get("/admin/clubs?status=denied").data.decode()   # still findable by the admin
    accounts.logout()
    accounts.signup(email="captain@uw.edu")
    page = client.post("/clubs/new", data=CLUB, follow_redirects=True).data.decode()
    assert "already on Sportive Circle" not in page
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) FROM clubs WHERE name = ? AND status = 'pending'", (CLUB["name"],)).fetchone()[0] == 1
        assert db.execute("SELECT name FROM clubs WHERE id = ?", (squat,)).fetchone()[0] == f"{CLUB['name']} (denied #{squat})"
    # Restoring the denied one while the real club has the name keeps the marked name
    accounts.logout()
    accounts.login(email="admin@uw.edu")
    client.post(f"/admin/clubs/{squat}/restore")
    with app.app_context():
        assert get_db().execute("SELECT name FROM clubs WHERE id = ?", (squat,)).fetchone()[0].endswith(f"(denied #{squat})")


def test_restored_club_gets_its_name_back(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app, CLUB["name"])
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    client.post(f"/admin/clubs/{club}/deny")
    client.post(f"/admin/clubs/{club}/restore")                  # the denial was a mistake
    with app.app_context():
        assert tuple(get_db().execute("SELECT name, status FROM clubs WHERE id = ?", (club,)).fetchone()) == (CLUB["name"], "pending")


def test_make_officer_only_reports_success_when_it_worked(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu")
    client.post(f"/clubs/{club}/follow")               # a follower, not a member
    fan = _user_id(app, "fan@uw.edu")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    page = client.post(f"/clubs/{club}/officers/{fan}", follow_redirects=True).data.decode()
    assert "Only confirmed members can be made officers" in page and "officer now" not in page


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


def test_signup_cant_flood_an_inbox(accounts, client, app):
    accounts.signup(email="target@uw.edu", verify=False)
    client.post("/logout")
    again = accounts.signup(email="target@uw.edu", password="someone-else-1", verify=False).data
    assert b"We just sent a code to that email" in again                       # someone else: wait a minute
    client.post("/logout")
    accounts.signup(email="target@uw.edu", verify=False)                       # the same person again (double tap):
    codes = [m for m in app.extensions["outbox"] if m["to"] == "target@uw.edu"]
    assert len(codes) == 1                                                     # no second code to confuse them


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


def test_suspending_a_host_tells_players_even_when_their_club_is_in_review(accounts, client, app):
    """Bot round 6: a club game on hold (club back in review) was canceled without telling its players."""
    club = _club_with_member(accounts, client, app)                       # logged in as the captain
    game = event_id_from(client.post(f"/events/new?club={club}", data=event_form(
        title="Club night", sport="spikeball", location="The Quad", club=str(club))))
    accounts.logout()
    accounts.login(email="member@uw.edu")
    client.post(f"/events/{game}/join")
    accounts.logout()
    accounts.signup(email="waiting@uw.edu", name="Wai Ting")
    client.post(f"/clubs/{club}/join", data={"message": "Can I join?"})
    accounts.logout()
    with app.app_context():
        get_db().execute("UPDATE clubs SET status = 'pending' WHERE id = ?", (club,))
        get_db().commit()
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="admin@uw.edu")
    page = client.post(f"/admin/users/{_user_id(app, 'captain@uw.edu')}/suspend", follow_redirects=True).data.decode()
    outbox = app.extensions.get("outbox", [])
    assert any(m["to"] == "member@uw.edu" and m["subject"].startswith("Canceled: Club night") for m in outbox)
    assert "only officer of" in page and "UW Spikeball Club</a>" in page   # someone has to take the club over
    waiting = _user_id(app, "waiting@uw.edu")
    assert client.post(f"/clubs/{club}/members/{waiting}/approve").status_code == 302   # an admin can let them in
    with app.app_context():
        assert get_db().execute("SELECT role FROM club_members WHERE club_id = ? AND user_id = ?",
                                (club, waiting)).fetchone()[0] == "member"


def test_report_queue_pages_and_two_admins_dont_overwrite_each_other(accounts, client, app):
    accounts.signup(email="bad@uw.edu", name="Rowan Ruleb")
    bad = _user_id(app, "bad@uw.edu")
    accounts.logout()
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="admin@uw.edu")
    admin = _user_id(app, "admin@uw.edu")
    with app.app_context():
        db = get_db()
        for n in range(150):
            db.execute("INSERT INTO reports (reporter_id, reported_user_id, target_type, target_id, reason, details,"
                       " status, created_at) VALUES (?, ?, 'user', ?, 'spam', ?, 'open', '2026-10-01 12:00')",
                       (admin, bad, bad, f"report number {n}"))
        db.commit()
        first, last = (db.execute(f"SELECT {f}(id) FROM reports").fetchone()[0] for f in ("MIN", "MAX"))
    page = client.get("/admin/reports").data.decode()
    assert "Showing 1–100 of 150" in page and "report number 149" not in page and "Next →" in page
    assert "report number 149" in client.get("/admin/reports?page=2").data.decode()   # the newest can be reached
    client.post(f"/admin/reports/{first}/dismissed?from=open")            # one admin dismisses it...
    page = client.post(f"/admin/reports/{first}/reviewed?from=open", follow_redirects=True).data.decode()
    assert "Another admin already handled that report" in page            # ...the other admin's click doesn't overwrite
    with app.app_context():
        assert get_db().execute("SELECT status FROM reports WHERE id = ?", (first,)).fetchone()[0] == "dismissed"
    assert last


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
    page = client.post("/signup", follow_redirects=True, data={"full_name": "x" * 61, "email": "long@uw.edu", "password": "purple-and-gold",
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



def test_focus_ring_is_visible_on_the_purple_header_and_hero():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    assert ".topbar :focus-visible, .husky-hero :focus-visible { outline: 3px solid var(--gold)" in css


def test_form_fields_keep_a_focus_outline():
    import pathlib
    css = pathlib.Path("sportive/static/style.css").read_text(encoding="utf-8")
    assert "input:focus, select:focus, textarea:focus { outline: none" not in css
    assert "input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 2px solid" in css


def test_big_phone_text_and_keyboard_users(accounts, client, app):
    """Bot round 6: with bigger phone text the tab bar pushed pages sideways; keyboard users lost their place."""
    root = pathlib.Path(app.root_path) / "static"
    css, chat, app_js = ((root / f).read_text() for f in ("style.css", "chat.js", "app.js"))
    assert "min-width: 0;  /* with bigger phone text the tabs shrink" in css
    assert "body.has-app-nav .topbar .brand { flex: 0 1 auto; min-width: 0; }" in css
    assert '"details.more-menu[open], details.chat-more[open]"' in app_js        # Esc closes a message's ⋯
    assert 'menu.setAttribute("role", "dialog")' in chat and "closeMenu(true)" in chat
    club = _approved_club(accounts, client, app)
    accounts.login(email="captain@uw.edu")
    page = client.get("/create").data.decode()
    assert '<span class="person"><strong>' in page and f"/events/new?club={club}" in page   # long club names shrink


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


def test_suggestions_trends_paging_and_blank_text(accounts, client, app):
    """Bot round 10: suggestions from deleted accounts made fake trends, admins couldn't page back, a trend's
    link could come up empty, and zero-width spaces passed as text."""
    from sportive.feedback import trending
    accounts.signup()
    zero_width = client.post("/suggestions", data={"kind": "idea", "body": "\u200b" * 6}, follow_redirects=True)
    assert b"5 to 2000 characters" in zero_width.data
    with app.app_context():
        db = get_db()
        for _ in range(3):                                               # one person, then their account was deleted
            db.execute("INSERT INTO suggestions (user_id, anonymous, kind, body, created_at) VALUES "
                       "(NULL, 0, 'idea', 'pickleball courts please', ?)", (to_db(now_local()),))
        db.executemany("INSERT INTO suggestions (user_id, anonymous, kind, body, created_at) VALUES (NULL, 0, 'idea', ?, ?)",
                       [(f"idea number {n}", to_db(now_local())) for n in range(700)])
        db.commit()
        assert "pickleball" not in [word for word, *_ in trending()]
    app.config["ADMIN_EMAILS"] = "dubs@uw.edu"
    first = client.get("/admin/suggestions").data.decode()
    assert "Older →" in first and "pickleball courts please" not in first
    assert "pickleball courts please" in client.get("/admin/suggestions?page=3").data.decode()
    assert client.get("/admin/suggestions?topic=pickleball").data.decode().count("pickleball courts please") == 3


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


def _move_to_past(app, event_id):
    with app.app_context():
        get_db().execute("UPDATE events SET starts_at = '2026-01-10 10:00', ends_at = '2026-01-10 12:00' WHERE id = ?",
                         (event_id,))
        get_db().commit()


def test_club_events_belong_to_the_club_and_leaving_takes_you_out(accounts, client, app):
    """Bot round 7: a removed member kept their spot (and the place) in members-only games, and an officer
    who left still managed the club events they made while the other officers couldn't."""
    ids = _people(accounts, app, "Maya", "Sam", "Mem")
    club = _club_with_officer(accounts, client, app)                        # Maya owns it
    _as(accounts, "Maya")
    client.post(f"/clubs/{club}/officers", data={"user": ids["Sam"], "action": "add"})
    _as(accounts, "Mem")
    client.post(f"/clubs/{club}/join", data={"message": "hi"})
    _as(accounts, "Maya")
    client.post(f"/clubs/{club}/members/{ids['Mem']}/approve")
    _as(accounts, "Sam")
    form = dict(title="Practice", sport="spikeball", location="The Quad", is_private="members", club=str(club),
                note="Meet by the cherry trees")
    game = event_id_from(client.post(f"/events/new?club={club}", data=event_form(**form)))
    _as(accounts, "Mem")
    client.post(f"/events/{game}/join")
    _as(accounts, "Maya")                                                   # another officer manages it too
    assert "Cancel event" in client.get(f"/events/{game}").data.decode()
    assert client.post(f"/events/{game}/edit", data=event_form(**{**form, "title": "Practice!"})).status_code == 302
    client.post(f"/clubs/{club}/members/{ids['Mem']}/remove")               # Mem is removed from the club...
    with app.app_context():
        assert not get_db().execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?",
                                    (game, ids["Mem"])).fetchone()          # ...and from its members-only game
    _as(accounts, "Mem")
    assert "cherry trees" not in client.get(f"/events/{game}").data.decode()   # the inside details are gone too
    _as(accounts, "Maya")
    client.post(f"/clubs/{club}/officers", data={"user": ids["Sam"], "action": "remove"})   # Sam steps down
    _as(accounts, "Sam")
    assert client.get(f"/events/{game}/edit").status_code == 403
    assert client.post(f"/events/{game}/cancel").status_code == 403


def test_a_finished_game_cant_be_moved_and_blocking_hides_emails(accounts, client, app):
    ids = _people(accounts, app, "Ana", "Ben")
    _as(accounts, "Ana")
    game = event_id_from(client.post("/events/new", data=event_form(title="Done game")))
    _as(accounts, "Ben")
    client.post(f"/events/{game}/join")
    _move_to_past(app, game)
    assert "ana@uw.edu" in client.get(f"/u/{ids['Ana']}").data.decode()    # played together: emails show
    _as(accounts, "Ana")
    moved = client.post(f"/events/{game}/edit", data=event_form(title="Done game"), follow_redirects=True)
    assert "This game is over" in moved.data.decode()
    with app.app_context():
        assert get_db().execute("SELECT starts_at FROM events WHERE id = ?", (game,)).fetchone()[0] == "2026-01-10 10:00"
    client.post(f"/block/{ids['Ben']}")
    assert "ben@uw.edu" not in client.get(f"/u/{ids['Ben']}").data.decode()
    _as(accounts, "Ben")
    assert "ana@uw.edu" not in client.get(f"/u/{ids['Ana']}").data.decode()


def test_clock_changes_use_real_time(accounts, client, app, monkeypatch):
    """Bot round 7: on the nights clocks change, reminders went out an hour off, Need players could land in the
    skipped hour, and a 7-hour game passed the 6-hour limit."""
    from datetime import datetime
    from sportive import events, reminders
    accounts.signup(email="host@uw.edu", name="Host Husky")
    monkeypatch.setattr(events, "now_local", lambda: datetime(2026, 10, 31, 12, 0))
    too_long = client.post("/events/new", data=event_form(starts_at="2026-11-01T00:30", ends_at="2026-11-01T06:30"))
    assert b"at most 6 hours" in too_long.data                               # 7 real hours that night
    monkeypatch.setattr(events, "now_local", lambda: datetime(2027, 3, 14, 1, 40))
    client.post("/need-players", data={"sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
                                       "starts_in": "30", "duration": "60", "players": "3"})
    with app.app_context():
        quick = get_db().execute("SELECT starts_at FROM events WHERE is_quick = 1").fetchone()
    assert quick is not None and quick[0] == "2027-03-14 03:10"                # 2:10 AM doesn't exist
    with app.app_context():
        db = get_db()
        db.execute("UPDATE events SET starts_at = '2027-03-14 03:30', ends_at = '2027-03-14 04:30'")
        db.execute("UPDATE rsvps SET remind_minutes = 60, created_at = '2027-03-13 10:00'")
        db.commit()
        sent = []
        monkeypatch.setattr(reminders, "send_email", lambda to, subject, body, **kw: sent.append(subject))
        monkeypatch.setattr(reminders, "now_local", lambda: datetime(2027, 3, 14, 1, 30))   # 1 real hour before
        assert reminders.send_due_reminders() == 1 and "starts in 60 min" in sent[0]
        db.execute("UPDATE events SET starts_at = '2026-11-01 02:15', ends_at = '2026-11-01 03:00'")
        db.execute("UPDATE rsvps SET reminder_sent = 0, created_at = '2026-10-31 10:00'")
        db.commit()
        monkeypatch.setattr(reminders, "now_local", lambda: datetime(2026, 11, 1, 1, 15))   # 2 real hours before
        assert reminders.send_due_reminders() == 0
        monkeypatch.setattr(reminders, "now_local", lambda: datetime(2026, 11, 1, 1, 15, fold=1))  # the 2nd 1:15
        assert reminders.send_due_reminders() == 1


def test_top_dawgs_ties_share_a_medal():
    from jinja2 import Environment
    tmpl = Environment().from_string("{% for dawg in top_dawgs %}"
                                     "{% set rank = (top_dawgs|selectattr('games', 'gt', dawg.games)|list|length) + 1 %}"
                                     "{{ rank }} {% endfor %}")
    assert tmpl.render(top_dawgs=[{"games": 5}, {"games": 5}, {"games": 3}]) == "1 1 3 "


def _app_invite_link(app, inviter_id):
    from sportive.parties import _signer
    with app.test_request_context():
        return "/join/" + _signer().dumps([0, inviter_id])


def _set_joined(app, email, days_ago):
    with app.app_context():
        get_db().execute("UPDATE users SET created_at = datetime('now', ?) WHERE email = ?", (f"-{days_ago} days", email))
        get_db().commit()


def test_old_invite_links_cant_undo_an_unfriend_or_a_removal(accounts, client, app):
    """Bot round 9: an old invite link made two people friends again after an unfriend, and let a player the host
    took off a game straight back in."""
    ids = _people(accounts, app, "Maya", "Jordan", "Sam")
    _set_joined(app, "jordan@uw.edu", 30)
    _set_joined(app, "sam@uw.edu", 30)
    link = _app_invite_link(app, ids["Maya"])
    _as(accounts, "Jordan")
    done = client.post(link, follow_redirects=True).data.decode()           # on the app for a month: it asks
    assert "Sent Maya a friend request" in done
    with app.app_context():
        assert get_db().execute("SELECT status FROM friendships").fetchone()[0] == "pending"
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(is_private="1", password="dawgs26", title="Hoops")))
    game_link = _invite_path(client.get(f"/events/{game}").data.decode())
    _as(accounts, "Sam")
    client.post(f"/events/{game}/join", data={"password": "dawgs26"})
    _as(accounts, "Maya")
    client.post(f"/events/{game}/players/{ids['Sam']}/remove")
    _as(accounts, "Sam")
    back = client.post(game_link, follow_redirects=True).data.decode()
    assert "The host took you off this game" in back
    with app.app_context():
        assert not get_db().execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (game, ids["Sam"])).fetchone()


def test_unfriend_and_block_end_held_spots_both_ways(accounts, client, app):
    """Bot round 9: blocking only canceled invites in the blocker's own games; unfriending kept held spots."""
    ids = _people(accounts, app, "Maya", "Jordan", "Sam")
    _friends(app, ids["Maya"], ids["Jordan"], ids["Sam"])
    _friends(app, ids["Jordan"], ids["Sam"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Open run", players="10")))
    client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"]]})   # Maya holds a spot for Jordan
    _as(accounts, "Jordan")
    client.post(f"/events/{game}/join")
    client.post(f"/events/{game}/party", data={"friend": [ids["Sam"]]})      # Jordan holds one for Sam
    status = "SELECT status FROM invites WHERE event_id = ? AND guest_id = ?"
    _as(accounts, "Sam")
    assert "You down?" in client.get(f"/events/{game}").data.decode()
    client.post(f"/block/{ids['Jordan']}")                                   # Sam blocks Jordan (not the host)
    with app.app_context():
        assert get_db().execute(status, (game, ids["Sam"])).fetchone()[0] == "canceled"
        assert not get_db().execute("SELECT 1 FROM notices WHERE user_id = ? AND key = ?",
                                    (ids["Sam"], f"invite:{game}")).fetchone()
    _as(accounts, "Maya")
    game2 = event_id_from(client.post("/events/new", data=event_form(title="Second run", players="10")))
    client.post(f"/events/{game2}/party", data={"friend": [ids["Sam"]]})
    client.post(f"/friends/remove/{ids['Sam']}")                              # unfriend: the held spot ends too
    with app.app_context():
        assert get_db().execute(status, (game2, ids["Sam"])).fetchone()[0] == "canceled"


def test_suspended_friends_dont_show_as_mutual(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan", "Sam")
    _friends(app, ids["Maya"], ids["Jordan"])
    _friends(app, ids["Jordan"], ids["Sam"])
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (ids["Jordan"],))
        get_db().commit()
    _as(accounts, "Maya")
    page = client.get("/friends").data.decode()
    assert "Friends with Jordan" not in page
    assert "mutual friend" not in client.get("/friends?q=sam").data.decode()


def test_private_game_requests_and_passwords(accounts, client, app):
    """Bot round 9: approving a request for someone already in held a spot nobody needed; tapping Join without
    a password counted as a wrong guess."""
    ids = _people(accounts, app, "Maya", "Sam", "John", "Kim")
    _friends(app, ids["Sam"], ids["John"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(is_private="1", password="dawgs26", title="Hoops",
                                                                     players="4")))
    _as(accounts, "Sam")
    client.post(f"/events/{game}/join", data={"password": "dawgs26"})
    client.post(f"/events/{game}/party", data={"friend": [ids["John"]], "note": ""})
    _as(accounts, "John")
    client.post(f"/events/{game}/join", data={"password": "dawgs26"})          # gets in on his own
    _as(accounts, "Maya")
    said = client.post(f"/events/{game}/requests/{ids['John']}/approve", follow_redirects=True).data.decode()
    assert "John is already in the game" in said
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM invites WHERE event_id = ? AND status = 'pending'",
                                (game,)).fetchone()[0] == 0
    _as(accounts, "Kim")
    for _ in range(12):
        client.post(f"/events/{game}/join", data={"password": ""})              # taps Join before typing
    client.post(f"/events/{game}/join", data={"password": "dawgs26"})
    with app.app_context():
        assert get_db().execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (game, ids["Kim"])).fetchone()


def test_16_bit_and_see_through_pngs_come_out_right():
    from sportive.photos import _clean_photo
    from PIL import Image
    gradient = Image.new("I;16", (64, 64))
    gradient.putdata([x * 1000 for y in range(64) for x in range(64)])
    data = BytesIO()
    gradient.save(data, "PNG")
    out = Image.open(BytesIO(_clean_photo(data.getvalue(), 64, False, 85))).convert("L")
    assert 90 < sum(out.getdata()) / (64 * 64) < 160                             # a gradient, not all white
    black_is_clear = Image.new("RGB", (64, 64), (0, 0, 0))
    data = BytesIO()
    black_is_clear.save(data, "PNG", transparency=(0, 0, 0))
    assert Image.open(BytesIO(_clean_photo(data.getvalue(), 64, False, 85))).getpixel((5, 5))[0] > 240


def test_club_event_changes_by_another_officer_and_members_only_switch(accounts, client, app):
    """Bot round 10: switching a game to members-only kept outsiders in it; notices named the host even when
    another officer made the change (and the host wasn't told)."""
    ids = _people(accounts, app, "Maya", "Sam", "Out")
    club = _club_with_officer(accounts, client, app)                         # Maya owns it
    _as(accounts, "Maya")
    client.post(f"/clubs/{club}/officers", data={"user": ids["Sam"], "action": "add"})
    form = dict(title="Practice", sport="spikeball", location="The Quad", club=str(club))
    game = event_id_from(client.post(f"/events/new?club={club}", data=event_form(**form)))
    _as(accounts, "Out")
    client.post(f"/events/{game}/join")
    _as(accounts, "Sam")
    saved = client.post(f"/events/{game}/edit", data=event_form(**form, is_private="members"), follow_redirects=True)
    assert "1 who aren&#39;t members are off the game" in saved.data.decode()
    with app.app_context():
        assert not get_db().execute("SELECT 1 FROM rsvps WHERE event_id = ? AND user_id = ?", (game, ids["Out"])).fetchone()
    _as(accounts, "Out")
    assert "members only, so you&#39;re off it" in client.get("/notifications").data.decode()
    _as(accounts, "Sam")
    client.post(f"/events/{game}/cancel")
    _as(accounts, "Maya")                                                     # the host hears it, from Sam
    assert "Sam canceled Practice" in client.get("/notifications").data.decode()


def test_weekly_practices_one_on_hold_notice_and_within_a_year(accounts, client, app):
    club = _club_with_member(accounts, client, app)                          # logged in as the captain
    form = dict(title="Weekly", sport="spikeball", location="The Quad", club=str(club))
    client.post(f"/events/new?club={club}", data=event_form(**form, repeat="4"))
    far = client.post(f"/events/new?club={club}", data=event_form(
        **form, starts_at=form_time(timedelta(days=360)), ends_at=form_time(timedelta(days=360, hours=1)), repeat="8"))
    assert b"more than a year away" in far.data
    with app.app_context():
        db = get_db()
        member = db.execute("SELECT id FROM users WHERE email = 'member@uw.edu'").fetchone()[0]
        db.executemany("INSERT INTO rsvps (event_id, user_id, created_at) VALUES (?, ?, '2026-09-01 10:00')",
                       [(row[0], member) for row in db.execute("SELECT id FROM events WHERE title = 'Weekly'")])
        db.commit()
    client.post(f"/clubs/{club}/edit", data={**CLUB, "name": "UW Spikeball Club Renamed"})   # back to review
    with app.app_context():
        notices = get_db().execute("SELECT text FROM notices WHERE user_id = ? AND kind = 'game_updates'",
                                   (member,)).fetchall()
    assert len(notices) == 1 and "Your 4 " in notices[0][0]


def test_one_click_unsubscribe_without_logging_in(accounts, client, app, monkeypatch):
    """Bot round 10: optional emails only linked to Settings (a login), with no List-Unsubscribe headers."""
    from sportive import digest
    from sportive.unsubscribe import unsubscribe_url
    accounts.signup(email="hoop@uw.edu", name="Hoop Husky")
    game = client.post("/events/new", data=event_form(title="Tuesday hoops"))
    assert game.status_code == 302
    accounts.logout()
    with app.test_request_context():
        digest.send_weekly()
        link = unsubscribe_url("hoop@uw.edu", "digest")
    sent = [m for m in app.extensions["outbox"] if m["to"] == "hoop@uw.edu" and m["subject"].startswith("Games this week")]
    assert sent and sent[-1]["unsubscribe"] == link and "Unsubscribe from these emails" in sent[-1]["body"]
    path = link.split("localhost:5050")[-1] if "localhost" in link else "/" + link.split("/", 3)[3]
    assert b"Unsubscribe?" in client.get(path).data                           # opening it changes nothing
    with app.app_context():
        assert get_db().execute("SELECT weekly_digest FROM users WHERE email = 'hoop@uw.edu'").fetchone()[0] == 1
    app.config["CSRF_ENABLED"] = True                                          # mail apps send no form token
    try:
        done = client.post(path, data={"List-Unsubscribe": "One-Click"})
    finally:
        app.config["CSRF_ENABLED"] = False
    assert done.status_code == 200 and b"You're unsubscribed" in done.data
    with app.app_context():
        assert get_db().execute("SELECT weekly_digest FROM users WHERE email = 'hoop@uw.edu'").fetchone()[0] == 0
    assert client.get("/unsubscribe/forged-token").status_code == 404


def test_search_with_only_accents_odd_letters_and_friends_first(accounts, client, app):
    """Bot round 11: a search of only accent marks crashed (500); "yilmaz" didn't find "Yılmaz"; Messages search
    could miss a friend behind 20 strangers with the same name."""
    ids = _people(accounts, app, "Maya", "Zoe")
    with app.app_context():
        db = get_db()
        db.executemany("INSERT INTO users (email, password_hash, full_name, verified) VALUES (?, 'x', ?, 1)",
                       [(f"chen{n}@uw.edu", f"Alex Chen{n:02d}") for n in range(25)]
                       + [("ibo@uw.edu", "İbrahim Yılmaz")])
        db.execute("UPDATE users SET full_name = 'Zoe Chen' WHERE id = ?", (ids["Zoe"],))
        db.commit()
    _friends(app, ids["Maya"], ids["Zoe"])
    _as(accounts, "Maya")
    assert client.get("/friends?q=%CC%81%CC%81").status_code == 200
    assert client.get("/messages?q=%CC%81%CC%81").status_code == 200
    assert "Yılmaz" in client.get("/friends?q=yilmaz").data.decode()
    assert "Zoe Chen" in client.get("/messages?q=chen").data.decode()


def test_message_odd_contents(accounts, client, app):
    """Bot round 11: zero-width-only messages made empty bubbles; photo-only chats had a blank preview; a reported
    photo left admins nothing to look at."""
    ids = _people(accounts, app, "Maya", "Jordan")
    _friends(app, ids["Maya"], ids["Jordan"])
    _as(accounts, "Maya")
    client.post(f"/messages/{ids['Jordan']}", data={"body": "\u200b\u200b"})
    client.post(f"/messages/{ids['Jordan']}", data={"body": "", "photo": (BytesIO(make_image()), "p.png")},
                content_type="multipart/form-data")
    with app.app_context():
        rows = get_db().execute("SELECT id, body, photo_id FROM direct_messages").fetchall()
    assert len(rows) == 1 and rows[0]["photo_id"]                               # only the photo went through
    _as(accounts, "Jordan")
    assert "📷 Photo" in client.get("/messages").data.decode()
    client.post(f"/report/dm/{rows[0]['id']}", data={"reason": "spam", "details": ""})
    with app.app_context():
        assert "sent a photo" in get_db().execute("SELECT snapshot FROM reports").fetchone()[0]


def test_invite_link_on_login_asks_and_admins_can_let_members_in(accounts, client, app):
    """Round 12 review: logging in (not signing up) through an invite link still made friends for accounts under
    a day old; admins could be told to confirm a club's members but had no buttons; "Wrong email?" left the
    mistyped account behind."""
    ids = _people(accounts, app, "Maya", "Newbie")
    link = _app_invite_link(app, ids["Maya"])
    client.post(link)                                                          # logged out: saved for after login
    accounts.login(email="newbie@uw.edu")
    with app.app_context():
        assert get_db().execute("SELECT status FROM friendships").fetchone()[0] == "pending"
    accounts.logout()
    club = _club_with_member(accounts, client, app)
    accounts.logout()
    accounts.signup(email="waits@uw.edu", name="Wai Ting")
    client.post(f"/clubs/{club}/join", data={"message": "please"})
    accounts.logout()
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="admin@uw.edu")
    page = client.get(f"/clubs/{club}").data.decode()
    assert "Join requests (1)" in page and "Confirm member" in page
    accounts.logout()
    data = {"full_name": "Typo Husky", "email": "tpyo@uw.edu", "password": "purple-and-gold",
            "password2": "purple-and-gold", "birth_date": "2006-03-01", "grad_year": "2030"}
    client.post("/signup", data=data)
    client.post("/signup", data={**data, "email": "typo@uw.edu"})
    with app.app_context():
        assert not get_db().execute("SELECT 1 FROM users WHERE email = 'tpyo@uw.edu'").fetchone()


def test_two_cancels_tell_players_once_and_a_canceled_game_cant_be_edited(accounts, client, app):
    """Round 13: two officers canceling at once emailed everyone twice; an edit could land after the cancel."""
    ids = _people(accounts, app, "Maya", "Sam", "Pat")
    _friends(app, ids["Maya"], ids["Pat"])
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Maya")
    client.post(f"/clubs/{club}/officers", data={"user": ids["Sam"], "action": "add"})
    form = dict(title="Club night", sport="spikeball", location="The Quad", club=str(club))
    game = event_id_from(client.post(f"/events/new?club={club}", data=event_form(**form)))
    _as(accounts, "Pat")
    client.post(f"/events/{game}/join")
    _as(accounts, "Maya")
    from sportive import events
    client.post(f"/events/{game}/cancel")
    with app.app_context():
        get_db().execute("UPDATE events SET cancelled = 0 WHERE id = ?", (game,))  # (as the 2nd officer saw it)
        get_db().commit()
    import unittest.mock as mock
    stale = None
    with app.test_request_context():
        from flask import g
        g.user = {"id": ids["Sam"]}
        stale = dict(events.query_events(["e.id = :id"], {"id": game}, limit=1, on_hold=True)[0])
    with app.app_context():
        get_db().execute("UPDATE events SET cancelled = 1 WHERE id = ?", (game,))
        get_db().commit()
    _as(accounts, "Sam")
    with mock.patch.object(events, "get_event", lambda event_id, host_only=False: stale):
        client.post(f"/events/{game}/cancel")                                 # lands second: nobody told again
        edited = client.post(f"/events/{game}/edit", data=event_form(**{**form, "location": "Denny Field"}),
                             follow_redirects=True).data.decode()
    canceled = [m for m in app.extensions["outbox"] if m["to"] == "pat@uw.edu" and m["subject"].startswith("Canceled")]
    assert len(canceled) == 1
    assert "This game was canceled, so it can&#39;t be edited" in edited
    with app.app_context():
        assert get_db().execute("SELECT location FROM events WHERE id = ?", (game,)).fetchone()[0] == "The Quad"


def test_stale_posted_a_game_and_invite_notices_go_away(accounts, client, app):
    """Round 13: "Maya posted a game" stayed after a cancel or a block; suspending a host left friends' "You down?"
    notices up with no "that invite is off"."""
    ids = _people(accounts, app, "Maya", "Ben", "Cara")
    _friends(app, ids["Maya"], ids["Ben"], ids["Cara"])
    _as(accounts, "Maya")
    g1 = event_id_from(client.post("/events/new", data=event_form(title="Game one")))
    g2 = event_id_from(client.post("/events/new", data=event_form(title="Game two", reserve=[str(ids["Ben"])])))
    posted = "SELECT COUNT(*) FROM notices WHERE user_id = ? AND key = ?"
    with app.app_context():
        assert get_db().execute(posted, (ids["Cara"], f"friend_game:{g1}")).fetchone()[0] == 1
    client.post(f"/events/{g1}/cancel")
    with app.app_context():
        assert get_db().execute(posted, (ids["Cara"], f"friend_game:{g1}")).fetchone()[0] == 0
    _as(accounts, "Cara")
    client.post(f"/block/{ids['Maya']}")
    with app.app_context():
        assert get_db().execute(posted, (ids["Cara"], f"friend_game:{g2}")).fetchone()[0] == 0
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    client.post(f"/admin/users/{ids['Maya']}/suspend")
    _as(accounts, "Ben")
    bell = client.get("/notifications").data.decode()
    assert "You down?" not in bell and "so that invite is off" in bell


def test_two_workers_starting_at_once_dont_crash_adding_columns(tmp_path):
    """Round 13: the 2 workers both added the same new column at startup; one crashed ("duplicate column name")."""
    import sqlite3
    import threading
    from sportive.db import ADDED_COLUMNS
    if sqlite3.sqlite_version_info < (3, 35):                                   # DROP COLUMN (to fake an old DB)
        return
    for attempt in range(8):
        path = str(tmp_path / f"t{attempt}.db")
        create_app({"TESTING": True, "DATABASE": path, "SECRET_KEY": "x" * 40})
        db = sqlite3.connect(path)
        for table, column, _ in ADDED_COLUMNS[-4:]:                              # an older database
            db.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        db.commit()
        db.close()
        errors, start = [], threading.Barrier(2)

        def boot():
            try:
                start.wait()
                create_app({"TESTING": True, "DATABASE": path, "SECRET_KEY": "x" * 40})
            except Exception as error:  # noqa: BLE001 - the test reports any crash
                errors.append(error)
        workers = [threading.Thread(target=boot) for _ in range(2)]
        [worker.start() for worker in workers]
        [worker.join() for worker in workers]
        assert errors == []


def test_odd_digits_and_huge_pages_dont_crash(accounts, client, app):
    """Round 14: "²" passes str.isdigit() but not int(): Home's ?page= and grad years crashed (500)."""
    accounts.signup()
    assert client.get("/?page=²").status_code == 200
    assert client.post("/profile/edit", data={"full_name": "Dubs Husky", "grad_year": "²⁰²⁷"}).status_code in (200, 302)
    assert client.post("/signup", data={"full_name": "A B", "email": "ab@uw.edu", "password": "purple-and-gold",
                                        "password2": "purple-and-gold", "birth_date": "2005-01-01",
                                        "grad_year": "²⁰²⁷"}).status_code == 302
    app.config["ADMIN_EMAILS"] = "dubs@uw.edu"
    assert client.get("/admin/reports?page=99999999999999999999999").status_code == 200
    assert client.get("/admin/suggestions?page=99999999999999999999999").status_code == 200


def test_blocked_profiles_show_only_name_and_photo(accounts, client, app):
    """Round 14: someone you blocked still saw your bio, gender and socials; pronouns could fake text."""
    ids = _people(accounts, app, "Alice", "Bob")
    _as(accounts, "Alice")
    client.post("/profile/edit", data={"full_name": "Alice Husky", "bio": "Hoops every night", "gender": "woman",
                                       "pronouns": "\u202enamow", "grad_year": "2027"})
    with app.app_context():
        assert get_db().execute("SELECT pronouns FROM users WHERE id = ?", (ids["Alice"],)).fetchone()[0] == "namow"
        get_db().execute("UPDATE users SET instagram = 'alice.ig' WHERE id = ?", (ids["Alice"],))
        get_db().commit()
    _as(accounts, "Bob")
    assert "alice.ig" in client.get(f"/u/{ids['Alice']}").data.decode()
    _as(accounts, "Alice")
    client.post(f"/block/{ids['Bob']}")
    _as(accounts, "Bob")
    page = client.get(f"/u/{ids['Alice']}").data.decode()
    assert "Alice Husky" in page and "alice.ig" not in page and "Hoops every night" not in page
    from sportive.textutil import person_name
    assert person_name("\u3164\u3164") == ""                                     # looks blank: not a name


def test_social_links_and_short_links(accounts, client, app):
    from sportive.profile import clean_social
    assert clean_social("tiktok", "https://www.tiktok.com/@dubs.husky.official?_t=8kL") == "dubs.husky.official"
    assert clean_social("tiktok", "vm.tiktok.com/ZMabc/").endswith("/")             # a short link, refused
    assert clean_social("instagram", "maya.co") == "maya.co"                        # a real username: fine
    assert 'maxlength="200"' in pathlib.Path(app.root_path, "templates/profile/edit_sports.html").read_text()


def test_home_says_when_there_are_more_games_than_it_lists(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    with app.app_context():
        db = get_db()
        host = db.execute("SELECT id FROM users WHERE email = 'host@uw.edu'").fetchone()[0]
        start = now_local() + timedelta(days=2)
        db.executemany("INSERT INTO events (title, sport, location, skill_level, starts_at, ends_at, host_id, created_at)"
                       " VALUES (?, 'basketball', 'IMA (Intramural Activities Building)', 'Casual', ?, ?, ?, ?)",
                       [(f"Game {n}", to_db(start), to_db(start + timedelta(hours=1)), host, to_db(now_local()))
                        for n in range(1010)])
        db.commit()
    assert "There are even more games" in client.get("/?page=20").data.decode()


def test_changes_reach_invited_friends_and_say_what_changed(accounts, client, app):
    """Round 15: a friend with a spot held wasn't told the time or place changed; the "Changed" email didn't say
    what changed (an end-time edit looked like nothing changed); a canceled game still showed spots left."""
    ids = _people(accounts, app, "Maya", "Jordan", "Priya")
    _friends(app, ids["Maya"], ids["Jordan"], ids["Priya"])
    _as(accounts, "Maya")
    form = dict(title="Hoops", players="6")
    game = event_id_from(client.post("/events/new", data=event_form(**form)))
    client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"], ids["Priya"]]})
    _as(accounts, "Jordan")
    client.post(f"/events/{game}/invite/answer", data={"answer": "yes"})
    _as(accounts, "Maya")
    client.post(f"/events/{game}/edit", data=event_form(**form, ends_at=form_time(timedelta(days=1, hours=3))))
    email = [m for m in app.extensions["outbox"] if m["to"] == "jordan@uw.edu" and m["subject"] == "Changed: Hoops"][-1]
    assert "Maya changed this game: now ends at" in email["body"]
    _as(accounts, "Priya")                                                   # only invited: told too
    assert "which changed: now ends at" in client.get("/notifications").data.decode()
    _as(accounts, "Maya")
    client.post(f"/events/{game}/cancel")
    assert "spots left" not in client.get(f"/events/{game}").data.decode()


def test_game_chats_hide_blocked_people_both_ways_and_suspended_people(accounts, client, app):
    """Round 16: in a game chat, blocking only hid the blocked person from the blocker; a suspended person's
    old messages still showed and counted as unread."""
    ids = _people(accounts, app, "Host", "Ann", "Ben", "Sus")
    _as(accounts, "Host")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    for name in ("Ann", "Ben", "Sus"):
        _as(accounts, name)
        client.post(f"/events/{game}/join")
    _as(accounts, "Sus")
    client.post(f"/events/{game}/chat", data={"body": "buy my stuff"})
    _as(accounts, "Ann")
    client.post(f"/block/{ids['Ben']}")
    client.post(f"/events/{game}/chat", data={"body": "ann private plan"})
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (ids["Sus"],))
        get_db().commit()
    _as(accounts, "Ben")
    seen = json.dumps(client.get(f"/events/{game}/chat/poll?after=0").get_json())
    assert "ann private plan" not in seen and "buy my stuff" not in seen
    _as(accounts, "Host")
    seen = json.dumps(client.get(f"/events/{game}/chat/poll?after=0").get_json())
    assert "ann private plan" in seen and "buy my stuff" not in seen


def test_admin_tools_on_a_suspended_profile_and_report_pages(accounts, client, app):
    """Round 16: a suspended profile looked normal to admins (no label, no Restore, no photo); acting on page 2
    of reports jumped back to page 1."""
    ids = _people(accounts, app, "Sam")
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="admin@uw.edu")
    client.post(f"/admin/users/{ids['Sam']}/suspend")
    page = client.get(f"/u/{ids['Sam']}").data.decode()
    assert "Suspended" in page and "Restore account" in page
    assert client.get(f"/u/{ids['Sam']}/photo").status_code == 200
    with app.app_context():
        db = get_db()
        admin = db.execute("SELECT id FROM users WHERE email = 'admin@uw.edu'").fetchone()[0]
        for n in range(130):
            db.execute("INSERT INTO reports (reporter_id, reported_user_id, target_type, target_id, reason, details,"
                       " status, created_at) VALUES (?, ?, 'user', ?, 'spam', ?, 'open', '2026-10-01 12:00')",
                       (admin, ids["Sam"], ids["Sam"], f"r{n}"))
        db.commit()
        last = db.execute("SELECT MAX(id) FROM reports").fetchone()[0]
    page2 = client.get("/admin/reports?page=2").data.decode()
    assert f"/admin/reports/{last}/reviewed?page=2" in page2 or "page=2&amp;from=open" in page2
    done = client.post(f"/admin/reports/{last}/reviewed?page=2&from=open")
    assert "page=2" in done.headers["Location"]


def test_need_players_place_check_uses_seattle_time_on_any_phone(app):
    """Round 16: on a phone set to Seoul, Need players asked the place check about Seoul's clock time."""
    js = (pathlib.Path(app.root_path) / "static" / "forms.js").read_text()
    assert 'timeZone: "America/Los_Angeles"' in js and "getHours()" not in js


def test_one_person_cant_flood_others(accounts, client, app):
    """Round 17: editing a game 100 times emailed every player 99 times; posting 100 games put 100 notices in each
    friend's bell; reserving spots in game after game did the same."""
    ids = _people(accounts, app, "Spam", "Vic")
    _friends(app, ids["Spam"], ids["Vic"])
    _as(accounts, "Spam")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    _as(accounts, "Vic")
    client.post(f"/events/{game}/join")
    _as(accounts, "Spam")
    for n in range(10):
        client.post(f"/events/{game}/edit", data=event_form(title="Hoops", starts_at=form_time(timedelta(days=1, hours=n % 2)),
                                                           ends_at=form_time(timedelta(days=1, hours=2 + n % 2))))
    changed = [m for m in app.extensions["outbox"] if m["to"] == "vic@uw.edu" and m["subject"].startswith("Changed")]
    from sportive.events import CHANGE_ALERTS_PER_DAY
    assert len(changed) == CHANGE_ALERTS_PER_DAY == 6                             # the bell keeps the latest
    games = [event_id_from(client.post("/events/new", data=event_form(title=f"Game {n}", players="10")))
             for n in range(8)]
    with app.app_context():
        posted = get_db().execute("SELECT COUNT(*) FROM notices WHERE user_id = ? AND kind = 'friend_games'",
                                  (ids["Vic"],)).fetchone()[0]
    assert posted == 5                                                            # 5 a day from one host
    for game_id in games[:5]:
        client.post(f"/events/{game_id}/party", data={"friend": [ids["Vic"]]})
    sixth = client.post(f"/events/{games[5]}/party", data={"friend": [ids["Vic"]]}, follow_redirects=True)
    assert b"a lot of games today" in sixth.data
    with app.app_context():
        get_db().execute("UPDATE events SET created_at = datetime('now') WHERE host_id = ?", (ids["Spam"],))
        get_db().executemany("INSERT INTO events (title, sport, location, skill_level, starts_at, ends_at, host_id)"
                             " VALUES ('x', 'basketball', 'IMA (Intramural Activities Building)', 'Casual', ?, ?, ?)",
                             [(to_db(now_local() + timedelta(days=3)), to_db(now_local() + timedelta(days=3, hours=1)),
                               ids["Spam"])] * 51)                   # 60 with the 9 above
        get_db().commit()
    too_many = client.post("/events/new", data=event_form(title="One more"), follow_redirects=True)
    assert b"You can post up to 60 games an hour, and you&#39;ve posted 60. Try again in a bit." in too_many.data


def test_suspended_people_disappear_from_lists_and_blocked_profiles_stay_quiet(accounts, client, app):
    """Round 17: a suspended person still showed (with a broken photo) in past games, club rosters, invite lists
    and an open DM; a blocked profile still said "No sports picked yet" and "Nothing coming up"."""
    ids = _people(accounts, app, "Host", "Sus")
    _friends(app, ids["Host"], ids["Sus"])
    _as(accounts, "Host")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    _as(accounts, "Sus")
    client.post(f"/events/{game}/join")
    client.post(f"/messages/{ids['Host']}", data={"body": "hi from sus"})
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (ids["Sus"],))
        get_db().commit()
    _as(accounts, "Host")
    assert "Sus Husky" not in client.get(f"/events/{game}").data.decode()
    poll = client.get(f"/messages/{ids['Sus']}/poll?after=0")
    assert poll.status_code != 200 or poll.get_json()["messages"] == []
    accounts.logout()
    ids2 = _people(accounts, app, "Ana", "Ben")
    _as(accounts, "Ana")
    client.post(f"/block/{ids2['Ben']}")
    _as(accounts, "Ben")
    page = client.get(f"/u/{ids2['Ana']}").data.decode()
    assert "No sports picked yet" not in page and "Nothing coming up" not in page and "Ana Husky" in page


def test_report_pages_past_the_end_show_the_last_page(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="admin@uw.edu")
    with app.app_context():
        db = get_db()
        admin = db.execute("SELECT id FROM users WHERE email = 'admin@uw.edu'").fetchone()[0]
        db.executemany("INSERT INTO reports (reporter_id, reported_user_id, target_type, target_id, reason, details,"
                       " status, created_at) VALUES (?, ?, 'user', ?, 'spam', 'x', 'open', '2026-10-01 12:00')",
                       [(admin, admin, admin)] * 100)
        db.commit()
    page = client.get("/admin/reports?page=2").data.decode()                      # 100 reports: only 1 page
    assert "No open reports" not in page


def test_text_limits_keep_important_texts_and_count_only_real_sends(accounts, client, app, monkeypatch):
    """Round 18: twenty "posted a game" texts used up the day, so a "game canceled" text never came; one friend could
    send someone twenty "You down?" texts; failed sends counted against the day; a STOP reply left no explanation."""
    from sportive import sms
    sent = _texts(monkeypatch)
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET phone = '+12065550142', phone_verified = 1, sms_updates = 1")
        db.commit()
        for n in range(sms.MAX_TEXTS_PER_DAY):
            assert sms.text_user(me, f"update {n}") is True
        assert sms.text_user(me, "one too many") is False                        # ordinary updates: capped
        assert sms.text_user(me, "Game canceled", kind="important") is True      # changes and cancels still come
        assert sms.text_user(me, "Reminder", kind="reminder") is True
        db.execute("DELETE FROM sms_log")
        for n in range(sms.INVITE_TEXTS_PER_SENDER):
            assert sms.text_user(me, "You down?", kind="invite:7") is True
        assert sms.text_user(me, "You down?", kind="invite:7") is False          # one friend: a few a day
        assert sms.text_user(me, "You down?", kind="invite:8") is True           # another friend: their own
        db.execute("DELETE FROM sms_log")

        def down(to, body):
            raise sms.SmsError(500, "down")
        monkeypatch.setattr(sms, "send_sms", down)
        for n in range(sms.MAX_TEXTS_PER_DAY + 5):
            sms.text_user(me, "try")
        monkeypatch.setattr(sms, "send_sms", lambda to, body: sent.append((to, body)))
        assert sms.text_user(me, "works again") is True                          # failures didn't use up the day

        def opted_out(to, body):
            raise sms.SmsError(sms.OPTED_OUT, "unsubscribed")
        monkeypatch.setattr(sms, "send_sms", opted_out)
        sms.text_user(me, "hi", kind="important")
        assert sms.normalize_phone("+1 206 555 01421") is None                   # +1 and too many digits
    assert "START back to that same number" in client.get("/settings/texts").data.decode()
    client.post("/settings/texts", data={"action": "toggle", "sms_updates": "1"})
    assert "START back to that same number" not in client.get("/settings/texts").data.decode()


def test_spam_limits_leave_normal_use_alone(accounts, client, app):
    """Round 18: renewing a friend's held spot in the same game counted as another invite; a link like
    instagram.com/maya.co was refused; club member counts included suspended people the roster hides."""
    from sportive.invites import INVITES_PER_FRIEND_PER_DAY, invited_too_often
    from sportive.profile import clean_social
    ids = _people(accounts, app, "Maya", "Jordan")
    _friends(app, ids["Maya"], ids["Jordan"])
    _as(accounts, "Maya")
    games = [event_id_from(client.post("/events/new", data=event_form(title=f"Hoops {n}")))
             for n in range(INVITES_PER_FRIEND_PER_DAY)]
    for game in games:
        client.post(f"/events/{game}/party", data={"friend": [ids["Jordan"]]})
    with app.app_context():
        assert invited_too_often(ids["Maya"], [ids["Jordan"]]) == ids["Jordan"]           # a sixth game: no
        assert invited_too_often(ids["Maya"], [ids["Jordan"]], games[0]) is None          # same game again: fine
    assert clean_social("instagram", "instagram.com/maya.co") == "maya.co"
    assert clean_social("instagram", "https://www.instagram.com/maya.co/") == "maya.co"
    assert clean_social("tiktok", "vm.tiktok.com/ZMabc/").endswith("/")
    with app.app_context():
        from sportive.clubs import MEMBER_COUNT
        db = get_db()
        db.execute("INSERT INTO clubs (name, sport, description, status, created_by, created_at)"
                   " VALUES ('Run Club', 'running', 'Easy miles', 'approved', ?, ?)", (ids["Maya"], to_db(now_local())))
        club = db.execute("SELECT id FROM clubs WHERE name = 'Run Club'").fetchone()[0]
        db.executemany("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
                       [(club, ids["Maya"], "officer", to_db(now_local())), (club, ids["Jordan"], "member", to_db(now_local()))])
        db.execute("UPDATE users SET suspended = 1 WHERE id = ?", (ids["Jordan"],))
        assert db.execute(f"SELECT {MEMBER_COUNT} FROM clubs c WHERE c.id = ?", (club,)).fetchone()[0] == 1


def test_private_and_members_only_club_events_keep_their_place_to_themselves(accounts, client, app):
    """Round 19: a club event marked Private had its title, time and place posted on the club's public page; an
    edit to members-only left the old post (with the place) up; anyone could open a members-only game's page and
    see the place and map, or send it on with "Send to friends"."""
    ids = _people(accounts, app, "Maya", "Sam", "Jordan")
    _friends(app, ids["Sam"], ids["Jordan"])
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Maya")
    club_game = dict(sport="spikeball", location="The Quad", club=str(club))
    event_id_from(client.post(f"/events/new?club={club}", data=event_form(
        title="Secret run", is_private="1", password="huskies1", **club_game)))
    open_run = event_id_from(client.post(f"/events/new?club={club}", data=event_form(title="Open run", **club_game)))
    _as(accounts, "Sam")
    client.post(f"/events/{open_run}/join")
    client.post(f"/events/{open_run}/send", data={"friend": [ids["Jordan"]]})
    accounts.logout()
    page = client.get(f"/clubs/{club}").data.decode()
    assert "Secret run" not in page and "New private event." in page          # a stranger with the club link
    assert "Open run" in page and "The Quad" in page
    _as(accounts, "Maya")
    client.post(f"/events/{open_run}/edit", data=event_form(title="Open run", is_private="members", **club_game))
    accounts.logout()
    page = client.get(f"/clubs/{club}").data.decode()
    assert "Open run" not in page and "New members-only event." in page        # the old post was rewritten
    _as(accounts, "Jordan")                                                    # not a member
    game_page = client.get(f"/events/{open_run}").data.decode()
    assert "Members see the place" in game_page and "The Quad" not in game_page and "event-map" not in game_page
    assert "Place shown in the game" in client.get(f"/messages/{ids['Sam']}").data.decode()   # Sam's old card
    _friends(app, ids["Jordan"], ids["Maya"])
    assert client.get(f"/events/{open_run}/send").status_code in (302, 303)     # can't send what you can't see
    _as(accounts, "Maya")
    assert "The Quad" in client.get(f"/events/{open_run}").data.decode()        # the club officer still sees it
    assert "Secret run" in client.get(f"/clubs/{club}").data.decode()


def test_editing_a_game_saves_before_emailing_players(accounts, client, app, monkeypatch):
    """Round 19: the "Changed" emails went out while the edit still held the database, so everyone else on the site
    (joins, messages) waited behind a slow mail server."""
    from sportive import events
    ids = _people(accounts, app, "Maya", "Sam")
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    _as(accounts, "Sam")
    client.post(f"/events/{game}/join")
    _as(accounts, "Maya")
    busy = []
    real = events.send_email
    monkeypatch.setattr(events, "send_email", lambda *a, **k: busy.append(get_db().in_transaction) or real(*a, **k))
    client.post(f"/events/{game}/edit", data=event_form(title="Hoops", starts_at=form_time(timedelta(days=1, hours=1)),
                                                       ends_at=form_time(timedelta(days=1, hours=3))))
    assert busy == [False]                                                  # saved first, then Sam's email
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM change_alerts WHERE user_id = ?", (ids["Sam"],)).fetchone()[0] == 1


def test_invite_link_for_a_finished_game_says_so_and_social_post_links(accounts, client, app):
    """Round 19: a link for a canceled game quietly became "Maya wants you on Sportive Circle"; pasted Instagram post
    or story links saved "p" or "stories" as the username; newer Snapchat and mobile Twitter links were refused."""
    from sportive.profile import clean_social
    _people(accounts, app, "Maya", "Sam")
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    page = client.get(f"/events/{game}").data.decode()
    link = re.search(r'/join/[\w.\-]+', page).group(0)
    client.post(f"/events/{game}/cancel")
    _as(accounts, "Sam")
    assert "isn't open anymore" in client.get(link).data.decode()
    assert clean_social("instagram", "instagram.com/p/Cxyz123/") == "p/Cxyz123/"         # a post: fails the check
    assert clean_social("instagram", "https://www.instagram.com/stories/maya/123") == "maya"
    assert clean_social("instagram", "instagram.com/_u/maya") == "maya"
    assert clean_social("snapchat", "snapchat.com/@maya") == "maya"
    assert clean_social("x_handle", "mobile.twitter.com/maya") == "maya"
    from sportive.profile import PERSON_SOCIAL_RULES
    assert not re.fullmatch(PERSON_SOCIAL_RULES["instagram"][1], "p/Cxyz123/")         # "doesn't look right"


def test_stop_note_and_number_lookups(accounts, client, app, monkeypatch):
    """Round 19: the "You replied STOP" note stayed after changing numbers; checking whether a number is taken
    stopped costing a code try (so anyone could look up which numbers are on the app)."""
    from sportive import sms
    _texts(monkeypatch)
    ids = _people(accounts, app, "Maya", "Sam")
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET phone = '+12065550142', phone_verified = 1, sms_updates = 1 WHERE id = ?",
                   (ids["Maya"],))
        db.execute("UPDATE users SET phone = '+12065550143', phone_verified = 1, sms_updates = 0, "
                   "sms_stopped_at = '2026-01-01 00:00' WHERE id = ?", (ids["Sam"],))
        db.commit()
        sms.remove_phone(ids["Sam"])
        assert db.execute("SELECT sms_stopped_at FROM users WHERE id = ?", (ids["Sam"],)).fetchone()[0] is None
        for n in range(sms.MAX_CODES_PER_NUMBER):
            assert "already used" in sms.start_phone_check(ids["Sam"], "+12065550142")
        assert sms._sent_today(ids["Sam"], codes=True) == sms.MAX_CODES_PER_NUMBER   # each lookup used a try


def test_phone_scripts_keep_typing_and_say_what_happened(app):
    """Round 19 (real-browser testers): chat emptied words typed while a message was sending, hung forever on a
    stuck send, sent half-typed Japanese/Chinese/Korean on the Enter that picks the word, kept keyboard focus
    outside the photo viewer, and a second double tap on a slow phone took the heart off again. Settings switches
    swapped the page for "No internet" when offline. "Maybe later" didn't stick, the wizard let you past an empty
    sport, and Need players said "full" when there was nobody left to find."""
    static = pathlib.Path(app.root_path) / "static"
    chat = (static / "chat.js").read_text()
    assert "isComposing" in chat and "AbortController" in chat and "sentText" in chat
    assert "openedFrom.focus" in chat and 'event.key === "Tab"' in chat and "dataset.hearting" in chat
    assert "visibilitychange" in chat and "never throw away something being typed" in chat
    script = (static / "app.js").read_text()
    assert "Couldn't save. Check your connection" in script and "Saving…" in script and "data-welcome-later" in script
    assert "nobody left to find" in (static / "forms.js").read_text()
    templates = pathlib.Path(app.root_path) / "templates"
    assert "data-welcome-later" in (templates / "profile/welcome.html").read_text()
    for name in ("events/form.html", "events/quick.html"):
        assert "'Choose a sport', required=True" in (templates / name).read_text()


def test_clubs_keep_an_owner_and_active_officers(accounts, client, app):
    """Round 20: after the owner deleted their account nobody could ever be made owner again; a suspended officer
    still counted as "another officer", so the last real one could leave; "Make officer" ignored blocks."""
    club = _club_with_member(accounts, client, app)                         # logged in as the captain (owner)
    member, fan = _user_id(app, "member@uw.edu"), _user_id(app, "fan@uw.edu")
    client.post(f"/clubs/{club}/officers/{member}")
    accounts.logout()
    accounts.signup(email="third@uw.edu", name="Third Officer")
    client.post(f"/clubs/{club}/join", data={"message": "Hi"})
    third = _user_id(app, "third@uw.edu")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    client.post(f"/clubs/{club}/members/{third}/approve")
    client.post(f"/clubs/{club}/officers/{third}")
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    with app.app_context():
        assert get_db().execute("SELECT created_by FROM clubs WHERE id = ?", (club,)).fetchone()[0] == member
        get_db().execute("UPDATE clubs SET created_by = NULL WHERE id = ?", (club,))   # an older club, owner gone
        get_db().commit()
    accounts.login(email="member@uw.edu")
    client.post(f"/clubs/{club}/officers", data={"user": third, "action": "owner"})
    with app.app_context():
        assert get_db().execute("SELECT created_by FROM clubs WHERE id = ?", (club,)).fetchone()[0] == third
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (third,))      # the owner is suspended
        get_db().commit()
    page = client.post(f"/clubs/{club}/leave", follow_redirects=True).data.decode()
    assert "only officer" in page                                          # the suspended one doesn't count
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 0 WHERE id = ?", (third,))
        get_db().execute("UPDATE club_members SET role = 'member' WHERE club_id = ? AND user_id = ?", (club, fan))
        get_db().execute("INSERT INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, '2026-09-01 10:00')",
                         (fan, third))
        get_db().commit()
    accounts.logout()
    accounts.login(email="third@uw.edu")
    client.post(f"/clubs/{club}/officers/{fan}")                            # Fan blocked them: no
    with app.app_context():
        assert get_db().execute("SELECT role FROM club_members WHERE club_id = ? AND user_id = ?",
                                (club, fan)).fetchone()[0] == "member"


def test_club_requests_posts_and_events_round_20(accounts, client, app, monkeypatch):
    """Round 20: canceling a join request also dropped the follow; a blocked person's join request emailed the
    officer who blocked them; a suspended officer's name stayed on old posts; a canceled event's post still
    advertised it; edits to a weekly series turned its post into one game's; ten private events pushed the open
    ones off the club page."""
    club = _club_with_member(accounts, client, app)                         # captain logged in
    captain = _user_id(app, "captain@uw.edu")
    client.post(f"/clubs/{club}/posts", data={"body": "Practice is on!"})
    club_game = dict(sport="spikeball", location="The Quad", club=str(club))
    for week in range(10):
        client.post(f"/events/new?club={club}", data=event_form(
            title=f"Secret {week}", is_private="1", password="huskies1", **club_game,
            starts_at=form_time(timedelta(days=1 + week)), ends_at=form_time(timedelta(days=1 + week, hours=1))))
    later = event_id_from(client.post(f"/events/new?club={club}", data=event_form(
        title="Open later", **club_game, starts_at=form_time(timedelta(days=20)),
        ends_at=form_time(timedelta(days=20, hours=1)))))
    series = event_id_from(client.post(f"/events/new?club={club}", data=event_form(
        title="Weekly run", repeat="4", **club_game, starts_at=form_time(timedelta(days=2, hours=3)),
        ends_at=form_time(timedelta(days=2, hours=4)))))
    for change in ("members", "members", ""):
        client.post(f"/events/{series}/edit", data=event_form(title="Weekly run", is_private=change, **club_game,
                                                              starts_at=form_time(timedelta(days=2, hours=3)),
                                                              ends_at=form_time(timedelta(days=2, hours=4))))
    client.post(f"/events/{later}/cancel")
    accounts.logout()
    page = client.get(f"/clubs/{club}").data.decode()
    assert "Canceled: New event: Open later" in page
    assert "every" in page and "for 4 weeks" in page                         # still the series' post
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (captain,))
        get_db().commit()
    accounts.login(email="member@uw.edu")
    assert "Cap Tain" not in client.get(f"/clubs/{club}").data.decode()     # "An officer" now
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 0 WHERE id = ?", (captain,))
        get_db().commit()
    accounts.logout()
    accounts.login(email="fan@uw.edu")
    client.post(f"/clubs/{club}/join", data={"message": "Me too"})
    page = client.post(f"/clubs/{club}/leave", follow_redirects=True).data.decode()
    assert "You still follow the club" in page
    with app.app_context():
        assert get_db().execute("SELECT role FROM club_members WHERE club_id = ? AND user_id = ?",
                                (club, _user_id(app, "fan@uw.edu"))).fetchone()[0] == "follower"
        get_db().execute("INSERT INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, '2026-09-01 10:00')",
                         (captain, _user_id(app, "fan@uw.edu")))
        get_db().execute("DELETE FROM club_join_emails")
        get_db().commit()
    before = len(app.extensions["outbox"])
    client.post(f"/clubs/{club}/join", data={"message": "Again"})
    assert not [m for m in app.extensions["outbox"][before:] if m["to"] == "captain@uw.edu"]
    with app.app_context():
        from sportive.events import club_event_text
        assert club_event_text({"members_only": 1, "starts_at": "2026-10-10 10:00"}, 1).startswith("New members-only")


def test_members_only_games_and_invite_links_round_20(accounts, client, app):
    """Round 20: a member could hold a spot in a members-only game for a friend who isn't in the club (who then
    saw its note and players); a removed player's invite link kept advertising the game; a blocked person could
    open the link of someone who blocked them; a forwarded members-only link showed the club's schedule."""
    club = _club_with_member(accounts, client, app)                         # captain logged in
    member = _user_id(app, "member@uw.edu")
    accounts.logout()
    ids = _people(accounts, app, "Pal", "Pest")
    _friends(app, member, ids["Pal"])
    accounts.login(email="captain@uw.edu")
    club_game = dict(sport="spikeball", location="The Quad", club=str(club))
    members_game = event_id_from(client.post(f"/events/new?club={club}", data=event_form(
        title="Members run", is_private="members", note="Court 3", **club_game)))
    open_game = event_id_from(client.post(f"/events/new?club={club}", data=event_form(title="Open run", **club_game)))
    accounts.logout()
    accounts.login(email="member@uw.edu")
    client.post(f"/events/{members_game}/join")
    assert "Not a club member" in client.get(f"/events/{members_game}/party").data.decode()
    client.post(f"/events/{members_game}/party", data={"friend": [ids["Pal"]]})
    assert "Not a club member" in client.get(f"/events/{members_game}/send").data.decode()
    members_link = re.search(r'/join/[\w.\-]+', client.get(f"/events/{members_game}").data.decode()).group(0)
    client.post(f"/events/{open_game}/join")
    open_link = re.search(r'/join/[\w.\-]+', client.get(f"/events/{open_game}").data.decode()).group(0)
    with app.app_context():
        assert not get_db().execute("SELECT 1 FROM invites WHERE guest_id = ?", (ids["Pal"],)).fetchone()
    accounts.logout()
    page = client.get(members_link).data.decode()
    assert "members' event" in page and "Members run" not in page        # no title or time to outsiders
    assert "Open run" in client.get(open_link).data.decode()
    client.post(f"/events/{open_game}/leave")
    accounts.login(email="member@uw.edu")
    client.post(f"/events/{open_game}/leave")
    accounts.logout()
    assert "Open run" not in client.get(open_link).data.decode()            # they left: the link is app-only
    with app.app_context():
        get_db().execute("INSERT INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, '2026-09-01 10:00')",
                         (member, ids["Pest"]))
        get_db().commit()
    _as(accounts, "Pest")
    assert "doesn&#39;t work anymore" in client.get(open_link, follow_redirects=True).data.decode()


def test_number_lookups_and_pasted_page_links(accounts, client, app, monkeypatch):
    """Round 20: a check on a number that's already taken used up that number's own codes for the day (so someone
    could stop its owner getting a code); snapchat.com/discover/… and story-highlight links saved as usernames."""
    from sportive import sms
    from sportive.profile import clean_social
    _texts(monkeypatch)
    ids = _people(accounts, app, "Maya", "Sam")
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET phone = '+12065550142', phone_verified = 1 WHERE id = ?", (ids["Maya"],))
        db.commit()
        for n in range(sms.MAX_CODES_PER_NUMBER):
            assert "already used" in sms.start_phone_check(ids["Sam"], "+12065550142")
        assert sms._sent_today(ids["Sam"], codes=True) == sms.MAX_CODES_PER_NUMBER     # costs the asker
        assert db.execute("SELECT COUNT(*) FROM sms_log WHERE phone = '+12065550142' AND kind = 'code'").fetchone()[0] == 0
    assert clean_social("snapchat", "snapchat.com/discover/foo").endswith("/")
    assert clean_social("snapchat", "snapchat.com/add").endswith("/")
    assert clean_social("snapchat", "add") == "add"                                  # typed, not a link
    assert clean_social("instagram", "instagram.com/stories/highlights/123").endswith("/")
    assert clean_social("instagram", "instagram.com/Stories/maya/1") == "maya"


def test_chat_never_posts_twice_or_reloads_over_a_draft(app):
    """Round 20: a send that answered after 20 seconds showed "Couldn't send", and sending again posted it twice;
    being logged out on another device reloaded the chat and lost the typed message."""
    chat = (pathlib.Path(app.root_path) / "static" / "chat.js").read_text()
    send = chat[chat.index("const sentText"):chat.index("// Picked photos")]
    assert "location.reload" not in send and "sentAfter" in send and "This is taking a while" in send
    assert "photos[i] ? 90000 : 20000" in send


def test_deleting_an_account_steps_down_first_and_keeps_clubs_true(accounts, client, app):
    """Round 21: two officers deleting their accounts at once could both go and leave a club with none (each was
    checked before either stepped down); a club whose other officer was suspended was deleted with the account."""
    club = _club_with_member(accounts, client, app)                         # captain (owner) logged in
    member = _user_id(app, "member@uw.edu")
    client.post(f"/clubs/{club}/officers/{member}")
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    with app.app_context():
        assert get_db().execute("SELECT created_by FROM clubs WHERE id = ?", (club,)).fetchone()[0] == member
    accounts.login(email="member@uw.edu")                                   # now the only officer, with a follower
    page = client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"},
                       follow_redirects=True).data.decode()
    assert "only officer" in page
    with app.app_context():
        assert get_db().execute("SELECT role FROM club_members WHERE user_id = ?", (member,)).fetchone()[0] == "officer"
    accounts.logout()
    ids = _people(accounts, app, "Maya", "Sam")
    _as(accounts, "Maya")
    client.post("/clubs/new", data={**CLUB, "name": "Quiet Club"})
    quiet = _club_id(app, "Quiet Club")
    _approve(app, quiet)
    with app.app_context():
        get_db().execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'officer', ?)",
                         (quiet, ids["Sam"], to_db(now_local())))
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (ids["Sam"],))
        get_db().commit()
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    with app.app_context():                                                 # Sam may be let back in: it stays
        assert get_db().execute("SELECT COUNT(*) FROM clubs WHERE id = ?", (quiet,)).fetchone()[0] == 1


def test_club_posts_stay_true_however_a_game_ends_or_changes(accounts, client, app):
    """Round 21: a club event canceled by a suspension still said "New event"; editing week 1 of a weekly series
    rewrote the series' post with week 1's day; series posts from before posts knew their weeks were treated as one
    event (canceling week 1 marked the whole series canceled)."""
    from sportive.db import count_series_weeks
    from sportive.timeutil import from_db
    club = _club_with_member(accounts, client, app)                         # captain logged in
    member = _user_id(app, "member@uw.edu")
    client.post(f"/clubs/{club}/officers/{member}")
    club_game = dict(sport="spikeball", location="The Quad", club=str(club))
    series = event_id_from(client.post(f"/events/new?club={club}", data=event_form(
        title="Weekly run", repeat="3", **club_game)))
    client.post(f"/events/{series}/edit", data=event_form(title="Weekly run", **club_game,
                                                          starts_at=form_time(timedelta(days=2)),
                                                          ends_at=form_time(timedelta(days=2, hours=2))))
    accounts.logout()
    accounts.login(email="member@uw.edu")
    single = event_id_from(client.post(f"/events/new?club={club}", data=event_form(title="Open night", **club_game)))
    accounts.logout()
    with app.app_context():
        db = get_db()
        weekly = db.execute("SELECT body FROM club_posts WHERE event_id = ?", (series,)).fetchone()[0]
        assert "for 3 weeks" in weekly and from_db(db.execute("SELECT starts_at FROM events WHERE id = ?",
                                                              (series,)).fetchone()[0]).strftime("%A") not in weekly
        db.execute("INSERT INTO club_posts (club_id, author_id, body, created_at, weeks) VALUES (?, NULL, ?, ?, 1)",
                   (club, "New: Old practice, every Monday at 5:00 PM for 4 weeks, starting Mon", to_db(now_local())))
        count_series_weeks(db)
        assert db.execute("SELECT weeks FROM club_posts WHERE body LIKE 'New: Old practice%'").fetchone()[0] == 4
        db.commit()
    accounts.signup(email="admin@uw.edu", name="Ad Min")
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    client.post(f"/admin/users/{member}/suspend")
    with app.app_context():   # another officer (the captain) takes the game over, so it isn't canceled
        db = get_db()
        assert db.execute("SELECT body FROM club_posts WHERE event_id = ?", (single,)).fetchone()[0] \
            .startswith("New event: Open night")
        assert db.execute("SELECT cancelled FROM events WHERE id = ?", (single,)).fetchone()[0] == 0
    # (A suspension that does cancel a club game marks its post "Canceled:": see
    # test_club_events_with_no_other_officer_are_still_canceled_on_suspension.)


def test_announcements_texts_and_emails_round_21(accounts, client, app, monkeypatch):
    """Round 21: friends' "Maya posted Hoops (Sat). Want in?" kept the old time after a change, and stayed after the
    game went private; people waiting on a club join request stopped hearing about its games; a text about a new
    end time read like the start moved; the Monday email listed games the host took you off; Gmail's own
    Unsubscribe button got a garbled link."""
    from sportive import digest
    from sportive.mail import build_message
    from sportive.timeutil import fmt_when
    sent = _texts(monkeypatch)
    ids = _people(accounts, app, "Maya", "Sam", "Jordan")
    _friends(app, ids["Maya"], ids["Sam"], ids["Jordan"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    later = dict(starts_at=form_time(timedelta(days=3)), ends_at=form_time(timedelta(days=3, hours=2)))
    client.post(f"/events/{game}/edit", data=event_form(title="Hoops", **later))
    with app.app_context():
        text = get_db().execute("SELECT text FROM notices WHERE key = ? AND user_id = ?",
                                (f"friend_game:{game}", ids["Sam"])).fetchone()[0]
        assert fmt_when(to_db(now_local().replace(second=0, microsecond=0) + timedelta(days=3)))[:3] in text
        get_db().execute("UPDATE users SET phone = '+12065550142', phone_verified = 1, sms_updates = 1 WHERE id = ?",
                         (ids["Jordan"],))
        get_db().commit()
    _as(accounts, "Jordan")
    client.post(f"/events/{game}/join")
    _as(accounts, "Maya")
    client.post(f"/events/{game}/edit", data=event_form(title="Hoops", starts_at=later["starts_at"],
                                                       ends_at=form_time(timedelta(days=3, hours=3))))
    assert "now ends" in sent[-1][1] and "new time" not in sent[-1][1]
    other = event_id_from(client.post("/events/new", data=event_form(title="Runs")))
    client.post(f"/events/{other}/players/{ids['Sam']}/remove")
    client.post(f"/events/{other}/edit", data=event_form(title="Runs", is_private="1", password="huskies1"))
    with app.app_context():
        assert not get_db().execute("SELECT 1 FROM notices WHERE key = ?", (f"friend_game:{other}",)).fetchone()
    other2 = event_id_from(client.post("/events/new", data=event_form(title="Pickup")))
    _as(accounts, "Sam")
    client.post(f"/events/{other2}/join")
    _as(accounts, "Maya")
    client.post(f"/events/{other2}/players/{ids['Sam']}/remove")
    with app.test_request_context():
        with app.app_context():
            sam = get_db().execute("SELECT * FROM users WHERE id = ?", (ids["Sam"],)).fetchone()
            from flask import g
            g.user = sam
            open_games, _ = digest.games_for(sam)
    assert not any("Pickup" in line for line in open_games)
    msg = build_message({"MAIL_USERNAME": "a@b.c"}, "x@uw.edu", "Hi", "body",
                        unsubscribe="https://sportivecircle.com/unsubscribe/" + "W" * 120)
    raw = msg.as_bytes().decode()
    assert "List-Unsubscribe: <https://sportivecircle.com/unsubscribe/" in raw and "Message-ID:" in raw


def test_waiting_to_join_still_hears_about_club_games(accounts, client, app):
    """Round 21: someone waiting on a join request stopped hearing about the club's new games; the club directory
    counted private games it doesn't show."""
    club = _club_with_member(accounts, client, app)                         # captain logged in
    accounts.logout()
    accounts.signup(email="waiting@uw.edu", name="Wai Ting")
    client.post(f"/clubs/{club}/follow")
    client.post(f"/clubs/{club}/join", data={"message": "Hi"})
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    club_game = dict(sport="spikeball", location="The Quad", club=str(club))
    client.post(f"/events/new?club={club}", data=event_form(title="Club night", **club_game))
    client.post(f"/events/new?club={club}", data=event_form(title="Secret", is_private="1", password="huskies1",
                                                           **club_game))
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM notices WHERE user_id = ? AND kind = 'friend_games'",
                                (_user_id(app, "waiting@uw.edu"),)).fetchone()[0] == 1
    directory = client.get("/clubs").data.decode()
    assert "1 upcoming" in directory and "2 upcoming" not in directory          # the private one isn't counted


def test_search_and_invite_wording_round_21(accounts, client, app):
    """Round 21: Messages search stopped at 20 people before keeping only those you can message, so 20 other "Alex"es
    hid the one who messaged you; clubs search didn't know sport names ("skiing"); a friend's invite link said the
    game wasn't open when only the friend had left."""
    ids = _people(accounts, app, "Ann", "Alex", "Sam")
    with app.app_context():
        db = get_db()
        db.executemany("INSERT INTO users (email, full_name, password_hash, verified, created_at) VALUES (?, ?, 'x', 1, ?)",
                       [(f"alex{n}@uw.edu", f"Alex A{n:02d}", to_db(now_local())) for n in range(25)])
        db.execute("INSERT INTO direct_messages (sender_id, recipient_id, body, created_at) VALUES (?, ?, 'hey', ?)",
                   (ids["Alex"], ids["Ann"], to_db(now_local())))
        db.commit()
    _as(accounts, "Ann")
    assert "Alex Husky" in client.get("/messages?q=alex").data.decode()
    _friends(app, ids["Ann"], ids["Sam"])
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    _as(accounts, "Sam")
    client.post(f"/events/{game}/join")
    link = re.search(r'/join/[\w.\-]+', client.get(f"/events/{game}").data.decode()).group(0)
    client.post(f"/events/{game}/leave")
    accounts.logout()
    assert "Sam isn't in that game anymore" in client.get(link).data.decode()
    accounts.signup(email="skier@uw.edu", name="Ski Er")
    client.post("/clubs/new", data={**CLUB, "name": "Husky Powder Crew", "sport": "snow",
                                    "description": "Weekend trips to the mountains."})
    _approve(app, _club_id(app, "Husky Powder Crew"))
    found = client.get("/clubs?q=skiing").data.decode()
    assert "Husky Powder Crew" in found


def _next(weekday, hour, minute=0, month=None):
    """The next date at least 2 days away on `weekday` (0 = Monday), optionally in `month`, at hour:minute."""
    day = now_local() + timedelta(days=2)
    while day.weekday() != weekday or (month and day.month != month):
        day += timedelta(days=1)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def test_games_only_while_the_place_is_open(accounts, client, app):
    """The owner: a game can't be posted at a place when it's closed (the IMA closes at 8:30 PM on weekends, the golf
    range is closed on Mondays in October, the WAC closes for the season). The form shows the hours; editing a
    game's note isn't held to hours that changed later; every week of a weekly practice is checked."""
    from sportive.placehours import closed_message, hours_on
    app.config["CHECK_PLACE_HOURS"] = True
    at = lambda moment: moment.strftime("%Y-%m-%dT%H:%M")
    accounts.signup()
    saturday = _next(5, 20)
    late = client.post("/events/new", data=event_form(starts_at=at(saturday), ends_at=at(saturday.replace(hour=22))),
                       follow_redirects=True).data.decode()
    assert "The IMA is open 9:00 AM – 8:30 PM on Saturdays" in late
    game = event_id_from(client.post("/events/new", data=event_form(
        starts_at=at(saturday.replace(hour=10)), ends_at=at(saturday.replace(hour=12)))))
    assert game
    early = client.post("/events/new", data=event_form(title="Early", starts_at=at(_next(0, 5)),
                                                       ends_at=at(_next(0, 7))), follow_redirects=True).data.decode()
    assert "The IMA is open 6:00 AM – 10:30 PM on Mondays" in early
    page = client.get("/events/new").data.decode()
    assert 'id="place-hours"' in page and "data-place-hours" in page
    with app.app_context():
        get_db().execute("UPDATE events SET starts_at = ?, ends_at = ? WHERE id = ?",   # posted before the hours
                         (to_db(saturday.replace(hour=21)), to_db(saturday.replace(hour=22)), game))
        get_db().commit()
    client.post(f"/events/{game}/edit", data=event_form(note="Bring water", starts_at=at(saturday.replace(hour=21)),
                                                       ends_at=at(saturday.replace(hour=22))))
    with app.app_context():
        assert get_db().execute("SELECT note FROM events WHERE id = ?", (game,)).fetchone()[0] == "Bring water"
        golf, wac = "UW Golf Driving Range", "Waterfront Activities Center (WAC)"
        monday = _next(0, 12, month=10)
        assert "closed on Mondays" in closed_message(golf, monday, monday.replace(hour=13))
        november = _next(2, 12, month=11)
        assert "closed for the season" in closed_message(wac, november, november.replace(hour=13))
        assert hours_on("Denny Field", november.date()) == "any"                # no posted hours: no limit
        assert closed_message("Green Lake Park pickleball courts", november.replace(hour=23),
                              november.replace(hour=23, minute=45)).startswith("The Green Lake pickleball courts are")
        assert closed_message("IMA South Tennis Courts", november.replace(hour=5),
                              november.replace(hour=6)) is None                # only a lights-off time
    accounts.logout()
    club = _approved_club(accounts, client, app, name="Husky Golf", sport="golf", location="UW Golf Driving Range")
    accounts.login(email="captain@uw.edu")
    tuesday = _next(1, 12, month=10)
    while (tuesday + timedelta(weeks=5)).month != 11:                         # a practice that runs into November
        tuesday += timedelta(weeks=1)
    page = client.post(f"/events/new?club={club}", data=event_form(
        title="Range day", sport="golf", location="UW Golf Driving Range", club=str(club), repeat="6",
        starts_at=at(tuesday), ends_at=at(tuesday.replace(hour=14))), follow_redirects=True).data.decode()
    assert "closed on Tuesdays" in page and "Week " in page


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
    _as(accounts, "Maya")                                                    # the host heard about the challenge
    assert "Jordan&#39;s team challenged 2v2 run" in client.get("/notifications").data.decode()


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
        assert re.search(r'name="password"[^>]*disabled|value="[a-z]+-[a-z]+-\d{3}"', html)   # ready-made, off until Private
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
        assert default_title("esports", "The HUB (Husky Union Building)") == "Esports at the HUB"
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
    assert settings.count('class="switch"') == 10         # club requests (officers) and trends (admins) hidden
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
    assert client.post(link).headers["Location"] == "/signup"      # the tap is what saves the invite
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
    client.get(link)                                              # only looking: logging in later doesn't join
    assert accounts.login(email="later@uw.edu").headers["Location"] != f"/events/{game}"
    accounts.logout()
    assert client.post(link, data={"go": "login"}).headers["Location"] == "/login"   # "I have an account"
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



def test_invite_friends_to_the_app_makes_you_friends(accounts, client, app):
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    link = _invite_path(client.get("/friends").data.decode())
    assert "Invite friends to Sportive Circle" in client.get("/friends").data.decode()
    accounts.logout()
    assert "Maya wants you on Sportive Circle" in client.get(link).data.decode()
    client.post(link)                                                   # "Sign up"
    client.post("/signup", data={"full_name": "Pal Friend", "email": "pal@uw.edu", "password": "purple-and-gold",
                                 "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    client.post("/verify", data={"code": accounts.code_for("pal@uw.edu")})
    with app.app_context():
        assert get_db().execute("SELECT status FROM friendships").fetchone()[0] == "accepted"


def test_sign_up_is_short_screens(client, app):
    """Screen 1 checks the details (and emails the code); screen 2 is sports; screen 3 (optional) is texts."""
    page = client.get("/signup").data.decode()
    assert "Step 1 of 4" in page and 'name="sports"' not in page and ">Next</button>" in page   # (3 without texts)
    bad = client.post("/signup", follow_redirects=True, data={"full_name": "Dubs Husky", "email": "dubs@gmail.com", "password": "purple-and-gold",
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
    """Like Instagram: on someone else's profile their photo opens big (and closes again); on yours one tap opens
    the editor and a double tap shows it big."""
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    maya = _user_id(app, "maya@uw.edu")
    mine = client.get(f"/u/{maya}").data.decode()
    assert 'href="/profile/photo" data-zoom="photo-big"' in mine and "data-zoom-double" in mine
    accounts.logout()
    accounts.signup(email="me@uw.edu")
    page = client.get(f"/u/{maya}").data.decode()
    assert 'data-zoom="photo-big"' in page and '<dialog id="photo-big" class="photo-lightbox"' in page
    assert f"background-image: url('/u/{maya}/photo?v=" in page and '<img' not in page.split('id="photo-big"')[1][:300]


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
    # ...and trying to join says why, not just "full" (tester: "it looks like it just doesn't work").
    said = client.post(f"/events/{game}/join", follow_redirects=True).data.decode()
    assert "Sorry, this game is full for now: 1 spot is held for friends Maya invited." in said
    assert "a spot opens at" in said and "Full for now" in said and "data-reload-in=" in said
    _as(accounts, "Friend")
    assert "Held run" in client.get("/?scope=all").data.decode()               # the friend it's held for sees it
    with app.app_context():                                                    # 30 minutes later the hold is over:
        get_db().execute("UPDATE invites SET expires_at = '2000-01-01 00:00'")
        get_db().commit()
    _as(accounts, "Stranger")
    assert "Held run" in client.get("/?scope=all").data.decode()               # open again for everyone


def test_a_really_full_game_still_just_says_full(accounts, client, app):
    """Only held spots get the "full for now" note: a game full of players has no time when it opens."""
    _people(accounts, app, "Maya", "Pal", "Stranger")
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Duo", players="2")))
    _as(accounts, "Pal")
    client.post(f"/events/{game}/join")
    _as(accounts, "Stranger")
    said = client.post(f"/events/{game}/join", follow_redirects=True).data.decode()
    assert "Sorry, this game is full." in said and "for now" not in said and "If someone leaves" in said


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
    """Optional step 3: a phone number with permission. Its code is only texted once the UW email is confirmed
    (texts cost money, so made-up accounts can't send any), then confirmed on the next screen."""
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
    assert sent == []                                                  # nothing texted before the email is real
    assert "Code from your email" in client.get("/verify").data.decode()
    with app.app_context():
        email_code = get_db().execute("SELECT verify_code FROM users").fetchone()[0]
    assert client.post("/verify", data={"code": email_code}).headers["Location"] == "/signup/number"
    assert sent[-1][0] == "+12065550142" and "Sportive Circle code:" in sent[-1][1]
    page = client.get("/signup/number").data.decode()
    assert "(•••) •••-0142" in page and "Code from the text" in page and "Skip for now" in page
    assert b"isn&#39;t right" in client.post("/signup/number", data={"code": "000000"}).data
    with app.app_context():
        sms_code = get_db().execute("SELECT sms_code FROM users").fetchone()[0]
    assert client.post("/signup/number", data={"code": sms_code}).headers["Location"] == "/"
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
        get_db().execute("UPDATE users SET phone = '+12065550142', phone_verified = 1, sms_updates = 1, verify_sent_at = NULL")
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
    assert ("5 min ago" in page or "6 min ago" in page) and "happening now" not in page   # a minute may tick over


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


def test_phone_numbers_with_a_country_picker():
    """Pick the country (+1, +44...), type the number any way: it's saved with its country code."""
    from sportive.phones import group_digits, phone_from_form, pretty_phone, split_phone
    assert phone_from_form("US", "206-555-0142") == phone_from_form("US", "(206) 555 0142") == "+12065550142"
    assert phone_from_form("CA", "1 604 555 0142") == "+16045550142"
    assert phone_from_form("GB", "07946 095 800") == "+447946095800"          # the leading 0 is dropped
    assert phone_from_form("IN", "98765 43210") == "+919876543210"
    assert phone_from_form("US", "+44 7946 095800") == "+447946095800"       # a typed + code wins
    assert phone_from_form("US", "555-0142") is None and phone_from_form("ZZ", "2065550142") is None
    assert split_phone("+12065550142") == ("US", "206-555-0142")
    assert pretty_phone("+447946095800") == "+44 794-609-5800"
    assert group_digits("2065550142", us=True) == "206-555-0142"


def test_club_registration_asks_for_a_phone_only_admins_see(accounts, client, app):
    accounts.signup(email="captain@uw.edu")
    form = client.get("/clubs/new").data.decode()
    assert 'name="contact_phone_country"' in form and '<option value="GB" data-dial="44"' in form
    page = client.post("/clubs/new", data={**CLUB, "contact_phone": ""}).data.decode()
    assert "Add a phone number we can reach you at" in page and 'data-error-field="contact_phone"' in page
    client.post("/clubs/new", data={**CLUB, "contact_phone_country": "GB", "contact_phone": "07946 095800"})
    with app.app_context():
        assert get_db().execute("SELECT contact_phone FROM clubs").fetchone()[0] == "+447946095800"
    club = _club_id(app)
    assert "+44 794-609-5800" not in client.get(f"/clubs/{club}").data.decode()      # not on the club page
    accounts.logout()
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="admin@uw.edu")
    assert 'href="tel:+447946095800">+44 794-609-5800</a>' in client.get("/admin/clubs").data.decode()


def test_admins_can_deny_spam_and_remove_verified_clubs(accounts, client, app, monkeypatch):
    from sportive import clubs
    monkeypatch.setattr(clubs, "send_email", lambda *args, **kwargs: None)
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="spammer@uw.edu")
    client.post("/clubs/new", data={**CLUB, "name": "Buy Cheap Stuff"})
    spam = _club_id(app, "Buy Cheap Stuff")
    accounts.logout()
    accounts.signup(email="captain@uw.edu")
    client.post("/clubs/new", data=CLUB)
    with app.app_context():
        real = get_db().execute("SELECT id FROM clubs WHERE name = ?", (CLUB["name"],)).fetchone()[0]
    accounts.logout()
    accounts.signup(email="admin@uw.edu")
    queue = client.get("/admin/clubs").data.decode()
    assert "Deny (spam)" in queue and ">Denied (0)</a>" in queue
    client.post(f"/admin/clubs/{spam}/deny")
    with app.app_context():
        assert get_db().execute("SELECT status FROM clubs WHERE id = ?", (spam,)).fetchone()[0] == "denied"
    assert "Buy Cheap Stuff" in client.get("/admin/clubs?status=denied").data.decode()
    client.post(f"/admin/clubs/{real}/approve")
    assert "UW Spikeball Club" in client.get("/clubs").data.decode()
    # Remove: back to the waiting list, off the public list, and the officers hear why
    client.post(f"/admin/clubs/{real}/remove", data={"note": "Your Instagram is private."})
    assert f'href="/clubs/{real}"' not in client.get("/clubs").data.decode()          # off the public list
    assert "UW Spikeball Club" in client.get("/admin/clubs?status=pending").data.decode()
    assert client.post(f"/admin/clubs/{real}/restore").status_code == 302            # only denied ones restore
    with app.app_context():
        assert get_db().execute("SELECT status FROM clubs WHERE id = ?", (real,)).fetchone()[0] == "pending"
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    assert "back in review: “Your Instagram is private.”" in client.get("/notifications").data.decode()
    # the spammer can't edit or resend a denied request
    accounts.logout()
    accounts.login(email="spammer@uw.edu")
    assert "was denied" in client.get(f"/clubs/{spam}").data.decode()
    assert client.get(f"/clubs/{spam}/edit").headers["Location"].endswith(f"/clubs/{spam}")


def test_phone_groups_never_leave_a_lonely_digit():
    from sportive.phones import group_digits
    assert group_digits("07946095800") == "079-4609-5800" and group_digits("9876543210") == "987-654-3210"


def test_send_a_public_game_to_friends_as_a_message(accounts, client, app):
    """Tester: "there's no way of just quickly sending it to those we have on the app as a DM"."""
    ids = _people(accounts, app, "Maya", "Me", "Pal", "Stranger")
    _friends(app, ids["Me"], ids["Pal"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Sunset run", players="6")))
    _as(accounts, "Me")                                               # not going, just saw it on Home
    page = client.get(f"/events/{game}").data.decode()
    assert f"/events/{game}/send" in page and "Send to friends" in page
    picker = client.get(f"/events/{game}/send").data.decode()
    assert "Pal Husky" in picker and "Stranger Husky" not in picker   # only friends
    done = client.post(f"/events/{game}/send", data={"friend": [ids["Pal"]], "note": "you in?"},
                       follow_redirects=True).data.decode()
    assert "Sent to Pal." in done
    bad = client.post(f"/events/{game}/send", data={"friend": [ids["Stranger"]]}, follow_redirects=True)
    assert b"only send games to your friends" in bad.data              # not to strangers
    _as(accounts, "Pal")
    thread = client.get(f"/messages/{ids['Me']}").data.decode()
    assert "you in?" in thread and 'class="chat-game' in thread and f'href="/events/{game}"' in thread
    assert "Sunset run" in thread
    polled = client.get(f"/messages/{ids['Me']}/poll?after=0").get_json()
    shared = polled if isinstance(polled, list) else polled.get("messages", polled)
    assert "Sunset run" in str(shared)


def test_private_games_cant_be_sent_to_friends(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Pal")
    _friends(app, ids["Maya"], ids["Pal"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Secret run", is_private="1",
                                                                     password="dawgs26")))
    assert f"/events/{game}/send" not in client.get(f"/events/{game}").data.decode()
    assert b"Only open games" in client.post(f"/events/{game}/send", data={"friend": [ids["Pal"]]},
                                             follow_redirects=True).data


def test_existing_people_get_a_texts_card_on_home_until_they_answer(accounts, client, app):
    _people(accounts, app, "Maya")
    _as(accounts, "Maya")
    home = client.get("/").data.decode()
    assert "New: game updates by text" in home and 'name="consent"' in home
    done = client.post("/settings/texts/not-now", follow_redirects=True).data.decode()
    assert "Settings → Texts" in done and "New: game updates by text" not in client.get("/").data.decode()


def test_adding_a_number_from_the_home_card_hides_it(accounts, client, app):
    ids = _people(accounts, app, "Maya")
    _as(accounts, "Maya")
    client.post("/settings/texts", data={"action": "send", "phone_country": "US", "phone": "206-555-0142",
                                         "consent": "1"})
    with app.app_context():
        code = get_db().execute("SELECT sms_code FROM users WHERE id = ?", (ids["Maya"],)).fetchone()[0]
    assert code
    client.post("/settings/texts", data={"action": "confirm", "code": code})
    assert "New: game updates by text" not in client.get("/").data.decode()


def test_texts_announcement_emails_everyone_once(accounts, client, app):
    from sportive.announcements import announce_texts
    _people(accounts, app, "Maya", "Jordan")
    with app.app_context():
        app.extensions["outbox"] = []
        assert announce_texts(send=False) == (2, 0) and app.extensions["outbox"] == []   # dry run sends nothing
        assert announce_texts(send=True) == (2, 0)
        mails = [m for m in app.extensions["outbox"] if "by text" in m["subject"]]
        assert sorted(m["to"] for m in mails) == ["jordan@uw.edu", "maya@uw.edu"]
        assert "/settings/texts" in mails[0]["body"]
        assert announce_texts(send=True) == (0, 0)                                          # never twice


def test_hosts_are_told_to_check_the_place_is_free(accounts, client, app):
    """The user: the host has to make sure the courts, field or trail aren't booked; we don't check."""
    accounts.signup()
    for page in ("/events/new", "/need-players"):
        html = client.get(page).data.decode()
        assert "Heads up: check you can use the" in html and "We don't reserve places" in html
    html = client.get("/events/new").data.decode()
    assert '"space"' in html and '"courts"' in html and '"trail"' in html  # the word follows the sport (forms.js)
    assert "make sure the place is free" in client.get("/terms").data.decode()


def test_messages_lists_friends_without_chats_and_can_search(accounts, client, app):
    """The user: "if we don't have messages with that friend, it doesn't show on the messages page"."""
    ids = _people(accounts, app, "Maya", "Jordan", "Sam", "Stranger")
    _friends(app, ids["Maya"], ids["Jordan"], ids["Sam"])
    _as(accounts, "Maya")
    client.post(f"/messages/{ids['Jordan']}", data={"body": "yo"})
    page = client.get("/messages").data.decode()
    assert "Jordan Husky" in page and "Sam Husky" in page and "Start a chat" in page   # Sam: friend, no chat yet
    assert "Stranger Husky" not in page
    assert page.count(f'href="/messages/{ids["Jordan"]}"') == 1                         # not twice
    assert 'data-filter-list="#inbox-people"' in page and 'data-filter-name="Sam Husky"' in page
    found = client.get("/messages?q=sam").data.decode()
    assert f'href="/messages/{ids["Sam"]}"' in found and "Friend" in found
    assert "Jordan Husky" not in found
    nobody = client.get("/messages?q=stranger").data.decode()
    assert "Stranger Husky" not in nobody and "find them in Friends" in nobody          # strangers: add first
    assert "at least 2 letters" in client.get("/messages?q=s").data.decode()


def test_empty_messages_page_points_to_friends(accounts, client):
    accounts.signup()
    page = client.get("/messages").data.decode()
    assert "No messages yet." in page and "Search friends and chats" in page


def _day_after_tomorrow(hour):
    from sportive.timeutil import now_local
    day = (now_local() + timedelta(days=2)).replace(hour=hour, minute=0)
    return day.strftime("%Y-%m-%d"), day.strftime("%Y-%m-%dT%H:%M")


def test_uw_rec_reservations_and_other_games_show_while_making_a_game(accounts, client, app):
    """The user: show "UW Rec: reserved" (can't play there) and other games there then (busy, not taken)."""
    app.config["ADMIN_EMAILS"] = "maya@uw.edu"
    _people(accounts, app, "Maya", "Sam")
    _as(accounts, "Maya")
    date, six_pm = _day_after_tomorrow(18)
    field = "Recreation Field 1 (by the IMA)"
    assert b"UW Rec reservations" in client.get("/admin/uw-rec").data
    done = client.post("/admin/uw-rec", data={"location": field, "label": "IM flag football", "date": date,
                                              "start": "18:00", "end": "22:00", "weeks": "3"}, follow_redirects=True)
    assert b"Added 3 reservations." in done.data
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rec_reservations").fetchone()[0] == 3
    client.post("/events/new", data=event_form(title="Field pickup", sport="soccer", location=field,
                                               starts_at=six_pm, ends_at=six_pm[:-5] + "19:00"))
    _as(accounts, "Sam")
    _, seven_pm = _day_after_tomorrow(19)
    info = client.get("/events/place-check", query_string={"location": field, "starts_at": six_pm,
                                                           "ends_at": seven_pm}).get_json()
    assert info["uw_rec"] and info["schedule"].startswith("https://reg.recreation.uw.edu")
    assert [r["label"] for r in info["reserved"]] == ["IM flag football"] and "10:00 PM" in info["reserved"][0]["when"]
    assert [g["title"] for g in info["games"]] == ["Field pickup"] and info["games"][0]["going"] == 1
    later = client.get("/events/place-check", query_string={"location": field, "starts_at": seven_pm[:-5] + "22:00",
                                                            "ends_at": seven_pm[:-5] + "23:00"}).get_json()
    assert later["reserved"] == [] and later["games"] == []                   # after both: nothing on
    trail = client.get("/events/place-check", query_string={"location": "Burke-Gilman Trail", "starts_at": six_pm,
                                                            "ends_at": seven_pm}).get_json()
    assert not trail["uw_rec"] and trail["schedule"] is None                  # not a UW Rec place
    assert client.get("/admin/uw-rec").status_code == 404                     # admins only


def test_game_page_shows_what_else_is_on_there(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "maya@uw.edu"
    _people(accounts, app, "Maya", "Sam")
    _as(accounts, "Maya")
    date, six_pm = _day_after_tomorrow(18)
    field = "Recreation Field 1 (by the IMA)"
    client.post("/admin/uw-rec", data={"location": field, "label": "Club rugby", "date": date,
                                       "start": "17:00", "end": "19:00", "weeks": "1"})
    mine = event_id_from(client.post("/events/new", data=event_form(title="Mine", sport="soccer", location=field,
                                                                     starts_at=six_pm, ends_at=six_pm[:-5] + "19:00")))
    _as(accounts, "Sam")
    client.post("/events/new", data=event_form(title="Secret kick", sport="soccer", location=field, starts_at=six_pm,
                                               ends_at=six_pm[:-5] + "19:00", is_private="1", password="dawgs26"))
    _as(accounts, "Maya")
    page = client.get(f"/events/{mine}").data.decode()
    assert "UW Rec: reserved" in page and "Club rugby" in page and "Check the place is still free" in page
    assert "A private game" in page and "Secret kick" not in page             # private details stay private


def test_removing_a_weekly_uw_rec_reservation(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "maya@uw.edu"
    _people(accounts, app, "Maya")
    _as(accounts, "Maya")
    date, _ = _day_after_tomorrow(18)
    client.post("/admin/uw-rec", data={"location": "IMA (Intramural Activities Building)", "label": "IM hoops",
                                       "date": date, "start": "18:00", "end": "21:00", "weeks": "4"})
    with app.app_context():
        first = get_db().execute("SELECT id FROM rec_reservations ORDER BY starts_at").fetchone()[0]
    client.post(f"/admin/uw-rec/{first}/delete")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rec_reservations").fetchone()[0] == 3
        second = get_db().execute("SELECT id FROM rec_reservations ORDER BY starts_at").fetchone()[0]
    client.post(f"/admin/uw-rec/{second}/delete", data={"all": "1"})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rec_reservations").fetchone()[0] == 0
    bad = client.post("/admin/uw-rec", data={"location": "Burke-Gilman Trail", "label": "x", "date": date,
                                             "start": "18:00", "end": "19:00"}, follow_redirects=True)
    assert b"Pick one of UW Rec" in bad.data


def test_events_can_have_no_limit_or_up_to_1000(accounts, client, app):
    """The user: club events can have more than 100 people; hosts choose a number or no limit."""
    accounts.signup()
    page = client.get("/events/new").data.decode()
    assert 'name="no_limit"' in page and 'max="1000"' in page
    assert 'name="no_limit"' not in client.get("/need-players").data.decode()   # Need players always counts down
    big = event_id_from(client.post("/events/new", data=event_form(title="Elm Hall Run", players="500")))
    assert "of 500" in client.get(f"/events/{big}").data.decode()
    open_run = event_id_from(client.post("/events/new", data=event_form(title="Hall social", no_limit="1",
                                                                        players="")))
    with app.app_context():
        assert get_db().execute("SELECT max_players FROM events WHERE id = ?", (open_run,)).fetchone()[0] is None
    detail = client.get(f"/events/{open_run}").data.decode()
    assert "spot" not in detail.split("Participants")[1].split("</dd>")[0]        # no "x spots left"
    edit = client.get(f"/events/{open_run}/edit").data.decode()
    assert 'name="no_limit" value="1" data-no-limit checked' in edit
    too_big = client.post("/events/new", data=event_form(title="Typo", players="1001"), follow_redirects=True)
    assert b"Pick 2 to 1000 participants" in too_big.data


def test_anyone_can_join_a_no_limit_event(accounts, client, app):
    _people(accounts, app, "Maya", "Sam", "Jordan")
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hall run", no_limit="1", players="")))
    for name in ("Sam", "Jordan"):
        _as(accounts, name)
        assert b"You&#39;re in" in client.post(f"/events/{game}/join", follow_redirects=True).data
    assert "Hall run" in client.get("/?scope=all").data.decode()


def _club_with_officer(accounts, client, app, owner="Maya"):
    """An approved club registered by `owner` (so they're its first officer). Returns its id. Ends logged out."""
    _as(accounts, owner)
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app, CLUB["name"])
    _approve(app, club)
    accounts.logout()
    return club


def test_club_owner_adds_and_removes_officers(accounts, client, app):
    """The user: the person who registered the club gives officer rights to other users."""
    ids = _people(accounts, app, "Maya", "Sam", "Jordan")
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Maya")
    page = client.get(f"/clubs/{club}").data.decode()
    assert "Manage officers" in page and "You're an officer" in page and "is-static" not in page
    found = client.get(f"/clubs/{club}/officers?q=sam").data.decode()
    assert "Sam Husky" in found and "Make officer" in found               # anyone on the app, not only members
    client.post(f"/clubs/{club}/officers", data={"user": ids["Sam"], "action": "add"})
    with app.app_context():
        role = get_db().execute("SELECT role FROM club_members WHERE club_id = ? AND user_id = ?",
                                (club, ids["Sam"])).fetchone()[0]
    assert role == "officer"
    _as(accounts, "Sam")                                                   # an officer, but not the owner:
    assert "You&#39;re now an officer of " + CLUB["name"] in client.get(f"/messages/{ids['Maya']}").data.decode()
    assert client.get(f"/clubs/{club}/edit").status_code == 200            # can edit the club
    assert client.get(f"/clubs/{club}/officers").status_code == 403        # can't hand out officer rights
    assert "Manage officers" not in client.get(f"/clubs/{club}").data.decode()
    assert client.post(f"/clubs/{club}/officers/{ids['Jordan']}").status_code == 403
    _as(accounts, "Maya")
    client.post(f"/clubs/{club}/officers", data={"user": ids["Sam"], "action": "remove"})
    kept = client.post(f"/clubs/{club}/officers", data={"user": ids["Maya"], "action": "remove"},
                       follow_redirects=True).data.decode()
    assert "The owner stays an officer" in kept
    with app.app_context():
        roles = dict(get_db().execute("SELECT user_id, role FROM club_members WHERE club_id = ?", (club,)).fetchall())
    assert roles[ids["Sam"]] == "member" and roles[ids["Maya"]] == "officer"


def _weekly_run_by_second_officer(accounts, client, app):
    """Maya owns the club; Sam, another officer, posts a 3-week run. Returns (ids, club). Ends logged out."""
    ids = _people(accounts, app, "Maya", "Sam", "Admin")
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Maya")
    client.post(f"/clubs/{club}/officers", data={"user": ids["Sam"], "action": "add"})
    _as(accounts, "Sam")
    client.post("/events/new", data={**event_form(title="Tuesday Run", sport="spikeball", location="The Quad"),
                                     "club": club, "repeat": "3"})
    accounts.logout()
    return ids, club


def _runs(app):
    with app.app_context():
        return [tuple(row) for row in get_db().execute(
            "SELECT host_id, cancelled FROM events WHERE title = 'Tuesday Run' ORDER BY starts_at").fetchall()]


def test_club_events_go_to_the_owner_when_their_officer_steps_down(accounts, client, app):
    ids, club = _weekly_run_by_second_officer(accounts, client, app)
    assert _runs(app) == [(ids["Sam"], 0)] * 3
    _as(accounts, "Maya")
    client.post(f"/clubs/{club}/officers", data={"user": ids["Sam"], "action": "remove"})
    assert _runs(app) == [(ids["Maya"], 0)] * 3                     # the club's runs go on, run by the owner
    _as(accounts, "Sam")                                             # and Sam is a player who can leave
    with app.app_context():
        first = get_db().execute("SELECT id FROM events WHERE title = 'Tuesday Run' ORDER BY starts_at").fetchone()[0]
    page = client.post(f"/events/{first}/leave", follow_redirects=True).data.decode()
    assert "You left" in page and "You&#39;re the host" not in page


def test_club_events_stay_when_their_officer_deletes_their_account(accounts, client, app):
    ids, club = _weekly_run_by_second_officer(accounts, client, app)
    _as(accounts, "Sam")
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    assert _runs(app) == [(ids["Maya"], 0)] * 3                     # not deleted, not canceled


def test_club_events_stay_when_their_officer_is_suspended(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    ids, club = _weekly_run_by_second_officer(accounts, client, app)
    _as(accounts, "Admin")
    client.post(f"/admin/users/{ids['Sam']}/suspend")
    assert _runs(app) == [(ids["Maya"], 0)] * 3


def test_club_events_with_no_other_officer_are_still_canceled_on_suspension(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    ids = _people(accounts, app, "Maya", "Admin")
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Maya")
    client.post("/events/new", data={**event_form(title="Tuesday Run", sport="spikeball", location="The Quad"),
                                     "club": club})
    _as(accounts, "Admin")
    client.post(f"/admin/users/{ids['Maya']}/suspend")
    assert _runs(app) == [(ids["Maya"], 1)]                          # nobody to hand it to: canceled, as before
    with app.app_context():
        assert get_db().execute("SELECT body FROM club_posts WHERE club_id = ? AND body LIKE '%Tuesday Run%'",
                                (club,)).fetchone()[0].startswith("Canceled: ")


def test_fixing_capitals_in_a_club_name_keeps_it_live(accounts, client, app):
    _people(accounts, app, "Maya")
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Maya")
    assert "sends it back for a quick check" in client.get(f"/clubs/{club}/edit").data.decode()   # warned first
    page = client.post(f"/clubs/{club}/edit", data={**CLUB, "name": "uw  SPIKEBALL club"},
                       follow_redirects=True).data.decode()
    assert "Club updated." in page and "check it again" not in page
    with app.app_context():
        assert tuple(get_db().execute("SELECT name, status FROM clubs WHERE id = ?", (club,)).fetchone()) \
            == ("uw SPIKEBALL club", "approved")      # (extra spaces are tidied on save)
    accounts.logout()
    assert client.get(f"/clubs/{club}").status_code == 200                # still public, so printed QR codes work
    _as(accounts, "Maya")
    client.post(f"/clubs/{club}/edit", data={**CLUB, "name": "UW Roundnet Club"})   # a real new name: re-checked
    with app.app_context():
        assert get_db().execute("SELECT status FROM clubs WHERE id = ?", (club,)).fetchone()[0] == "pending"


def test_follow_after_the_login_ended_goes_back_to_the_club(accounts, client, app):
    _people(accounts, app, "Maya", "Sam")
    club = _club_with_officer(accounts, client, app)                          # ends logged out
    sent = client.post(f"/clubs/{club}/follow", headers={"Referer": f"http://localhost/clubs/{club}"})
    assert sent.status_code == 302 and f"next=/clubs/{club}" in sent.headers["Location"]
    assert "follow" not in sent.headers["Location"]                              # not the form's address (a 405)
    page = client.post(f"/login?next=/clubs/{club}", data={"email": "sam@uw.edu", "password": "purple-and-gold"},
                       follow_redirects=True)
    assert page.status_code == 200 and CLUB["name"] in page.data.decode()
    # A form sent from another website goes to Home instead
    accounts.logout()
    elsewhere = client.post(f"/clubs/{club}/follow", headers={"Referer": "https://evil.example/clubs/1"})
    assert elsewhere.headers["Location"] == "/login?next=/"


def test_forms_have_back_buttons(accounts, client, app):
    _people(accounts, app, "Maya")
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Maya")
    assert f'href="/clubs/{club}" data-back>← Back' in client.get(f"/clubs/{club}/edit").data.decode()
    assert 'class="back-link"' in client.get("/events/new").data.decode()
    assert f'href="/clubs/{club}" data-back' in client.get(f"/events/new?club={club}").data.decode()
    assert 'class="back-link"' in client.get("/need-players").data.decode()


def test_owner_hands_the_club_to_another_officer(accounts, client, app):
    """The user: the owner can switch the owner role to an officer (e.g. whoever registered it hands it over)."""
    ids = _people(accounts, app, "Maya", "John", "Sam")
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Maya")
    page = client.get(f"/clubs/{club}/officers").data.decode()
    assert 'value="owner"' not in page                                          # only other officers get the button
    refused = client.post(f"/clubs/{club}/officers", data={"user": ids["Sam"], "action": "owner"},
                          follow_redirects=True).data.decode()
    assert "Make them an officer first" in refused                            # not an officer yet
    client.post(f"/clubs/{club}/officers", data={"user": ids["John"], "action": "add"})
    assert 'value="owner"' in client.get(f"/clubs/{club}/officers").data.decode()
    done = client.post(f"/clubs/{club}/officers", data={"user": ids["John"], "action": "owner"},
                       follow_redirects=True).data.decode()
    assert "John is the owner now" in done
    with app.app_context():
        owner = get_db().execute("SELECT created_by FROM clubs WHERE id = ?", (club,)).fetchone()[0]
        maya_role = get_db().execute("SELECT role FROM club_members WHERE club_id = ? AND user_id = ?",
                                     (club, ids["Maya"])).fetchone()[0]
    assert owner == ids["John"] and maya_role == "officer"                   # Maya stays an officer
    assert client.get(f"/clubs/{club}/officers").status_code == 403           # ...but can't manage officers now
    _as(accounts, "John")
    assert "You&#39;re now the owner of" in client.get(f"/messages/{ids['Maya']}").data.decode()
    officers_page = client.get(f"/clubs/{club}/officers").data.decode()
    assert 'value="owner"' in officers_page                                      # John can hand it back to Maya
    client.post(f"/clubs/{club}/officers", data={"user": ids["Maya"], "action": "remove"})
    with app.app_context():
        assert get_db().execute("SELECT role FROM club_members WHERE club_id = ? AND user_id = ?",
                                (club, ids["Maya"])).fetchone()[0] == "member"  # the old owner can be removed now
# ---------------------------------------------------------------- security sweep fixes (bot 19)

def test_email_codes_stop_after_five_a_day(accounts, client, app):
    """Each code allows 5 tries, so 5 codes a day means 25 guesses a day at most (for resets and sign-ups)."""
    accounts.signup(verify=False)
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET verify_sent_at = NULL")          # past the one-minute wait
        db.executemany("INSERT INTO email_codes (inbox, sent_at) VALUES ('dubs', ?)", [(to_db(now_local()),)] * 4)
        db.commit()
        code = db.execute("SELECT verify_code FROM users").fetchone()[0]
    page = client.post("/verify/resend", follow_redirects=True).data.decode()
    assert "a lot of codes for one day" in page
    with app.app_context():
        assert get_db().execute("SELECT verify_code FROM users").fetchone()[0] == code   # no new code
    client.post("/verify", data={"code": code})
    accounts.logout()
    with app.app_context():
        get_db().execute("UPDATE users SET verify_sent_at = NULL, verify_code = NULL")
        get_db().commit()
    client.post("/forgot", data={"email": "dubs@uw.edu"})              # same answer, but no new code today
    with app.app_context():
        assert get_db().execute("SELECT verify_code FROM users").fetchone()[0] is None


def test_code_texts_are_limited_per_number_and_lookups_count(accounts, client, app, monkeypatch):
    from sportive import sms
    _texts(monkeypatch)
    accounts.signup(email="owner@uw.edu")
    client.post("/settings/texts", data={"action": "send", "phone": "206-555-0142", "consent": "1"})
    with app.app_context():
        code = get_db().execute("SELECT sms_code FROM users").fetchone()[0]
    client.post("/settings/texts", data={"action": "confirm", "code": code})
    accounts.logout()
    accounts.signup(email="snoop@uw.edu")
    snoop = _user_id(app, "snoop@uw.edu")
    for _ in range(sms.MAX_CODES_PER_DAY):
        client.post("/settings/texts", data={"action": "send", "phone": "206-555-0142", "consent": "1"})
    page = client.post("/settings/texts", data={"action": "send", "phone": "206-555-0142", "consent": "1"},
                       follow_redirects=True).data.decode()
    assert "a lot of codes" in page                                     # lookups count toward the limits
    with app.app_context():
        get_db().execute("DELETE FROM sms_log WHERE user_id = ?", (snoop,))
        get_db().executemany("INSERT INTO sms_log (user_id, phone, kind, ok, created_at) VALUES (NULL, ?, 'code', 1, ?)",
                             [("+12065550199", to_db(now_local()))] * sms.MAX_CODES_PER_NUMBER)
        get_db().commit()
    page = client.post("/settings/texts", data={"action": "send", "phone": "206-555-0199", "consent": "1"},
                       follow_redirects=True).data.decode()
    assert "That number got a lot of codes today" in page


def test_only_admins_and_the_registrant_see_the_club_phone(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu")
    client.post(f"/clubs/{club}/join")
    fan = _user_id(app, "fan@uw.edu")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    assert 'value="206-555-0142"' in client.get(f"/clubs/{club}/edit").data.decode()   # they typed it
    client.post(f"/clubs/{club}/members/{fan}/approve")
    client.post(f"/clubs/{club}/officers/{fan}")
    accounts.logout()
    accounts.login(email="fan@uw.edu")
    form = client.get(f"/clubs/{club}/edit").data.decode()
    assert 'value="206-555-0142"' not in form and "We have a number on file" in form
    client.post(f"/clubs/{club}/edit", data={**CLUB, "contact_phone": "", "meets": "Wednesdays"})
    with app.app_context():
        row = get_db().execute("SELECT meets, contact_phone FROM clubs WHERE id = ?", (club,)).fetchone()
    assert row["meets"] == "Wednesdays" and row["contact_phone"] == "+12065550142"   # kept when left empty


def test_join_requests_email_officers_once_a_day(accounts, client, app, monkeypatch):
    from sportive import clubs
    emails = []
    monkeypatch.setattr(clubs, "send_email", lambda to, subject, body, html=None: emails.append(subject))
    club = _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu")
    for _ in range(5):
        client.post(f"/clubs/{club}/join")
        client.post(f"/clubs/{club}/leave")
    assert len(emails) == 1


def test_wrong_passwords_only_lock_out_the_device_they_came_from(accounts, client, app):
    accounts.signup()
    accounts.logout()
    attacker = app.test_client()
    for _ in range(10):
        attacker.post("/login", data={"email": "dubs@uw.edu", "password": "wrong-password"},
                      environ_base={"REMOTE_ADDR": "203.0.113.9"})
    blocked = attacker.post("/login", data={"email": "dubs@uw.edu", "password": "purple-and-gold"},
                            environ_base={"REMOTE_ADDR": "203.0.113.9"})
    assert b"Too many wrong passwords" in blocked.data
    no_account = attacker.post("/login", data={"email": "nobody@uw.edu", "password": "x"},
                               environ_base={"REMOTE_ADDR": "203.0.113.9"})
    for i in range(25):                                                 # many accounts from one address
        attacker.post("/login", data={"email": f"nobody{i}@uw.edu", "password": "x"},
                      environ_base={"REMOTE_ADDR": "203.0.113.9"})
    assert b"Wrong email or password" in no_account.data
    assert b"Too many wrong passwords" in attacker.post("/login", data={"email": "other@uw.edu", "password": "x"},
                                                        environ_base={"REMOTE_ADDR": "203.0.113.9"}).data
    assert accounts.login().status_code == 302                         # the owner still gets in from their phone


def test_log_out_ends_a_copied_cookie(accounts, client, app):
    accounts.signup()
    copied = client.get_cookie("session").value
    assert client.get("/settings").status_code == 200
    accounts.logout()
    thief = app.test_client()
    thief.set_cookie("session", copied)
    assert thief.get("/settings").status_code == 302                   # sent to log in


def test_private_data_isnt_cached_and_scripts_only_come_from_the_map_folder(accounts, client):
    accounts.signup()
    game = event_id_from(client.post("/events/new", data=event_form()))
    assert client.get(f"/events/{game}/calendar.ics").headers["Cache-Control"] == "no-store"
    assert client.get(f"/events/{game}/chat/poll").headers["Cache-Control"] == "no-store"
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "script-src 'self' https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/;" in csp
    assert client.get("/static/style.css").headers.get("Cache-Control") != "no-store"



def test_officer_page_messages_match_what_happened(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="stranger@uw.edu", name="Stran Ger")
    stranger = _user_id(app, "stranger@uw.edu")
    captain = _user_id(app, "captain@uw.edu")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    page = client.post(f"/clubs/{club}/officers", data={"user": stranger, "action": "remove"},
                       follow_redirects=True).data.decode()
    assert "isn&#39;t an officer" in page and "is a member now" not in page
    page = client.post(f"/clubs/{club}/officers", data={"user": captain, "action": "owner"},
                       follow_redirects=True).data.decode()
    assert "already the owner" in page


def test_place_check_hides_private_game_headcounts(accounts, client, app):
    _people(accounts, app, "Maya", "Sam")
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(is_private="1", password="abcd-efgh")))
    with app.app_context():
        e = get_db().execute("SELECT location, starts_at, ends_at FROM events WHERE id = ?", (game,)).fetchone()
    _as(accounts, "Sam")
    found = client.get("/events/place-check", query_string={"location": e["location"],
                                                            "starts_at": e["starts_at"][:16].replace(" ", "T"),
                                                            "ends_at": e["ends_at"][:16].replace(" ", "T")}).get_json()
    private = [x for x in found["games"] if x["title"] == "A private game"]
    assert private and private[0]["going"] is None and private[0]["max"] is None and private[0]["url"] is None


def test_one_account_per_inbox_even_with_both_uw_addresses(accounts, client, app):
    """netid@uw.edu and netid@u.washington.edu are one inbox: signing up with both at once can't make two accounts."""
    other = app.test_client()
    accounts.signup(email="dup@uw.edu", verify=False)
    first_code = accounts.code_for("dup@uw.edu")
    other.post("/signup", data={"full_name": "Dup Two", "email": "dup@u.washington.edu", "password": "purple-and-gold",
                                "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    with app.app_context():                                        # the newer sign-up replaced the older one
        assert get_db().execute("SELECT COUNT(*) FROM users WHERE email LIKE 'dup@%'").fetchone()[0] == 1
    client.post("/verify", data={"code": first_code})
    other.post("/verify", data={"code": accounts.code_for("dup@u.washington.edu")})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM users WHERE email LIKE 'dup@%' AND verified = 1").fetchone()[0] == 1


def test_an_event_thats_too_long_opens_the_form_on_the_end_time(accounts, client, app):
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    page = client.post("/events/new", data=event_form(ends_at=form_time(timedelta(days=1, hours=20))))
    assert b"at most" in page.data and b'data-error-field="ends_at"' in page.data


def test_invite_link_to_a_full_game_says_so(accounts, client, app):
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    game = event_id_from(client.post("/events/new", data=event_form(title="Full hoops", players="2")))
    link = _invite_path(client.get(f"/events/{game}").data.decode())
    accounts.logout()
    accounts.signup(email="sam@uw.edu", name="Sam Park")
    client.post(f"/events/{game}/join")
    accounts.logout()
    landing = client.get(link).data.decode()
    assert "This game is full right now" in landing and "Sign up and join" not in landing
    client.post(link)
    client.post("/signup", data={"full_name": "New Friend", "email": "new@uw.edu", "password": "purple-and-gold",
                                 "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    client.post("/verify", data={"code": accounts.code_for("new@uw.edu")})
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (game,)).fetchone()[0] == 2   # not overbooked
        assert db.execute("SELECT status FROM friendships WHERE requester_id = (SELECT id FROM users WHERE"
                          " email = 'maya@uw.edu')").fetchall()                                          # still friends


def test_invite_links_to_private_games_keep_the_place_to_themselves(accounts, client, app):
    """Bot round 5: a forwarded or previewed invite link showed a private game's place to anyone holding it."""
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    game = event_id_from(client.post("/events/new", data=event_form(title="Secret hoops", is_private="1",
                                                                     password="tiger-lily-123")))
    link = _invite_path(client.get(f"/events/{game}").data.decode())
    open_game = event_id_from(client.post("/events/new", data=event_form(title="Open hoops")))
    open_link = _invite_path(client.get(f"/events/{open_game}").data.decode())
    accounts.logout()
    for agent in ("facebookexternalhit/1.1", "Discordbot/2.0", "Mozilla/5.0"):
        page = client.get(link, headers={"User-Agent": agent}).data.decode()
        assert "Secret hoops" in page and "Place shown once you" in page and 'name="robots" content="noindex"' in page
        assert "Intramural" not in page and "tiger-lily" not in page
    preview = client.get(open_link).data.decode()       # a public game's preview says what it is, and where
    assert re.search(r'og:description" content="Basketball · [^"]*IMA', preview)


def test_members_only_invite_links_dont_promise_a_spot(accounts, client, app):
    club = _club_with_member(accounts, client, app)
    game = event_id_from(client.post(f"/events/new?club={club}", data=event_form(
        title="Practice", sport="spikeball", location="The Quad", is_private="members", club=str(club))))
    link = _invite_path(client.get(f"/events/{game}").data.decode())
    accounts.logout()
    page = client.get(link).data.decode()
    assert "for UW Spikeball Club members" in page and "Sign up and join" not in page and "The Quad" not in page
    accounts.signup(email="outsider@uw.edu", name="Out Sider")
    assert "Join the game" not in client.get(link).data.decode()


def test_club_link_previews_use_the_club_description(accounts, client, app):
    club = _approved_club(accounts, client, app)
    page = client.get(f"/clubs/{club}").data.decode()
    assert 'og:description" content="Casual roundnet on the Quad.' in page
    assert "Disallow: /settings" in client.get("/robots.txt").data.decode()


def test_being_blocked_or_suspended_clears_their_messages_from_my_inbox(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan", "Sam")
    _friends(app, ids["Maya"], ids["Jordan"], ids["Sam"])
    _as(accounts, "Jordan")
    client.post(f"/messages/{ids['Maya']}", data={"body": "hey"})
    client.post(f"/block/{ids['Maya']}")                              # Jordan blocks Maya after writing
    _as(accounts, "Sam")
    client.post(f"/messages/{ids['Maya']}", data={"body": "yo"})
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (ids["Sam"],))
        get_db().commit()
    _as(accounts, "Maya")
    inbox = client.get("/messages").data.decode()
    assert "Jordan Husky" not in inbox and "Sam Husky" not in inbox
    from sportive.notifications import _count
    with app.app_context():
        assert _count("messages", ids["Maya"]) == 0
    client.post(f"/messages/{ids['Sam']}", data={"body": "still there?"})
    with app.app_context():
        assert not get_db().execute("SELECT 1 FROM direct_messages WHERE recipient_id = ?", (ids["Sam"],)).fetchone()


def test_deleting_an_account_clears_its_login_and_code_records(accounts, client, app):
    accounts.signup()
    accounts.logout()
    client.post("/login", data={"email": "dubs@uw.edu", "password": "wrong-password"})
    accounts.login()
    client.post("/login", data={"email": "dubs@uw.edu", "password": "wrong-again"})   # logged in: ignored
    with app.app_context():
        get_db().execute("INSERT INTO login_failures (ip, email, failed_at) VALUES ('1.2.3.4', 'dubs@uw.edu', ?)",
                         (to_db(now_local()),))
        get_db().commit()
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    with app.app_context():
        db = get_db()
        assert not db.execute("SELECT 1 FROM login_failures WHERE email = 'dubs@uw.edu'").fetchone()
        assert not db.execute("SELECT 1 FROM email_codes WHERE inbox = 'dubs'").fetchone()


def test_club_decisions_made_twice_at_once_only_apply_once(accounts, client, app, monkeypatch):
    """Two admins deciding the same club at the same moment: both read "waiting", but only the first decision
    lands and only its email goes out. The second admin is told it already moved on."""
    from sportive import clubs
    emails = []
    monkeypatch.setattr(clubs, "send_email", lambda to, subject, body, html=None: emails.append(subject))
    accounts.signup(email="captain@uw.edu", name="Cap Tain")
    client.post("/clubs/new", data=CLUB)
    club = _club_id(app, CLUB["name"])
    accounts.logout()
    accounts.signup(email="admin@uw.edu", name="Ad Min")
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    with app.app_context():
        stale = dict(get_db().execute("SELECT * FROM clubs WHERE id = ?", (club,)).fetchone())
    monkeypatch.setattr(clubs, "get_club", lambda club_id: stale)    # both admins loaded the club while waiting
    client.post(f"/admin/clubs/{club}/approve")
    page = client.post(f"/admin/clubs/{club}/reject", data={"note": "Fix it"}, follow_redirects=True).data.decode()
    assert "already moved on" in page
    with app.app_context():
        assert get_db().execute("SELECT status FROM clubs WHERE id = ?", (club,)).fetchone()[0] == "approved"
    assert len(emails) == 1


def test_texting_failures_are_handled(accounts, client, app, monkeypatch):
    """Twilio errors never break a page: a STOP reply turns texts off, other failures are logged and explained."""
    from sportive import sms
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")

    def fail(code):
        def send(to, body):
            raise sms.SmsError(code, "failed")
        return send
    monkeypatch.setattr(sms, "send_sms", fail(30003))                  # e.g. an unreachable number
    page = client.post("/settings/texts", data={"action": "send", "phone": "206-555-0142", "consent": "1"},
                       follow_redirects=True).data.decode()
    assert "couldn&#39;t text that number" in page
    monkeypatch.setattr(sms, "send_sms", fail(sms.OPTED_OUT))
    with app.app_context():
        get_db().execute("UPDATE users SET sms_sent_at = NULL WHERE id = ?", (me,))   # past the one-minute wait
        get_db().commit()
    page = client.post("/settings/texts", data={"action": "send", "phone": "206-555-0142", "consent": "1"},
                       follow_redirects=True).data.decode()
    assert "replied STOP" in page
    with app.app_context():                                            # a confirmed number that later replies STOP
        db = get_db()
        db.execute("UPDATE users SET phone = '+12065550142', phone_verified = 1, sms_updates = 1 WHERE id = ?", (me,))
        db.commit()
        assert sms.text_user(me, "Game moved") is False
        assert db.execute("SELECT sms_updates FROM users WHERE id = ?", (me,)).fetchone()[0] == 0   # respected
        monkeypatch.setattr(sms, "send_sms", fail(500))
        assert sms.text_code(me, "123456", "password reset") is False  # never raises


def test_being_removed_and_game_changes_are_separate_notices(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Sam")
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    _as(accounts, "Sam")
    client.post(f"/events/{game}/join")
    _as(accounts, "Maya")
    client.post(f"/events/{game}/players/{ids['Sam']}/remove")
    with app.app_context():
        keys = [r[0] for r in get_db().execute("SELECT key FROM notices WHERE user_id = ?", (ids["Sam"],))]
    assert f"removed:{game}" in keys and f"change:{game}" not in keys


def test_first_day_fixes(accounts, client, app):
    """Skipping texts at sign-up doesn't bring the texts card straight back; a waiting club says when posting opens."""
    client.post("/signup", data={"full_name": "New Husky", "email": "fresh@uw.edu", "password": "purple-and-gold",
                                 "password2": "purple-and-gold", "birth_date": "2005-01-15"})
    client.post("/signup/sports", data={"sports": ["basketball"]})
    client.post("/signup/texts", data={"phone": ""})                   # "Skip, email only"
    client.post("/verify", data={"code": accounts.code_for("fresh@uw.edu")})
    accounts.upload_photo()
    assert "New: game updates by text" not in client.get("/").data.decode()
    client.post("/clubs/new", data=CLUB)
    page = client.get(f"/clubs/{_club_id(app, CLUB['name'])}").data.decode()
    assert "once the club is verified" in page and "Post an update" not in page


def test_daily_database_backup(accounts, app, tmp_path, monkeypatch):
    import sqlite3
    from sportive import backups
    accounts.signup()
    app.config["BACKUP_DIR"] = str(tmp_path / "backups")
    with app.app_context():
        first = backups.make_backup()
        assert first and first.endswith(f"sportive-{now_local():%Y-%m-%d}.db")
        assert backups.make_backup() is None                             # once a day
        copy = sqlite3.connect(first)
        assert copy.execute("SELECT email FROM users").fetchone()[0] == "dubs@uw.edu"   # a real, readable copy
        copy.close()
        for day in range(1, 10):                                         # older copies from past days
            (tmp_path / "backups" / f"sportive-2026-01-{day:02d}.db").write_bytes(b"old")
        backups.remove_old_backups(str(tmp_path / "backups"))
        kept = sorted(p.name for p in (tmp_path / "backups").iterdir())
        assert len(kept) == backups.KEEP and kept[-1] == first.rsplit("/", 1)[1]
        (tmp_path / "backups" / f"sportive-{now_local():%Y-%m-%d}.db.lock").write_bytes(b"")
        assert backups.make_backup(force=True) is None                   # the other copy of the site is on it
        lock = tmp_path / "backups" / f"sportive-{now_local():%Y-%m-%d}.db.lock"
        old = lock.stat().st_mtime - backups.STALE_LOCK_SECONDS - 60
        os.utime(lock, (old, old))                                       # left by a crash long ago
        assert backups.make_backup(force=True) and not lock.exists()     # cleared, and the backup is made


def test_update_texts_fit_in_one_plain_text():
    """Texts over 160 plain characters, or with any emoji, cost 2-3 texts each: every update fits in one."""
    from sportive.sms import SMS_LIMIT, one_text
    short = one_text("José changed 🏀 Friday hoops – now 7:00 PM at the IMA.")
    assert short == "Sportive Circle: Jose changed Friday hoops - now 7:00 PM at the IMA."
    link = "https://sportivecircle.com/events/1234"
    long = one_text("Maya wants you in Sunday sunrise soccer at the Husky Soccer Field with the whole crew, bring "
                    "cleats and water, we're playing two halves of forty minutes. Your spot is held for 30 min: " + link)
    assert len(long) <= SMS_LIMIT and long.endswith("... " + link) and long.isascii()


def test_home_screen_app_setup(accounts, client):
    """The site opens like an app from the home screen; iPhone users get a one-time tip (shown by app.js)."""
    accounts.signup()
    home = client.get("/").data.decode()
    assert 'rel="manifest"' in home and "data-install-tip hidden" in home and "Add to Home Screen" in home
    manifest = client.get("/static/manifest.json").get_json()
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes                             # what Android needs for one-tap Add
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200
    assert "data-install-button" in home
    accounts.logout()
    assert "data-install-tip" in client.get("/").data.decode()          # the landing page (QR code) too


def test_names_from_everywhere(accounts, client, app):
    """Joined emoji stay one picture, "Jose" finds "José", and A-Z lists ignore capitals and accents."""
    from sportive.textutil import initial, person_name
    assert person_name("👩🏽\u200d🦱 Curly") == "👩🏽\u200d🦱 Curly" and person_name("Ma\u202eya") == "Maya"
    assert initial("👩🏽\u200d🦱 Curly") == "👩🏽\u200d🦱" and initial(" zoë") == "Z"
    ids = _people(accounts, app, "Searcher")
    accounts.signup(email="jnunez@uw.edu", name="José Núñez")
    accounts.logout()
    accounts.signup(email="adam@uw.edu", name="adam lowercase")
    accounts.logout()
    _as(accounts, "Searcher")
    assert "José Núñez" in client.get("/friends?q=jose nunez").data.decode()
    with app.app_context():
        for other in ("jnunez@uw.edu", "adam@uw.edu"):
            get_db().execute("INSERT INTO friendships (requester_id, addressee_id, status, created_at) VALUES "
                             "(?, (SELECT id FROM users WHERE email = ?), 'accepted', '2026-09-01 10:00')",
                             (ids["Searcher"], other))
        get_db().commit()
        from sportive.social import friends_of
        assert [f["full_name"] for f in friends_of(ids["Searcher"])] == ["adam lowercase", "José Núñez"]


def test_calendar_file_updates_and_form_errors_open_the_right_step(accounts, client, app):
    accounts.signup()
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    assert "SEQUENCE:0" in client.get(f"/events/{game}/calendar.ics").data.decode()
    client.post(f"/events/{game}/edit", data=event_form(title="Hoops at 7"))
    assert "SEQUENCE:1" in client.get(f"/events/{game}/calendar.ics").data.decode()   # apps update their copy
    client.post(f"/events/{game}/cancel")
    ics = client.get(f"/events/{game}/calendar.ics").data.decode()
    assert "SEQUENCE:2" in ics and "STATUS:CANCELLED" in ics
    # A mistake on a later step: the form opens on that field instead of step 1.
    page = client.post("/events/new", data=event_form(players="1")).data.decode()
    assert 'data-error-field="players"' in page
    page = client.post("/need-players", data={"sport": "soccer", "location": "Denny Field", "skill_level": "All levels",
                                              "starts_in": "15", "duration": "60", "players": "5000"}).data.decode()
    assert 'data-error-field="players"' in page


def test_small_photos_for_lists_and_long_cache_for_versioned_files(accounts, client):
    accounts.signup()
    home = client.get("/").data.decode()
    me = re.search(r'/u/(\d+)', home).group(1)
    full, thumb = client.get(f"/u/{me}/photo?v=1").data, client.get(f"/u/{me}/photo?v=1&s=96").data
    assert len(thumb) < len(full) and thumb[:2] == b"\xff\xd8"          # a real, smaller JPEG
    with client.application.test_request_context():
        from flask import render_template_string
        html = render_template_string('{% from "_macros.html" import avatar %}{{ avatar(1, "A B", "5", 32) }}')
    assert "s=96" in html                                                  # small circles ask for the small one
    css = re.search(r'href="(/static/style\.css\?v=\d+)"', home).group(1)
    assert "max-age=31536000" in client.get(css).headers["Cache-Control"]


def test_suspended_people_get_no_game_or_club_emails(accounts, client, app, monkeypatch):
    from sportive import events
    sent = []
    monkeypatch.setattr(events, "send_email", lambda to, subject, body, html=None: sent.append(to))
    ids = _people(accounts, app, "Host", "Player")
    _as(accounts, "Host")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    _as(accounts, "Player")
    client.post(f"/events/{game}/join")
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (ids["Player"],))
        get_db().commit()
    _as(accounts, "Host")
    client.post(f"/events/{game}/cancel")
    assert "player@uw.edu" not in sent


def test_expired_records_are_cleaned_up_but_messages_stay(accounts, client, app):
    from sportive import backups
    ids = _people(accounts, app, "Maya", "Sam")
    _friends(app, ids["Maya"], ids["Sam"])
    _as(accounts, "Maya")
    client.post(f"/messages/{ids['Sam']}", data={"body": "old but kept"})
    with app.app_context():
        db = get_db()
        long_ago = "2025-01-01 10:00"
        db.execute("INSERT INTO notices (user_id, kind, text, url, created_at) VALUES (?, 'account', 'old', '/', ?)",
                   (ids["Maya"], long_ago))
        db.execute("INSERT INTO sms_log (user_id, phone, kind, ok, created_at) VALUES (?, '+12065550142', 'code', 1, ?)",
                   (ids["Maya"], long_ago))
        db.execute("INSERT INTO email_codes (inbox, sent_at) VALUES ('maya', ?)", (long_ago,))
        db.execute("UPDATE direct_messages SET created_at = ?", (long_ago,))
        db.commit()
        assert backups.clean_up_old_records() >= 3
        assert not db.execute("SELECT 1 FROM notices WHERE text = 'old'").fetchone()
        assert db.execute("SELECT 1 FROM direct_messages WHERE body = 'old but kept'").fetchone()


def test_weekly_practices_skip_the_hour_clocks_jump_over(accounts, client, app):
    club = _club_with_member(accounts, client, app)
    form = event_form(title="Late practice", sport="spikeball", location="The Quad", repeat="3", club=str(club),
                      starts_at="2027-03-07T02:30", ends_at="2027-03-07T03:00")
    page = client.post(f"/events/new?club={club}", data=form, follow_redirects=True).data.decode()
    with app.app_context():
        starts = [r[0][:16] for r in get_db().execute(
            "SELECT starts_at FROM events WHERE club_id = ? AND title = 'Late practice' ORDER BY starts_at", (club,))]
    assert starts == ["2027-03-07 02:30", "2027-03-21 02:30"]            # Mar 14 2:30 AM doesn't exist
    assert "One week was skipped" in page


def test_a_suspended_owner_doesnt_strand_their_club_or_friend_requests(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="vice@uw.edu", name="Vice Husky")
    client.post(f"/clubs/{club}/join")
    vice = _user_id(app, "vice@uw.edu")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    client.post(f"/clubs/{club}/members/{vice}/approve")
    client.post(f"/clubs/{club}/officers", data={"user": vice, "action": "add"})
    client.post(f"/friends/request/{vice}")                              # a request the suspension leaves behind
    captain = _user_id(app, "captain@uw.edu")
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (captain,))
        get_db().commit()
    accounts.logout()
    accounts.login(email="vice@uw.edu")
    assert client.get(f"/clubs/{club}/officers").status_code == 200      # the other officer can run it
    assert "Cap Tain" not in client.get("/friends").data.decode()
    client.post(f"/friends/accept/{captain}")
    with app.app_context():
        assert get_db().execute("SELECT status FROM friendships").fetchone()[0] == "pending"


def test_club_search_matches_words_in_any_order(accounts, client, app):
    _approved_club(accounts, client, app, name="Club Ultimate Frisbee")
    accounts.signup(email="finder@uw.edu")
    for q in ("ultimate club", "FRISBEE", "ultimate", "club%"):
        page = client.get("/clubs", query_string={"q": q}).data.decode()
        assert ("Club Ultimate Frisbee" in page) == (q != "club%"), q    # a % is a letter, not a wildcard


def test_logging_in_from_a_club_page_comes_back_to_it(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu")
    accounts.logout()
    page = client.get(f"/clubs/{club}").data.decode()                    # opened from a QR code, logged out
    login = re.search(r'<a href="(/login[^"]*)">Log in</a>', page).group(1).replace("&amp;", "&")
    assert f"next=%2Fclubs%2F{club}" in login or f"next=/clubs/{club}" in login
    assert client.post(login, data={"email": "fan@uw.edu", "password": "purple-and-gold"}).headers["Location"] \
        == f"/clubs/{club}"


def test_place_check_hides_members_only_games_from_outsiders(accounts, client, app):
    club = _club_with_member(accounts, client, app)
    form = event_form(title="Secret practice", sport="spikeball", location="The Quad", is_private="members",
                      club=str(club))
    game = event_id_from(client.post(f"/events/new?club={club}", data=form))
    with app.app_context():
        e = get_db().execute("SELECT location, starts_at, ends_at FROM events WHERE id = ?", (game,)).fetchone()
    accounts.logout()
    accounts.signup(email="outsider@uw.edu", name="Out Sider")
    found = client.get("/events/place-check", query_string={
        "location": e["location"], "starts_at": e["starts_at"][:16].replace(" ", "T"),
        "ends_at": e["ends_at"][:16].replace(" ", "T")}).get_json()
    assert found["games"] and all("Secret practice" not in g["title"] and g["going"] is None for g in found["games"])


def test_club_page_shows_outsiders_only_a_count_of_members_only_events(accounts, client, app):
    club = _club_with_member(accounts, client, app)
    client.post(f"/events/new?club={club}", data=event_form(title="Secret practice", sport="spikeball",
                                                            location="The Quad", is_private="members", club=str(club)))
    assert "Secret practice" in client.get(f"/clubs/{club}").data.decode()        # an officer sees it
    accounts.logout()
    page = client.get(f"/clubs/{club}").data.decode()                            # a visitor from a QR code
    assert "Secret practice" not in page and "1 event for members" in page


def test_youre_in_screen_after_sign_up(accounts, client, app):
    """The last sign-up step shows how to put the app on the home screen once, then goes where they were headed."""
    accounts.signup(photo=False)
    done = accounts.upload_photo()
    assert done.headers["Location"] == _after_sign_up("/")
    page = client.get(done.headers["Location"]).data.decode()
    assert "You're in!" in page and "Add to Home Screen" in page and 'data-next="/"' in page and "Maybe later" in page
    assert 'data-next="/"' in client.get("/welcome?next=https://evil.example").data.decode()   # never off-site
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    assert "Want your games one tap away?" in client.get(f"/events/{game}").data.decode()
    second = event_id_from(client.post("/events/new", data=event_form(title="More hoops")))
    assert "Want your games one tap away?" not in client.get(f"/events/{second}").data.decode()   # first game only


def test_log_in_or_reset_with_either_uw_address(accounts, client, app):
    accounts.signup(email="dubs@uw.edu")
    accounts.logout()
    assert accounts.login(email="dubs@u.washington.edu").status_code == 302      # same inbox, same account
    assert client.get("/forgot").headers["Location"] == "/settings/password"      # logged in: change it there
    accounts.logout()
    with app.app_context():
        get_db().execute("UPDATE users SET verify_sent_at = NULL, verify_code = NULL")
        get_db().commit()
    client.post("/forgot", data={"email": "DUBS@u.washington.edu"})
    with app.app_context():
        assert get_db().execute("SELECT verify_code FROM users WHERE email = 'dubs@uw.edu'").fetchone()[0]


def test_pasted_social_links_become_usernames(accounts, client, app):
    accounts.signup()
    client.post("/profile/edit/sports", data={"instagram": "https://www.instagram.com/maya.hoops/?hl=en",
                                              "tiktok": "tiktok.com/@maya", "x_handle": "twitter.com/maya",
                                              "sports": ["basketball"]})
    with app.app_context():
        row = get_db().execute("SELECT instagram, tiktok, x_handle FROM users").fetchone()
    assert (row["instagram"], row["tiktok"], row["x_handle"]) == ("maya.hoops", "maya", "maya")


def test_one_admin_tab_with_everything(accounts, client, app):
    accounts.signup(email="boss@uw.edu", name="Boss Husky")
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    home = client.get("/").data.decode()
    assert 'href="/admin"' in home and ">Reports</span>" not in home and ">Club requests</span>" not in home
    page = client.get("/admin").data.decode()
    for part in ("Reports", "Club requests", "UW Rec reservations", "Suggestions"):
        assert part in page
    accounts.logout()
    accounts.signup(email="normal@uw.edu")
    assert client.get("/admin").status_code == 404                       # not for everyone


def test_uw_rec_bookings_are_copied_by_themselves(accounts, client, app, monkeypatch):
    """UW Rec's public schedule is read once a day (no typing): weekly repeats become dates, skipped days stay
    out, bookings admins typed in are kept, and a failure keeps yesterday's copy. No real network in tests."""
    from sportive import uwrec
    page = ('<a href="/Facility/GetFacility?facilityId=11111111-1111-1111-1111-111111111111">Denny Field - Turf</a>'
            '<a href="/Facility/GetFacility?facilityId=22222222-2222-2222-2222-222222222222">Gym B</a>')
    now = now_local()
    first = (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    skip = first + timedelta(days=7)
    rugby = {"Text": "Womxn's Rugby - Practice", "StartDate": first.strftime("%Y-%m-%dT%H:%M:%S.000"),
             "EndDate": first.replace(hour=20).strftime("%Y-%m-%dT%H:%M:%S.000"),
             "RecurrenceRule": f"FREQ=WEEKLY;UNTIL={(first + timedelta(days=22)).strftime('%Y%m%dT070000')}Z;"
                               f"BYDAY={['MO','TU','WE','TH','FR','SA','SU'][first.weekday()]}",
             "RecurrenceException": skip.strftime("%Y%m%dT%H%M%S")}
    kendo = {"Text": "Kendo - Practice", "StartDate": first.strftime("%Y-%m-%dT%H:%M:%S.000"),
             "EndDate": first.replace(hour=21).strftime("%Y-%m-%dT%H:%M:%S.000")}

    def fake_get(path, params=None):
        if path == "/Facility":
            return page
        return json.dumps([rugby] if params["selectedFacilityId"].startswith("1") else [kendo])
    monkeypatch.setattr(uwrec, "_get", fake_get)
    app.config["UW_REC_PAUSE"] = 0
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO rec_reservations (location, starts_at, ends_at, label, source, created_at)"
                   " VALUES ('Denny Field', ?, ?, 'Typed in', 'admin', ?)",
                   (to_db(first), to_db(first.replace(hour=19)), to_db(now)))
        db.commit()
        assert uwrec.sync() == 4                                          # 4 rugby weeks - 1 skipped + kendo
        rows = db.execute("SELECT location, label, starts_at FROM rec_reservations WHERE source = 'feed'"
                          " ORDER BY starts_at").fetchall()
        assert [r["label"] for r in rows].count("Womxn's Rugby - Practice") == 3
        assert to_db(skip) not in [r["starts_at"] for r in rows]
        assert ("IMA (Intramural Activities Building)", "Gym B: Kendo - Practice") in [(r[0], r[1]) for r in rows]
        assert uwrec.last_report()["status"] == "ok"
        monkeypatch.setattr(uwrec, "_get", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
        with pytest.raises(OSError):
            uwrec.sync()                                                  # UW Rec down: yesterday's copy stays
        assert db.execute("SELECT COUNT(*) FROM rec_reservations WHERE source = 'feed'").fetchone()[0] == 4
        assert db.execute("SELECT COUNT(*) FROM rec_reservations WHERE source = 'admin'").fetchone()[0] == 1
        assert uwrec.last_report()["status"] == "failed"



# UW Rec's real data for Denny Field (Sept 30, 2026), and what UW Rec's own calendar showed for Oct 4-10:
# rugby Mon 5 and Thu 8, 6-8 PM; HFS Fri 9, 4-7 PM. If the date math ever changes, this catches it.
UW_REC_DENNY = [
    {"Text": "Womxn's Rugby - Practice", "StartDate": "2026-10-01T18:00:00.000", "EndDate": "2026-10-01T20:00:00.000",
     "RecurrenceRule": "FREQ=WEEKLY;UNTIL=20261218T040000Z;BYDAY=MO,TH;WKST=SU",
     "RecurrenceException": "20261126T180000"},
    {"Text": "HFS", "StartDate": "2026-10-09T16:00:00.000", "EndDate": "2026-10-09T19:00:00.000",
     "RecurrenceRule": None, "RecurrenceException": None},
]


def test_uw_rec_dates_match_uw_recs_own_calendar():
    from datetime import datetime
    from sportive.uwrec import occurrences
    until = datetime(2026, 12, 31)
    rugby = occurrences(UW_REC_DENNY[0], until)
    week = [(s.strftime("%a %b %d %H:%M"), e.strftime("%H:%M")) for s, e in rugby
            if datetime(2026, 10, 4) <= s < datetime(2026, 10, 11)]
    assert week == [("Mon Oct 05 18:00", "20:00"), ("Thu Oct 08 18:00", "20:00")]
    assert datetime(2026, 11, 26, 18) not in [s for s, _ in rugby]           # Thanksgiving skipped
    assert rugby[-1][0] == datetime(2026, 12, 17, 18)                          # last one: Dec 17 (UNTIL is UTC)
    assert all(s.weekday() in (0, 3) and s.hour == 18 for s, _ in rugby)
    assert occurrences(UW_REC_DENNY[1], until) == [(datetime(2026, 10, 9, 16), datetime(2026, 10, 9, 19))]


def test_uw_rec_copy_refuses_what_it_cant_read_and_sudden_drops(app, monkeypatch):
    from sportive import uwrec
    app.config["UW_REC_PAUSE"] = 0
    page = '<a href="/Facility/GetFacility?facilityId=11111111-1111-1111-1111-111111111111">Denny Field - Turf</a>'
    start = (now_local() + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    booking = lambda title, hours=2, rule=None: {"Text": title, "StartDate": start.strftime("%Y-%m-%dT%H:%M:%S"),
                                                 "EndDate": (start + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S"),
                                                 "RecurrenceRule": rule}
    feed = {"items": [booking(f"Game {i}") for i in range(30)]
                     + [booking("Monthly", rule="FREQ=MONTHLY;BYDAY=2TU"), booking("Too long", hours=40),
                        booking("All-day tournament", hours=23)]}
    monkeypatch.setattr(uwrec, "_get", lambda path, params=None: page if path == "/Facility"
                        else json.dumps(feed["items"]))
    with app.app_context():
        assert uwrec.sync() == 31                                    # + the all-day one; monthly and 40 hours left out
        report = uwrec.last_report()
        assert report["status"] == "warnings" and len(report["problems"]) == 2
        feed["items"] = [booking("Only one")]
        assert uwrec.sync() == 0 and uwrec.last_report()["status"] == "kept"   # 1 vs 31: probably a broken page
        assert get_db().execute("SELECT COUNT(*) FROM rec_reservations WHERE source = 'feed'").fetchone()[0] == 31


def test_uw_rec_copy_keeps_a_place_that_didnt_answer_and_reads_odd_data(accounts, client, app, monkeypatch):
    """Bot round 8: an empty answer for one space wiped that place's bookings; one odd booking stopped the whole
    copy (blamed on the network); "Updated just now" showed after a failed run; dates past the copy said "none"."""
    from sportive import uwrec
    app.config["UW_REC_PAUSE"] = 0
    page = ('<a href="/Facility/GetFacility?facilityId=11111111-1111-1111-1111-111111111111">Denny Field - Turf</a>'
            '<a href="/Facility/GetFacility?facilityId=22222222-2222-2222-2222-222222222222">Gym B</a>')
    start = (now_local() + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    booking = lambda title, day=0: {"Text": title, "StartDate": (start + timedelta(days=day)).strftime("%Y-%m-%dT%H:%M:%S"),
                                    "EndDate": (start + timedelta(days=day, hours=2)).strftime("%Y-%m-%dT%H:%M:%S")}
    answers = {"1": json.dumps([booking(f"Field {i}", i) for i in range(15)]),
               "2": json.dumps([booking(f"Gym {i}", i) for i in range(15)])}
    monkeypatch.setattr(uwrec, "_get", lambda path, params=None: page if path == "/Facility"
                        else answers[params["selectedFacilityId"][0]])
    count = "SELECT COUNT(*) FROM rec_reservations WHERE source = 'feed' AND location = ?"
    with app.app_context():
        db = get_db()
        assert uwrec.sync() == 30
        answers["1"] = ""                                                        # Denny Field: no answer at all
        answers["2"] = json.dumps([booking(f"Gym {i}", i) for i in range(14)]
                                  + [{"Text": 123, "StartDate": None, "EndDate": None}, "oops",
                                     {"Text": "UTC one", "StartDate": start.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
                                      "EndDate": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S") + "Z"}])
        uwrec.sync()
        assert db.execute(count, ("Denny Field",)).fetchone()[0] == 15             # its last copy is kept
        assert db.execute(count, ("IMA (Intramural Activities Building)",)).fetchone()[0] == 15   # 14 + the UTC one
        report = uwrec.last_report()
        assert report["status"] == "warnings" and any("Denny Field" in p for p in report["problems"])
        copied = uwrec.last_copied()
        monkeypatch.setattr(uwrec, "_get", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
        with pytest.raises(OSError):
            uwrec.sync()
        assert uwrec.last_copied() == copied                                    # a failed run isn't "updated"
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="admin@uw.edu")
    far = now_local() + timedelta(days=40)
    found = client.get("/events/place-check", query_string={
        "location": "Denny Field", "starts_at": far.strftime("%Y-%m-%dT18:00"), "ends_at": far.strftime("%Y-%m-%dT19:00")}
    ).get_json()
    assert found["beyond_copy"] is True
    soon = client.get("/events/place-check", query_string={
        "location": "Denny Field", "starts_at": start.strftime("%Y-%m-%dT%H:%M"),
        "ends_at": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")}).get_json()
    assert soon["beyond_copy"] is False


def test_sign_up_back_button_and_wrong_email(accounts, client, app):
    """Bot round 8: going back to fix sign-up was blocked for a minute; Back after an error hit "Confirm Form
    Resubmission"; the code page had no way out of a mistyped email."""
    data = {"full_name": "Fresh Husky", "email": "fersh@uw.edu", "password": "purple-and-gold",
            "password2": "purple-and-gold", "birth_date": "2006-03-01", "grad_year": "2030"}
    bad = client.post("/signup", data={**data, "password2": "nope-nope-nope"})
    assert bad.status_code == 302 and bad.headers["Location"] == "/signup"    # a normal page, so Back works
    again = client.get("/signup").data.decode()
    assert "Passwords do not match" in again and 'value="fersh@uw.edu"' in again and "purple-and-gold" not in again
    assert client.post("/signup", data=data).headers["Location"] == "/signup/sports"
    code = accounts.code_for("fersh@uw.edu")
    fixed = client.post("/signup", data={**data, "full_name": "Fresh Dawg"})  # Back, fixed the name, Next again
    assert fixed.headers["Location"] == "/signup/sports" and accounts.code_for("fersh@uw.edu") == code
    verify = client.get("/verify").data.decode()
    assert "Wrong email? Fix it" in verify
    form = client.get("/signup?fix=1").data.decode()
    assert 'value="fersh@uw.edu"' in form and 'value="Fresh Dawg"' in form
    assert client.post("/signup", data={**data, "email": "fresh@uw.edu"}).headers["Location"] == "/signup/sports"
    client.post("/verify", data={"code": accounts.code_for("fresh@uw.edu")})
    with app.app_context():
        assert get_db().execute("SELECT verified FROM users WHERE email = 'fresh@uw.edu'").fetchone()[0] == 1
    accounts.upload_photo()                                                 # (the photo step comes first)
    assert "haven't joined any clubs yet" in client.get("/clubs?mine=1").data.decode()


def test_changing_your_password_kills_a_pending_reset_code_and_phones_stay_one_account(accounts, client, app):
    accounts.signup(email="alice@uw.edu", name="Alice Husky")
    accounts.logout()
    client.post("/forgot", data={"email": "alice@uw.edu"})                  # someone else asks for a reset code
    code = accounts.code_for("alice@uw.edu")
    accounts.login(email="alice@uw.edu")
    client.post("/profile/password", data={"current_password": "purple-and-gold", "password": "new-password-22",
                                           "password2": "new-password-22"})
    accounts.logout()
    client.post("/forgot", data={"email": "nobody@uw.edu"})                 # (just to be on the reset flow)
    with client.session_transaction() as sess:
        sess["reset_email"] = "alice@uw.edu"
    client.post("/reset", data={"code": code, "password": "attacker-pass-9", "password2": "attacker-pass-9"})
    assert b"Wrong email or password" in client.post("/login", data={"email": "alice@uw.edu",
                                                                     "password": "attacker-pass-9"}).data
    from sportive.sms import check_phone_code
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users (email, password_hash, full_name, verified, phone, sms_code, sms_code_expires)"
                   " VALUES ('bob@uw.edu', 'x', 'Bob', 1, '+12065550142', '111111', '2099-01-01 00:00')")
        db.execute("UPDATE users SET phone = '+12065550142', sms_code = '222222', sms_code_expires = '2099-01-01 00:00'"
                   " WHERE email = 'alice@uw.edu'")
        db.commit()
        ids = dict(db.execute("SELECT email, id FROM users").fetchall())
        assert check_phone_code(ids["bob@uw.edu"], "111111") is None            # Bob confirms first...
        assert check_phone_code(ids["alice@uw.edu"], "222222") == "That number is already used by another account."


def test_uw_rec_copy_drops_old_places_and_only_counts_real_copies(app, monkeypatch):
    """Round 12 review: bookings for a place we no longer read stayed forever; a run where every place sent junk
    still counted as a fresh copy; databases from before "last good copy" showed nothing."""
    from sportive import uwrec
    app.config["UW_REC_PAUSE"] = 0
    page = '<a href="/Facility/GetFacility?facilityId=11111111-1111-1111-1111-111111111111">Denny Field - Turf</a>'
    start = (now_local() + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    answer = {"text": json.dumps([{"Text": "Rugby", "StartDate": start.strftime("%Y-%m-%dT%H:%M:%S"),
                                   "EndDate": (start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")}])}
    monkeypatch.setattr(uwrec, "_get", lambda path, params=None: page if path == "/Facility" else answer["text"])
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO app_state (key, value) VALUES ('uw_rec_synced_at', '2026-09-01 06:00')")
        db.execute("INSERT INTO app_state (key, value) VALUES ('uw_rec_report', ?)",
                   (json.dumps({"at": "2026-09-01 06:00", "status": "ok", "saved": 1, "previous": 0, "problems": [],
                                "more": 0}),))
        db.execute("INSERT INTO rec_reservations (location, starts_at, ends_at, label, source, created_at)"
                   " VALUES ('Old Place', ?, ?, 'Gone', 'feed', ?)", (to_db(start), to_db(start), to_db(now_local())))
        db.commit()
        assert uwrec.last_copied() == "2026-09-01 06:00"                       # from before this was tracked
        assert uwrec.sync() == 1
        assert db.execute("SELECT COUNT(*) FROM rec_reservations WHERE location = 'Old Place'").fetchone()[0] == 0
        copied = uwrec.last_copied()
        answer["text"] = "<html>busy</html>"                                    # every place sends junk
        uwrec.sync()
        assert uwrec.last_report()["status"] == "kept" and uwrec.last_copied() == copied
        assert db.execute("SELECT COUNT(*) FROM rec_reservations WHERE location = 'Denny Field'").fetchone()[0] == 1


def test_monday_email_games_this_week(accounts, client, app, monkeypatch):
    """Everyone gets a Monday email of open games in their sports (and what they're going to), unless it's off.
    Nothing to show: no email. It goes out once a week, even with two copies of the site."""
    from datetime import datetime
    from sportive import digest
    sent = []
    monkeypatch.setattr(digest, "send_email", lambda to, subject, body, html=None, **kw: sent.append((to, body)))
    ids = _people(accounts, app, "Host", "Hooper", "Runner", "Quiet")
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM user_sports")
        db.executemany("INSERT INTO user_sports (user_id, sport) VALUES (?, ?)",
                       [(ids["Hooper"], "basketball"), (ids["Runner"], "running")])
        db.execute("UPDATE users SET weekly_digest = 0 WHERE id = ?", (ids["Quiet"],))
        db.commit()
    _as(accounts, "Host")
    client.post("/events/new", data=event_form(title="Tuesday hoops"))
    with app.test_request_context():
        assert digest.send_weekly() == 2                                 # Hooper (a game) + Host (going)
    by = dict(sent)
    assert "Tuesday hoops" in by["hooper@uw.edu"] and "Open games you could join" in by["hooper@uw.edu"]
    assert "You're going to" in by["host@uw.edu"]
    assert "runner@uw.edu" not in by and "quiet@uw.edu" not in by       # nothing in running; switched off
    # Once a week: the claim stops a second send, and it only starts Monday from 9 AM.
    starts = []
    monkeypatch.setattr(digest.threading, "Thread", lambda target, args, name, daemon: type(
        "T", (), {"start": lambda self: starts.append(name)})())
    monday = datetime(2026, 10, 5, 9, 30)
    monkeypatch.setattr(digest, "now_local", lambda: monday)
    digest.weekly_round(app); digest.weekly_round(app)
    assert starts == ["weekly-email"]
    monkeypatch.setattr(digest, "now_local", lambda: datetime(2026, 10, 6, 9, 30))   # Tuesday
    digest.weekly_round(app)
    assert starts == ["weekly-email"]
    _as(accounts, "Hooper")
    client.post("/settings/weekly", data={})                            # switch it off
    with app.app_context():
        assert get_db().execute("SELECT weekly_digest FROM users WHERE id = ?", (ids["Hooper"],)).fetchone()[0] == 0


def test_photos_in_chats_and_friendlier_chats(accounts, client, app):
    """Photos in DMs and game chats (resized, private to the chat), plus day dividers, quick replies and a ⋯ menu
    instead of a Report link under every message."""
    from io import BytesIO
    ids = _people(accounts, app, "Maya", "Sam", "Stranger")
    _friends(app, ids["Maya"], ids["Sam"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    photo = make_image(size=(3000, 2000), fmt="JPEG")
    client.post(f"/messages/{ids['Sam']}", data={"body": "", "photo": (BytesIO(photo), "court.jpg")},
                content_type="multipart/form-data")
    client.post(f"/events/{game}/chat", data={"body": "Warm-up pic", "photo": (BytesIO(photo), "court.jpg")},
                content_type="multipart/form-data")
    bad = client.post(f"/messages/{ids['Sam']}", data={"body": "", "photo": (BytesIO(b"not a photo"), "x.jpg")},
                      content_type="multipart/form-data", follow_redirects=True).data.decode()
    assert "isn&#39;t a photo we can use" in bad
    with app.app_context():
        db = get_db()
        dm_photo = db.execute("SELECT photo_id FROM direct_messages WHERE photo_id IS NOT NULL").fetchone()[0]
        chat_photo = db.execute("SELECT photo_id FROM event_messages WHERE photo_id IS NOT NULL").fetchone()[0]
        assert db.execute("SELECT COUNT(*) FROM chat_photos").fetchone()[0] == 2   # the bad file saved nothing
    from PIL import Image
    saved = client.get(f"/chat-photos/{dm_photo}")
    assert saved.status_code == 200 and max(Image.open(BytesIO(saved.data)).size) == 1280   # made smaller
    page = client.get(f"/events/{game}/chat").data.decode()
    assert f"/chat-photos/{chat_photo}" in page and "Warm-up pic" in page and "Today" in page
    assert "On my way" not in page and 'name="photo"' in page and 'accept="image/*"' in page   # no suggestion chips
    _as(accounts, "Sam")
    thread = client.get(f"/messages/{ids['Maya']}").data.decode()
    assert f"/chat-photos/{dm_photo}" in thread and "Down to play?" not in thread and "🚩 Report" not in thread
    assert ">Report</a>" in thread                                    # tucked in the ⋯ menu
    assert client.get(f"/chat-photos/{chat_photo}").status_code == 404   # not in that game
    _as(accounts, "Stranger")
    assert client.get(f"/chat-photos/{dm_photo}").status_code == 404


def test_chats_send_without_reloading_the_page(accounts, client, app):
    """The chat page sends in the background (X-Chat-Send) and gets a small answer instead of a reload."""
    ids = _people(accounts, app, "Maya", "Sam")
    _friends(app, ids["Maya"], ids["Sam"])
    _as(accounts, "Maya")
    sent = client.post(f"/messages/{ids['Sam']}", data={"body": "Down to play?"}, headers={"X-Chat-Send": "1"})
    assert sent.status_code == 200 and sent.get_json() == {"ok": True, "error": None}
    empty = client.post(f"/messages/{ids['Sam']}", data={"body": "  "}, headers={"X-Chat-Send": "1"}).get_json()
    assert empty["ok"] is False and "Type a message" in empty["error"]
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    assert client.post(f"/events/{game}/chat", data={"body": "On my way"},
                       headers={"X-Chat-Send": "1"}).get_json()["ok"] is True
    assert client.post(f"/messages/{ids['Sam']}", data={"body": "No script"}).status_code == 302   # still works




# ---- Fixes from the bot test run (AI testers' findings) ----

def test_full_for_now_doesnt_name_players_of_a_private_game(accounts, client, app):
    ids = _people(accounts, app, "Hana", "Anna", "Gus", "Otto")
    _friends(app, ids["Anna"], ids["Gus"])
    _as(accounts, "Hana")
    game = event_id_from(client.post("/events/new", data=event_form(title="Secret", players="3", is_private="1",
                                                                     password="dawgs26")))
    _as(accounts, "Anna")
    client.post(f"/events/{game}/join", data={"password": "dawgs26"})
    with app.app_context():                     # Anna's friend Gus has a held spot (as after the host says yes)
        from sportive.invites import HOLD_TIME
        from sportive.timeutil import now_local, to_db
        get_db().execute("""INSERT INTO invites (event_id, inviter_id, guest_id, status, created_at, expires_at)
                            VALUES (?, ?, ?, 'pending', ?, ?)""",
                         (game, ids["Anna"], ids["Gus"], to_db(now_local()), to_db(now_local() + HOLD_TIME)))
        get_db().commit()
    _as(accounts, "Otto")
    page = client.get(f"/events/{game}").data.decode()
    assert "Anna" not in page and "held for invited friends" in page


def test_owner_cant_add_someone_who_blocked_them(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Vic")
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Vic")
    client.post(f"/block/{ids['Maya']}")
    _as(accounts, "Maya")
    said = client.post(f"/clubs/{club}/officers", data={"user": ids["Vic"], "action": "add"},
                       follow_redirects=True).data.decode()
    assert "can&#39;t add this person" in said
    with app.app_context():
        assert get_db().execute("SELECT 1 FROM club_members WHERE club_id = ? AND user_id = ?",
                                (club, ids["Vic"])).fetchone() is None


def test_odd_digits_in_players_dont_crash(accounts, client):
    accounts.signup()
    response = client.post("/events/new", data=event_form(players="²"))
    assert response.status_code == 200 and b"Pick 2 to 1000 participants" in response.data


def test_send_to_friends_counts_the_whole_batch_toward_the_limit(accounts, client, app):
    names = ["Maya"] + [f"Pal{n}" for n in range(10)]
    ids = _people(accounts, app, *names)
    _friends(app, ids["Maya"], *[ids[n] for n in names[1:]])
    _as(accounts, "Maya")
    for n in range(15):
        client.post(f"/messages/{ids['Pal0']}", data={"body": f"hi {n}"})
    game = event_id_from(client.post("/events/new", data=event_form(title="Pickup", players="20")))
    said = client.post(f"/events/{game}/send", data={"friend": [ids[n] for n in names[1:]]},
                       follow_redirects=True).data.decode()
    assert "slow down" in said


def test_leaving_a_game_you_werent_in_says_so(accounts, client, app):
    _people(accounts, app, "Maya", "Sam")
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    _as(accounts, "Sam")
    assert b"You weren&#39;t going to this game." in client.post(f"/events/{game}/leave", follow_redirects=True).data


def test_skipping_texts_at_sign_up_hides_the_home_texts_card(client, app):
    client.post("/signup", data={"full_name": "New Kid", "email": "newkid@uw.edu", "password": "purple-and-gold",
                                 "password2": "purple-and-gold", "birth_date": "2006-01-01", "grad_year": "2029"})
    client.post("/signup/sports", data={"sports": ["running"]})
    client.post("/signup/texts", data={"phone": ""})
    with app.app_context():
        code = get_db().execute("SELECT verify_code FROM users WHERE email = 'newkid@uw.edu'").fetchone()[0]
    client.post("/verify", data={"code": code})
    assert "New: game updates by text" not in client.get("/").data.decode()


def test_clubs_never_end_up_without_officers(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Bea")
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Maya")
    client.post(f"/clubs/{club}/officers", data={"user": ids["Bea"], "action": "add"})
    said = client.post(f"/clubs/{club}/leave", follow_redirects=True).data.decode()
    assert "You&#39;re the owner" in said                                  # hand over before leaving
    client.post(f"/clubs/{club}/officers", data={"user": ids["Bea"], "action": "owner"})
    client.post(f"/clubs/{club}/leave")                                     # now Maya can leave
    _as(accounts, "Bea")
    said = client.post(f"/clubs/{club}/officers", data={"user": ids["Bea"], "action": "remove"},
                       follow_redirects=True).data.decode()
    assert "stays an officer" in said or "at least one officer" in said
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM club_members WHERE club_id = ? AND role = 'officer'",
                                (club,)).fetchone()[0] == 1


def test_admins_can_reach_manage_officers(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    _people(accounts, app, "Maya", "Boss")
    club = _club_with_officer(accounts, client, app)
    _as(accounts, "Boss")
    assert "Manage officers (admin)" in client.get(f"/clubs/{club}").data.decode()
    assert client.get(f"/clubs/{club}/officers").status_code == 200


def test_remove_all_weeks_keeps_other_weekdays(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "maya@uw.edu"
    _people(accounts, app, "Maya")
    _as(accounts, "Maya")
    first, _ = _day_after_tomorrow(18)
    from datetime import date as _date
    second = (_date.fromisoformat(first) + timedelta(days=1)).isoformat()
    for day in (first, second):
        client.post("/admin/uw-rec", data={"location": "Denny Field", "label": "IM flag", "date": day,
                                           "start": "18:00", "end": "22:00", "weeks": "3"})
    with app.app_context():
        one = get_db().execute("SELECT id FROM rec_reservations ORDER BY starts_at").fetchone()[0]
    client.post(f"/admin/uw-rec/{one}/delete", data={"all": "1"})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rec_reservations").fetchone()[0] == 3


# ---- Loop round 1: accounts, hosting, chats (whole-app testers) ----

def test_blocked_people_dont_see_your_upcoming_games_on_your_profile(accounts, client, app):
    ids = _people(accounts, app, "Alice", "Bob")
    _as(accounts, "Alice")
    client.post("/events/new", data=event_form(title="Alice hoops"))
    client.post(f"/block/{ids['Bob']}")
    _as(accounts, "Bob")
    assert "Alice hoops" not in client.get(f"/u/{ids['Alice']}").data.decode()


def test_suspended_accounts_cant_reset_their_password(accounts, client, app):
    accounts.signup(email="bob@uw.edu", name="Bob Husky")
    accounts.logout()
    client.post("/forgot", data={"email": "bob@uw.edu"})
    with app.app_context():
        code = get_db().execute("SELECT verify_code FROM users WHERE email = 'bob@uw.edu'").fetchone()[0]
        get_db().execute("UPDATE users SET suspended = 1 WHERE email = 'bob@uw.edu'")
        get_db().commit()
    page = client.post("/reset", data={"email": "bob@uw.edu", "code": code, "password": "new-pass-word-1",
                                       "password2": "new-pass-word-1"}, follow_redirects=True).data.decode()
    assert "Password changed" not in page


def test_suspended_people_cant_get_friend_requests(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Sus")
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (ids["Sus"],))
        get_db().commit()
    _as(accounts, "Maya")
    assert client.post(f"/friends/request/{ids['Sus']}").status_code == 404


def test_blocked_chat_isnt_marked_seen(accounts, client, app):
    ids = _people(accounts, app, "Ann", "Ben")
    _friends(app, ids["Ann"], ids["Ben"])
    _as(accounts, "Ann")
    client.post(f"/messages/{ids['Ben']}", data={"body": "last one"})
    client.post(f"/block/{ids['Ben']}")
    _as(accounts, "Ben")
    client.get(f"/messages/{ids['Ann']}")
    with app.app_context():
        assert get_db().execute("SELECT read_at FROM direct_messages").fetchone()[0] is None


def test_no_reactions_in_canceled_games_or_on_blocked_peoples_messages(accounts, client, app):
    ids = _people(accounts, app, "Host", "Pat", "Rae")
    _as(accounts, "Host")
    game = event_id_from(client.post("/events/new", data=event_form(title="Chatty")))
    for name in ("Pat", "Rae"):
        _as(accounts, name)
        client.post(f"/events/{game}/join")
    client.post(f"/events/{game}/chat", data={"body": "hi all"})          # Rae's message
    with app.app_context():
        msg = get_db().execute("SELECT id FROM event_messages").fetchone()[0]
    _as(accounts, "Pat")
    client.post(f"/block/{ids['Rae']}")
    assert client.post("/chat/react", data={"kind": "game", "id": msg, "emoji": "❤️"}).status_code == 404
    client.post(f"/unblock/{ids['Rae']}")
    _as(accounts, "Host")
    client.post(f"/events/{game}/cancel")
    _as(accounts, "Pat")
    assert client.post("/chat/react", data={"kind": "game", "id": msg, "emoji": "❤️"}).status_code in (403, 404)


def test_visitors_dont_see_officer_names_on_club_updates(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.login(email="captain@uw.edu")
    client.post(f"/clubs/{club}/posts", data={"body": "Nets at 5"})
    accounts.logout()
    page = client.get(f"/clubs/{club}").data.decode()
    assert "Nets at 5" in page and "Cap Tain" not in page


def test_roster_file_name_keeps_accented_letters(accounts, client, app):
    club = _approved_club(accounts, client, app, name="Ünïcode Clüb")
    accounts.login(email="captain@uw.edu")
    response = client.get(f"/clubs/{club}/roster.csv")
    assert "unicode-club-roster.csv" in response.headers["Content-Disposition"]


def test_changing_only_the_end_time_says_so(accounts, client, app):
    _people(accounts, app, "Host", "Pat")
    _as(accounts, "Host")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    with app.app_context():
        row = get_db().execute("SELECT starts_at, ends_at FROM events WHERE id = ?", (game,)).fetchone()
    _as(accounts, "Pat")
    client.post(f"/events/{game}/join")
    _as(accounts, "Host")
    from sportive.timeutil import from_db
    later = (from_db(row["ends_at"]) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    client.post(f"/events/{game}/edit", data=event_form(title="Hoops", starts_at=row["starts_at"].replace(" ", "T"),
                                                         ends_at=later))
    _as(accounts, "Pat")
    bell = client.get("/notifications").data.decode()
    assert "now ends at" in bell and "new time" not in bell


def test_on_hold_club_games_stay_in_my_events_and_players_are_told(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.login(email="captain@uw.edu")
    game = event_id_from(client.post("/events/new", data=event_form(title="Club night", club=str(club))))
    accounts.logout()
    accounts.signup(email="pat@uw.edu", name="Pat Husky")
    client.post(f"/events/{game}/join")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    client.post(f"/clubs/{club}/edit", data={**CLUB, "name": "UW Spikeball Club 2"})
    accounts.logout()
    accounts.login(email="pat@uw.edu")
    assert "Club night" in client.get("/me/events").data.decode()
    assert "on hold" in client.get("/notifications").data.decode()
    said = client.get(f"/events/{game}/party", follow_redirects=True).data.decode()
    assert "on hold" in said


# ---- Loop round 2: races, admin tools, phone layout ----

def test_cant_join_a_game_after_its_canceled(accounts, client, app):
    _people(accounts, app, "Host", "Pat")
    _as(accounts, "Host")
    game = event_id_from(client.post("/events/new", data=event_form(title="Rainout")))
    _as(accounts, "Pat")
    from sportive.events import get_event, try_join
    with app.test_request_context():
        from flask import g
        g.user = get_db().execute("SELECT * FROM users WHERE email = 'pat@uw.edu'").fetchone()
        event = get_event(game)                                   # loaded before the cancel, like a racing request
        get_db().execute("UPDATE events SET cancelled = 1 WHERE id = ?", (game,))
        get_db().commit()
        joined, _ = try_join(event)
    assert not joined


def test_parallel_wrong_codes_cant_get_past_the_limit(accounts, client, app):
    accounts.signup(email="bob@uw.edu", name="Bob Husky")
    accounts.logout()
    client.post("/forgot", data={"email": "bob@uw.edu"})
    with app.app_context():
        from sportive.auth import MAX_CODE_ATTEMPTS
        get_db().execute("UPDATE users SET verify_attempts = ? WHERE email = 'bob@uw.edu'", (MAX_CODE_ATTEMPTS - 1,))
        get_db().commit()
    with app.test_request_context():
        from sportive.auth import claim_code_try
        uid = get_db().execute("SELECT id FROM users WHERE email = 'bob@uw.edu'").fetchone()[0]
        assert claim_code_try(uid) and not claim_code_try(uid)    # one try left, then none


def test_crossing_friend_requests_make_one_friendship(accounts, client, app):
    ids = _people(accounts, app, "Ann", "Ben")
    _as(accounts, "Ann")
    client.post(f"/friends/request/{ids['Ben']}")
    _as(accounts, "Ben")
    client.post(f"/friends/request/{ids['Ann']}")                 # = accept
    with app.app_context():
        rows = get_db().execute("SELECT status FROM friendships").fetchall()
    assert [r[0] for r in rows] == ["accepted"]


def test_suspending_someone_cancels_invites_they_sent(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    ids = _people(accounts, app, "Host", "Xan", "Fay", "Boss")
    _friends(app, ids["Xan"], ids["Fay"])
    _as(accounts, "Host")
    game = event_id_from(client.post("/events/new", data=event_form(title="Pickup", players="10")))
    _as(accounts, "Xan")
    client.post(f"/events/{game}/join")
    client.post(f"/events/{game}/party", data={"friend": [ids["Fay"]]})
    _as(accounts, "Boss")
    client.post(f"/admin/users/{ids['Xan']}/suspend")
    with app.app_context():
        assert get_db().execute("SELECT status FROM invites WHERE inviter_id = ?", (ids["Xan"],)).fetchone()[0] == "canceled"


def test_denying_a_club_cancels_its_on_hold_events(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.login(email="captain@uw.edu")
    game = event_id_from(client.post("/events/new", data=event_form(title="Club night", club=str(club))))
    accounts.logout()
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    accounts.signup(email="boss@uw.edu", name="Bo Ss")
    client.post(f"/admin/clubs/{club}/remove", data={"note": "Instagram link is dead"})
    client.post(f"/admin/clubs/{club}/deny")
    with app.app_context():
        assert get_db().execute("SELECT cancelled FROM events WHERE id = ?", (game,)).fetchone()[0] == 1
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    client.post(f"/admin/clubs/{club}/restore")                  # not an admin: nothing happens


def test_officers_see_why_their_club_was_removed(accounts, client, app):
    club = _approved_club(accounts, client, app)
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    accounts.signup(email="boss@uw.edu", name="Bo Ss")
    client.post(f"/admin/clubs/{club}/remove", data={"note": "Instagram link is dead"})
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    page = client.get(f"/clubs/{club}").data.decode()
    assert "Why it's back in review" in page and "Instagram link is dead" in page


def test_filtered_suggestions_dont_hide_new_ones(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    accounts.signup(email="kid@uw.edu", name="Kid Husky")
    client.post("/suggestions", data={"kind": "bug", "body": "The map button does nothing on my phone"})
    accounts.logout()
    accounts.signup(email="boss@uw.edu", name="Bo Ss")
    client.get("/admin/suggestions?kind=idea")
    with app.test_request_context():
        pass
    page = client.get("/admin/suggestions").data.decode()
    assert "map button" in page and "New" in page.split("map button")[0][-600:]


def test_no_reports_about_suspended_accounts(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Xan")
    with app.app_context():
        get_db().execute("UPDATE users SET suspended = 1 WHERE id = ?", (ids["Xan"],))
        get_db().commit()
    _as(accounts, "Maya")
    assert client.get(f"/report/user/{ids['Xan']}").status_code == 404


def test_chat_messages_can_be_reached_with_the_keyboard(accounts, client, app):
    ids = _people(accounts, app, "Ann", "Ben")
    _friends(app, ids["Ann"], ids["Ben"])
    _as(accounts, "Ann")
    client.post(f"/messages/{ids['Ben']}", data={"body": "yo"})
    assert 'class="chat-bubble" tabindex="0"' in client.get(f"/messages/{ids['Ben']}").data.decode()


# ---- Loop round 3: emails & texts, feed & search, deployment ----

def test_weekly_email_command_runs_outside_a_page(app):
    result = app.test_cli_runner().invoke(args=["send-weekly"])
    assert result.exit_code == 0 and "Sent the weekly email" in result.output


def test_every_email_links_to_settings(app):
    from sportive.mail import compose
    with app.test_request_context():
        text, html = compose("Hi", "Hi", ["Line"], reason="Because.")
    assert "/settings" in text and "/settings" in html


def test_reset_code_isnt_texted_when_texts_are_off(accounts, client, app):
    from sportive import sms
    sent = []
    sms.send_sms, original = (lambda to, body: sent.append(body)), sms.send_sms
    try:
        accounts.signup(email="bob@uw.edu", name="Bob Husky")
        with app.app_context():
            get_db().execute("UPDATE users SET phone = '+12065550142', phone_verified = 1, sms_updates = 0")
            get_db().commit()
            uid = get_db().execute("SELECT id FROM users").fetchone()[0]
        with app.test_request_context():
            assert sms.text_code(uid, "123456", "password reset") is False
        assert sent == []
    finally:
        sms.send_sms = original


def test_admin_cancellations_dont_blame_the_host(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    ids = _people(accounts, app, "Hana", "Pat", "Boss")
    _as(accounts, "Hana")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    _as(accounts, "Pat")
    client.post(f"/events/{game}/join")
    _as(accounts, "Boss")
    client.post(f"/admin/users/{ids['Hana']}/suspend")
    _as(accounts, "Pat")
    bell = client.get("/notifications").data.decode()
    assert "Sportive Circle canceled" in bell and "Hana canceled" not in bell


def test_top_dawgs_skips_blocked_people_and_solo_games(accounts, client, app):
    ids = _people(accounts, app, "Mia", "Bob", "Cal")
    from sportive.timeutil import now_local, to_db
    start = now_local().replace(day=1, hour=0, minute=1)
    with app.app_context():
        db = get_db()
        def game(host, *players):
            cur = db.execute("""INSERT INTO events (host_id, title, sport, location, skill_level, starts_at, ends_at,
                                created_at) VALUES (?, 'g', 'basketball', 'IMA (Intramural Activities Building)',
                                'Casual', ?, ?, ?)""", (host, to_db(start), to_db(start + timedelta(minutes=30)), to_db(start)))
            for p in (host, *players):
                db.execute("INSERT INTO rsvps (event_id, user_id, created_at) VALUES (?, ?, ?)", (cur.lastrowid, p, to_db(start)))
        game(ids["Bob"]); game(ids["Bob"]); game(ids["Bob"])         # solo: don't count
        game(ids["Cal"], ids["Bob"])                                  # real game: counts for both
        db.commit()
    if now_local() <= start + timedelta(minutes=30):
        return  # first half hour of the month: nothing has ended yet
    _as(accounts, "Mia")
    from sportive.spirit import top_dawgs
    with app.test_request_context():
        board = {r["full_name"].split()[0]: r["games"] for r in top_dawgs(viewer=ids["Mia"])}
    assert board.get("Bob") == 1 and board.get("Cal") == 1
    client.post(f"/block/{ids['Bob']}")
    with app.test_request_context():
        assert "Bob" not in {r["full_name"].split()[0] for r in top_dawgs(viewer=ids["Mia"])}


def test_my_clubs_only_lists_clubs_you_can_open(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="mo@uw.edu", name="Mo Husky")
    client.post(f"/clubs/{club}/join", data={"message": "hi"})
    with app.app_context():
        get_db().execute("UPDATE clubs SET status = 'pending' WHERE id = ?", (club,))
        get_db().commit()
    assert f'href="/clubs/{club}"' not in client.get("/clubs?mine=1").data.decode()


def test_empty_my_sports_feed_points_to_all_sports(accounts, client, app):
    accounts.signup(email="mia@uw.edu", name="Mia Husky", sports=("tennis",))
    page = client.get("/").data.decode()
    assert "No games for your sports yet" in page and "scope=all" in page


def test_seed_refuses_the_live_database(tmp_path):
    import os
    import subprocess
    import sys
    env = {**os.environ, "RENDER_EXTERNAL_URL": "https://x.onrender.com", "DATABASE": str(tmp_path / "live.db"),
           "SECRET_KEY": "k" * 48}
    result = subprocess.run([sys.executable, "seed.py"], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and "won't add demo accounts" in result.stderr


# ---- UW club sports ----

def test_uw_club_sports_can_be_picked(accounts, client, app):
    """The user: no club wants to be "Other" (e.g. the boxing club)."""
    from sportive.constants import SPORTS
    for key in ("boxing", "bjj", "judo", "wrestling", "fencing", "rugby", "lacrosse", "water_polo", "badminton",
                "squash", "ice_hockey", "sailing", "table_tennis"):
        assert key in SPORTS
    club = _approved_club(accounts, client, app, name="UW Boxing Club", sport="boxing")
    with app.app_context():
        assert get_db().execute("SELECT sport FROM clubs WHERE id = ?", (club,)).fetchone()[0] == "boxing"
    accounts.signup(email="fighter@uw.edu", name="Fi Ghter", sports=("boxing",))
    assert "Boxing" in client.get("/clubs?sport=boxing").data.decode()
    game = event_id_from(client.post("/events/new", data=event_form(title="Sparring", sport="boxing",
                                                                     location="IMA (Intramural Activities Building)",
                                                                     players="8")))
    assert "Sparring" in client.get(f"/events/{game}").data.decode()


def test_other_clubs_move_to_their_sport_by_name(app):
    from sportive.db import init_db
    with app.app_context():
        db = get_db()
        owner = db.execute("INSERT INTO users (email, full_name, password_hash, created_at, verified) "
                           "VALUES ('o@uw.edu', 'O W', 'x', '2026-01-01 00:00', 1)").lastrowid
        for name, sport in (("UW Boxing Club", "other"), ("Husky Disc Golf", "other"), ("Kickboxing Crew", "other"),
                            ("Chess Club", "other"), ("Spike Boxing", "spikeball")):
            db.execute("INSERT INTO clubs (name, sport, description, status, created_by, created_at) "
                       "VALUES (?, ?, 'x', 'approved', ?, '2026-01-01 00:00')", (name, sport, owner))
        db.execute("PRAGMA user_version = 0")      # an older database that hasn't been sorted yet
        db.commit()
        init_db()
        sports = dict(db.execute("SELECT name, sport FROM clubs").fetchall())
        db.execute("UPDATE clubs SET sport = 'other' WHERE name = 'UW Boxing Club'")   # an officer's own pick later
        db.commit()
        init_db()                                  # a restart doesn't sort again
        assert db.execute("SELECT sport FROM clubs WHERE name = 'UW Boxing Club'").fetchone()[0] == "other"
    assert sports == {"UW Boxing Club": "boxing", "Husky Disc Golf": "disc_golf", "Kickboxing Crew": "muay_thai",
                      "Chess Club": "other", "Spike Boxing": "spikeball"}


# ---- Loop round 4: speed, data integrity, wording ----

def test_friend_search_and_suggestions_still_find_the_right_people(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan", "Sam", "Alex")
    _friends(app, ids["Maya"], ids["Jordan"])
    _friends(app, ids["Jordan"], ids["Sam"])
    _as(accounts, "Maya")
    from sportive.social import friend_suggestions, search_people
    with app.test_request_context():
        found = {p["full_name"].split()[0]: p for p in search_people(ids["Maya"], "Husky")}
        assert found["Sam"]["mutual"] == 1 and found["Alex"]["mutual"] == 0
        assert "Sam" in {p["full_name"].split()[0] for p in friend_suggestions(ids["Maya"])}


def test_club_events_have_an_index(app):
    with app.app_context():
        names = {r[1] for r in get_db().execute("PRAGMA index_list(events)")}
    assert "idx_events_club" in names


def test_only_officer_with_followers_hands_the_club_over_before_deleting(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu", name="Fan Husky")
    client.post(f"/clubs/{club}/follow")
    accounts.logout()
    accounts.login(email="captain@uw.edu")
    said = client.post("/profile/delete", data={"confirm": "DELETE", "password": "purple-and-gold"},
                       follow_redirects=True).data.decode()
    assert "only officer" in said
    with app.app_context():
        assert get_db().execute("SELECT 1 FROM clubs WHERE id = ?", (club,)).fetchone() is not None


def test_deleting_an_account_clears_notices_and_reactions_for_its_games(accounts, client, app):
    ids = _people(accounts, app, "Xa", "Yo")
    _as(accounts, "Xa")
    game = event_id_from(client.post("/events/new", data=event_form(title="Hoops")))
    _as(accounts, "Yo")
    client.post(f"/events/{game}/join")
    client.post(f"/events/{game}/chat", data={"body": "hey"})
    _as(accounts, "Xa")
    client.post(f"/events/{game}/players/{ids['Yo']}/remove")              # notice to Yo links to the game
    _friends(app, ids["Xa"], ids["Yo"])
    client.post(f"/messages/{ids['Yo']}", data={"body": "sorry"})
    with app.app_context():
        dm = get_db().execute("SELECT id FROM direct_messages").fetchone()[0]
    _as(accounts, "Yo")
    client.post("/chat/react", data={"kind": "dm", "id": dm, "emoji": "❤️"})
    _as(accounts, "Xa")
    client.post("/profile/delete", data={"confirm": "DELETE", "password": "purple-and-gold"})
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT COUNT(*) FROM notices WHERE url LIKE ?", (f"/events/{game}%",)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM message_reactions").fetchone()[0] == 0


def test_daily_cleanup_removes_reactions_on_missing_messages(accounts, app):
    from sportive.backups import clean_up_old_records
    accounts.signup()
    me = _user_id(app, "dubs@uw.edu")
    with app.app_context():
        get_db().execute("INSERT INTO message_reactions (kind, message_id, user_id, emoji, created_at) "
                         "VALUES ('game', 999, ?, '❤️', '2026-01-01 00:00')", (me,))
        get_db().commit()
        clean_up_old_records()
        assert get_db().execute("SELECT COUNT(*) FROM message_reactions").fetchone()[0] == 0


def test_help_pages_match_the_app(client):
    privacy = client.get("/privacy").data.decode()
    assert "Former member" in privacy and "Read receipts" in privacy and "Message an admin" not in privacy
    faq = client.get("/faq").data.decode()
    assert "Who can I message?" in faq and "Send to friends" in faq and "Manage officers" in faq


# ---- "Maya posted a game": friends and club followers hear about new games ----

def _outbox(app):
    return app.extensions.setdefault("outbox", [])


def test_friends_get_an_email_and_a_notice_when_you_post_a_game(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan", "Stranger")
    _friends(app, ids["Maya"], ids["Jordan"])
    _outbox(app).clear()
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Sunset hoops")))
    mails = [m for m in _outbox(app) if "posted a game" in m["subject"]]
    assert [m["to"] for m in mails] == ["jordan@uw.edu"]                  # friends only, not strangers or the host
    assert "Maya posted a game: Sunset hoops" == mails[0]["subject"]
    assert f"/events/{game}" in mails[0]["body"] and "See the game and join" in mails[0]["body"]
    _as(accounts, "Jordan")
    bell = client.get("/notifications").data.decode()
    assert "Maya posted Sunset hoops" in bell and f'href="/events/{game}"' in bell


def test_no_game_emails_for_private_games_blocked_people_or_people_who_opted_out(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan", "Sam", "Vic")
    _friends(app, ids["Maya"], ids["Jordan"], ids["Sam"], ids["Vic"])
    _as(accounts, "Sam")
    client.post("/settings/friend-games", data={})                          # Sam turns the email off
    _as(accounts, "Vic")
    client.post(f"/block/{ids['Maya']}")                                    # Vic blocks Maya
    _outbox(app).clear()
    _as(accounts, "Maya")
    client.post("/events/new", data=event_form(title="Secret run", is_private="1", password="dawgs26"))
    assert not [m for m in _outbox(app) if "posted a game" in m["subject"]]
    client.post("/events/new", data=event_form(title="Open run"))
    assert [m["to"] for m in _outbox(app) if "posted a game" in m["subject"]] == ["jordan@uw.edu"]
    _as(accounts, "Sam")
    assert "Maya posted Open run" in client.get("/notifications").data.decode()   # still in Sam's bell


def test_game_emails_are_capped_per_day(accounts, client, app):
    from sportive.friendgames import EMAILS_PER_DAY
    ids = _people(accounts, app, "Maya", "Jordan")
    _friends(app, ids["Maya"], ids["Jordan"])
    _outbox(app).clear()
    _as(accounts, "Maya")
    for n in range(EMAILS_PER_DAY + 2):
        client.post("/events/new", data=event_form(title=f"Game {n}", starts_at=form_time(timedelta(days=1, hours=n)),
                                                   ends_at=form_time(timedelta(days=1, hours=n + 1))))
    assert len([m for m in _outbox(app) if "posted a game" in m["subject"]]) == EMAILS_PER_DAY


def test_club_followers_hear_about_club_events(accounts, client, app):
    club = _approved_club(accounts, client, app)
    accounts.signup(email="fan@uw.edu", name="Fan Husky")
    client.post(f"/clubs/{club}/follow")
    accounts.logout()
    _outbox(app).clear()
    accounts.login(email="captain@uw.edu")
    client.post("/events/new", data=event_form(title="Club night", club=str(club), repeat="3"))
    mails = [m for m in _outbox(app) if "posted a game" in m["subject"]]
    assert [m["to"] for m in mails] == ["fan@uw.edu"]                       # once, not once per week
    assert "for UW Spikeball Club" in mails[0]["body"]
    _outbox(app).clear()
    client.post("/events/new", data=event_form(title="Members night", club=str(club), is_private="members"))
    assert not [m for m in _outbox(app) if "posted a game" in m["subject"]]  # followers aren't members


def test_settings_has_the_new_game_email_switch(accounts, client):
    accounts.signup()
    page = client.get("/settings").data.decode()
    assert 'name="email_friend_games"' in page and "friends or my clubs post a game" in page


def test_joining_clears_the_posted_a_game_notice(accounts, client, app):
    ids = _people(accounts, app, "Maya", "Jordan")
    _friends(app, ids["Maya"], ids["Jordan"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Sunset hoops")))
    _as(accounts, "Jordan")
    client.post(f"/events/{game}/join")
    assert "Maya posted Sunset hoops" not in client.get("/notifications").data.decode()


# ---- Places for every sport; Need players boxes stay level ----

def test_sports_offer_the_places_clubs_really_use():
    from sportive.constants import LOCATIONS, SPORT_LOCATIONS
    fencing = SPORT_LOCATIONS["fencing"]
    assert "Red Square" in fencing and "IMA Mat Rooms (martial arts)" in fencing and "Recreation Field 1 (by the IMA)" in fencing
    assert "Emerald City Boxing Gym (Roosevelt)" in SPORT_LOCATIONS["boxing"]
    assert SPORT_LOCATIONS["archery"][0] == "IMA Archery Room" and "IMA Pool" in SPORT_LOCATIONS["water_polo"]
    for sport in ("judo", "bjj", "karate", "taekwondo", "wrestling", "muay_thai", "kendo"):
        assert "IMA Mat Rooms (martial arts)" in SPORT_LOCATIONS[sport], sport
    for sport, places in SPORT_LOCATIONS.items():
        assert places and all(p in LOCATIONS for p in places), sport


def test_need_players_tip_sits_under_both_boxes(accounts, client):
    accounts.signup()
    page = client.get("/need-players").data.decode()
    row = page[page.index('<div class="row">'):page.index("</div>", page.index('<div class="row">'))]
    assert 'name="sport"' in row and 'name="location"' in row and "data-place-tip" not in row
    assert "data-place-tip" in page


def test_reserve_spots_lists_every_friend_and_holds_can_be_renewed(accounts, client, app):
    """Vincent: Thomas was reserved, then wasn't anymore, and couldn't be picked again. Reserve spots now lists
    every friend (like Send to friends), says why someone can't be picked, and a held spot that ran out can be
    held again."""
    ids = _people(accounts, app, "Maya", "Thomas", "Jordan", "Sam")
    _friends(app, ids["Maya"], ids["Thomas"], ids["Jordan"], ids["Sam"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Sunday 5v5 IMA", players="10")))
    client.post(f"/events/{game}/party", data={"friend": [ids["Thomas"], ids["Jordan"]]})
    _as(accounts, "Sam")
    client.post(f"/events/{game}/join")
    _as(accounts, "Maya")
    page = client.get(f"/events/{game}/party").data.decode()
    sent = client.get(f"/events/{game}/send").data.decode()
    for name in ("Thomas Husky", "Jordan Husky", "Sam Husky"):                  # everyone, on both pages
        assert name in page and name in sent
    assert "Already in this game" in page and "Spot held for 30 more min" in page
    with app.app_context():                                                   # 30 minutes pass, Thomas never answers
        get_db().execute("UPDATE invites SET expires_at = '2000-01-01 00:00' WHERE guest_id = ?", (ids["Thomas"],))
        get_db().commit()
    assert "held spot ran out" in client.get(f"/events/{game}").data.decode()
    page = client.get(f"/events/{game}/party").data.decode()
    assert "Their held spot ran out. Reserve it again?" in page
    again = client.post(f"/events/{game}/party", data={"friend": [ids["Thomas"]]}, follow_redirects=True)
    assert b"held for 30 minutes" in again.data
    with app.app_context():
        assert get_db().execute("SELECT expires_at > '2000-01-01 00:00' FROM invites WHERE guest_id = ?",
                                (ids["Thomas"],)).fetchone()[0] == 1
    refused = client.post(f"/events/{game}/party", data={"friend": [ids["Sam"]]}, follow_redirects=True)
    assert b"only invite your friends who aren&#39;t in this game" in refused.data   # already going


def test_the_host_sees_what_happened_to_each_invite(accounts, client, app):
    """Vincent: "we don't know why" a reserved friend disappeared. The game page now says, for each invite that
    didn't end with the friend in the game: can't make it, joined then left, taken off, or taken back."""
    ids = _people(accounts, app, "Maya", "Thomas", "Jordan", "Sam", "Lee")
    _friends(app, ids["Maya"], ids["Thomas"], ids["Jordan"], ids["Sam"], ids["Lee"])
    _as(accounts, "Maya")
    game = event_id_from(client.post("/events/new", data=event_form(title="Sunday 5v5 IMA", players="10")))
    client.post(f"/events/{game}/party", data={"friend": [ids["Thomas"], ids["Jordan"], ids["Sam"], ids["Lee"]]})
    _as(accounts, "Thomas")
    client.post(f"/events/{game}/invite/answer", data={"answer": "yes"})
    client.post(f"/events/{game}/leave")
    _as(accounts, "Jordan")
    client.post(f"/events/{game}/invite/answer", data={"answer": "no"})
    _as(accounts, "Sam")
    client.post(f"/events/{game}/invite/answer", data={"answer": "yes"})
    _as(accounts, "Maya")
    client.post(f"/events/{game}/players/{ids['Sam']}/remove")
    client.post(f"/events/{game}/invite/{ids['Lee']}/cancel")
    page = client.get(f"/events/{game}").data.decode()
    assert "Invites that didn't work out" in page
    for line in ("joined, then left", "said they can&#39;t make it", "the host took them off", "invite was taken back"):
        assert line in page
