"""Clubs post to everyone: an officer posts as the club (photos, 🔥, replies, plans), every feed shows it with
the verified club mark, and the card leads to the club's events and info."""
from datetime import timedelta
from io import BytesIO

from conftest import make_image
from sportive.db import get_db
from test_feed import approved_club, as_user, form_time, post, user_id


def test_a_club_post_reaches_everyone_not_only_followers(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    photos = [(BytesIO(make_image()), f"run{n}.png") for n in range(2)]
    page = post(client, as_club=str(club), body="Saturday long run, all paces 🏃", photos=photos).data.decode()
    assert "Posted as UW Run Club" in page
    accounts.logout()
    accounts.signup(email="hooper@uw.edu", sports=("basketball",))   # doesn't follow it, doesn't run
    feed = client.get("/feed").data.decode()
    assert "Saturday long run, all paces" in feed and "Verified club" in feed
    assert f"/clubs/{club}#events" in feed and "Events &amp; info" in feed and 'class="head-follow"' in feed
    assert "Photo 1 of 2 from UW Run Club" in feed                     # the club's name, not the officer's
    assert "Saturday long run" not in client.get("/feed?sport=basketball").data.decode()  # other sports' channels
    assert "Saturday long run" in client.get(f"/clubs/{club}").data.decode()            # and on the club's page
    officer = user_id(app, "officer@uw.edu")
    assert "Saturday long run" not in client.get(f"/users/{officer}").data.decode()     # the club's, not personal


def test_only_officers_post_as_a_club_and_any_officer_can_delete(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    post(client, as_club=str(club), body="Club update")
    accounts.logout()
    accounts.signup(email="member@uw.edu", sports=("running",))
    assert post(client, as_club=str(club), body="I'm the club now").status_code == 403
    with app.app_context():
        db = get_db()
        post_id = db.execute("SELECT id FROM posts WHERE club_id = ?", (club,)).fetchone()[0]
        db.execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'officer', '2026-01-01')",
                   (club, user_id(app, "member@uw.edu")))
        db.commit()
    assert client.post(f"/posts/{post_id}/delete").status_code == 302                  # a second officer
    with app.app_context():
        assert get_db().execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone() is None


def test_a_club_plan_is_a_club_event_and_posting_from_the_club_page(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    composer = client.get("/feed").data.decode()
    assert "Post as" in composer and "UW Run Club ✓ (club)" in composer
    post(client, as_club=str(club), body="Track night", plan="1", starts_at=form_time(timedelta(days=2)),
         duration="60", location="Husky Track", spots="10")
    with app.app_context():
        assert get_db().execute("SELECT club_id FROM events WHERE title = 'Track night'").fetchone()[0] == club
    assert "Track night" in client.get(f"/clubs/{club}").data.decode()
    response = client.post("/posts/new", data={"as_club": str(club), "from_club": "1", "body": "From the page"},
                           content_type="multipart/form-data")
    assert response.headers["Location"].endswith(f"/clubs/{club}#announcements")


def test_a_club_post_hides_while_the_club_is_not_verified(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    post(client, as_club=str(club), body="Soon gone")
    with app.app_context():
        get_db().execute("UPDATE clubs SET status = 'rejected' WHERE id = ?", (club,))
        get_db().commit()
    as_user(accounts, "officer@uw.edu")
    assert "Soon gone" not in client.get("/feed").data.decode()


def test_every_verified_clubs_updates_reach_the_whole_feed(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("tennis",))
    club = approved_club(app, "officer@uw.edu", name="UW Tennis Club", sport="tennis")
    client.post(f"/clubs/{club}/posts", data={"body": "Ladder results are up"})
    accounts.logout()
    accounts.signup(email="runner@uw.edu", sports=("running",))
    feed = client.get("/feed").data.decode()
    assert "Ladder results are up" in feed and f"/clubs/{club}#events" in feed


def test_clubs_reply_as_the_club_and_their_posts_take_replies(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    post(client, as_club=str(club), body="Who's in for Saturday?")
    accounts.logout()
    accounts.signup(email="maya@uw.edu", name="Maya Chen", sports=("running",))
    with app.app_context():
        club_post = get_db().execute("SELECT id FROM posts WHERE club_id = ?", (club,)).fetchone()[0]
    client.post(f"/posts/{club_post}/replies", data={"body": "Me!"})                  # people reply to clubs
    assert client.post(f"/posts/{club_post}/replies", data={"body": "x", "as_club": str(club)}).status_code == 403
    post(client, body="Need a running buddy")
    with app.app_context():
        maya_post = get_db().execute("SELECT id FROM posts WHERE club_id IS NULL").fetchone()[0]
    as_user(accounts, "officer@uw.edu")
    page = client.get(f"/posts/{club_post}").data.decode()
    assert "Me!" in page and "Reply as" in page
    client.post(f"/posts/{maya_post}/replies", data={"body": "Come run with us!", "as_club": str(club)})
    as_user(accounts, "maya@uw.edu")
    page = client.get(f"/posts/{maya_post}").data.decode()
    assert "Come run with us!" in page and "Verified club" in page and f'href="/clubs/{club}"' in page
    bell = client.get("/notifications").data.decode()
    assert "💬 UW Run Club replied to your post" in bell


def test_my_clubs_shows_club_posts_and_officers_post_from_it(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    response = client.post("/posts/new", data={"as_club": str(club), "from_my_clubs": "1", "body": "Hill repeats"},
                           content_type="multipart/form-data")
    assert response.headers["Location"].endswith("/clubs/updates")
    accounts.logout()
    accounts.signup(email="fan@uw.edu", sports=("basketball",))
    client.post(f"/clubs/{club}/follow")
    page = client.get("/clubs/updates").data.decode()
    assert "Hill repeats" in page and "Verified club" in page and "data-pull-refresh" in page


def test_a_plan_follows_every_game_rule(accounts, client, app):
    accounts.signup(email="maya@uw.edu", sports=("basketball",))
    plan = {"plan": "1", "sport": "basketball", "body": "Run it", "duration": "120", "spots": "3",
            "starts_at": form_time(timedelta(days=1))}
    assert "can&#39;t be played at Denny Field" in post(client, **plan, location="Denny Field").data.decode()
    page = post(client, **plan, location="IMA (Intramural Activities Building)", open_to="nobody").data.decode()
    assert "pick who the game is open to" in page
    post(client, **plan, location="IMA (Intramural Activities Building)", skill_level="Competitive",
         open_to="women")
    with app.app_context():
        game = get_db().execute("SELECT skill_level, open_to, max_players FROM events").fetchone()
    assert tuple(game) == ("Competitive", "women", 4)
    feed = client.get("/feed").data.decode()
    assert 'id="sport-rules"' in feed and "Heads up: check you can use the" in feed and "data-pull-refresh" in feed


def test_new_games_sit_together_in_one_row(accounts, client, app):
    accounts.signup(email="host@uw.edu", sports=("soccer",))
    for n in range(3):
        client.post("/events/new", data={"title": f"Pickup {n}", "sport": "soccer", "location": "Denny Field",
                                         "players": "10", "starts_at": form_time(timedelta(days=1, hours=n)),
                                         "ends_at": form_time(timedelta(days=1, hours=n + 1)), "note": ""})
    accounts.logout()
    accounts.signup(email="fan@uw.edu", sports=("soccer",))
    feed = client.get("/feed").data.decode()
    assert feed.count('class="card feed-card feed-games"') == 1 and feed.count('class="games-tile"') == 3


def test_feed_rows_fit_the_smallest_phones(client):
    """Bot run 1: at 320px the one-line post box pushed Post 7px off screen, Report + Delete on a club post did
    the same, and "Reply as" made a post's page 472px wide. (Checked in a browser; these rules keep it fixed.)"""
    css = client.get("/static/style.css").data.decode()
    assert "grid-template-columns: minmax(0, 1fr) auto" in css                      # the one-line post box
    assert ".feed-actions { display: flex; flex-wrap: wrap;" in css                  # 🔥 Reply … Report Delete
    assert ".reply-form .post-as { flex: 1 1 100%; min-width: 0;" in css            # Reply as


def test_reacting_happens_in_place(accounts, client, app):
    """🔥, replies, Follow, I'm in and Delete send in the background and swap just their card (app.js), so the
    page never reloads; Report and Delete sit behind a ⋯ menu."""
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    post(client, as_club=str(club), body="Club run")
    post(client, body="My own run")
    feed = client.get("/feed").data.decode()
    assert 'class="like-form" data-inplace' in feed and 'data-inplace="remove"' in feed
    assert feed.count("data-swap") >= 2 and 'class="more-menu card-more"' in feed
    with app.app_context():
        post_id = get_db().execute("SELECT id FROM posts WHERE club_id IS NULL").fetchone()[0]
    page = client.get(f"/posts/{post_id}").data.decode()
    assert 'id="replies" data-swap' in page and 'class="reply-form" data-inplace' in page
    js = client.get("/static/app.js").data.decode()
    assert "form[data-inplace]" in js and "replaceWith(fresh)" in js


def test_all_clubs_feed_and_a_tidy_feed_top(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("tennis",))
    club = approved_club(app, "officer@uw.edu", name="UW Tennis Club", sport="tennis")
    post(client, as_club=str(club), sport="tennis", body="Ladder night")
    client.post(f"/clubs/{club}/posts", data={"body": "Courts booked"})
    accounts.logout()
    accounts.signup(email="runner@uw.edu", sports=("running",))
    everything = client.get("/clubs/feed").data.decode()                        # All clubs: every verified club
    assert "Ladder night" in everything and "Courts booked" in everything and ">All clubs<" in everything
    assert "Ladder night" not in client.get("/clubs/updates").data.decode()       # My clubs: only clubs you follow
    client.post(f"/clubs/{club}/follow")
    assert "Ladder night" in client.get("/clubs/updates").data.decode()
    feed = client.get("/feed").data.decode()
    assert 'href="/clubs/feed"' in feed                                           # the Clubs tab opens All clubs
    assert 'class="sport-filter"' in feed and "All my sports" in feed and "sport-channels" not in feed
    assert "data-help-bubble" not in feed and 'placeholder="Who\'s down?"' in feed


def test_play_says_how_many_sports_instead_of_listing_fifty(accounts, client):
    """Someone who picked every sport got a paragraph of sport names above the games."""
    accounts.signup(email="all@uw.edu", sports=("running", "tennis", "soccer", "hiking", "basketball"))
    page = client.get("/").data.decode()
    assert "Showing your 5 sports" in page and "Change sports" in page


def test_home_and_club_tabs_stay_under_the_header(client):
    """Scrolled a little, the sticky purple header covered Feed / Play / My events, so the tab row looked empty."""
    css = client.get("/static/style.css").data.decode()
    assert "body.has-app-nav .home-tabs { position: sticky; top: 60px;" in css
