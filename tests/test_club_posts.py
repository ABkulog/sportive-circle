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
    assert f'href="/clubs/{club}"' in feed and 'class="head-follow"' in feed and "Events &amp; info" not in feed
    assert "Photo 1 of 2 from UW Run Club" in feed                     # the club's name, not the officer's
    assert "Saturday long run" not in client.get("/feed?sport=basketball").data.decode()  # other sports' channels
    assert "Saturday long run" in client.get(f"/clubs/{club}").data.decode()            # and on the club's page
    officer = user_id(app, "officer@uw.edu")
    assert "Saturday long run" not in client.get(f"/u/{officer}").data.decode()     # the club's, not personal


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
        assert get_db().execute("SELECT club_id FROM events WHERE note = 'Track night'").fetchone()[0] == club
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
    assert "Ladder results are up" in feed and f'href="/clubs/{club}"' in feed


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


def test_the_feed_is_only_posts_games_are_on_play(accounts, client, app):
    accounts.signup(email="host@uw.edu", sports=("soccer",))
    for n in range(3):
        client.post("/events/new", data={"title": f"Pickup {n}", "sport": "soccer", "location": "Denny Field",
                                         "players": "10", "starts_at": form_time(timedelta(days=1, hours=n)),
                                         "ends_at": form_time(timedelta(days=1, hours=n + 1)), "note": ""})
    accounts.logout()
    accounts.signup(email="fan@uw.edu", sports=("soccer",))
    feed = client.get("/feed").data.decode()
    assert "Pickup 0" not in feed and "feed-games" not in feed
    assert "Pickup 0" in client.get("/").data.decode()


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
    assert f'id="replies-{post_id}" data-swap' in page and 'class="reply-form" data-inplace' in page
    js = client.get("/static/app.js").data.decode()
    assert "form[data-inplace]" in js and "replaceWith(fresh)" in js


def test_all_clubs_feed_and_a_tidy_feed_top(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("tennis",))
    club = approved_club(app, "officer@uw.edu", name="UW Tennis Club", sport="tennis")
    post(client, as_club=str(club), sport="tennis", body="Ladder night")
    client.post(f"/clubs/{club}/posts", data={"body": "Courts booked"})
    accounts.logout()
    accounts.signup(email="runner@uw.edu", sports=("running",))
    everything = client.get("/feed?show=clubs").data.decode()                   # All clubs: every verified club
    assert "Ladder night" in everything and "Courts booked" in everything
    assert "Ladder night" not in client.get("/clubs/updates").data.decode()       # My clubs: only clubs you follow
    client.post(f"/clubs/{club}/follow")
    assert "Ladder night" in client.get("/clubs/updates").data.decode()
    feed = client.get("/feed").data.decode()
    assert 'href="/feed?show=myclubs"' in feed                                   # My clubs: a chip on the feed
    assert 'class="feed-chips"' in feed and ">All<" in feed and "More ▾" in feed and "sport-channels" not in feed
    assert "data-help-bubble" not in feed and 'placeholder="What\'s happening?"' in feed


def test_play_says_how_many_sports_instead_of_listing_fifty(accounts, client):
    """Someone who picked every sport got a paragraph of sport names above the games."""
    accounts.signup(email="all@uw.edu", sports=("running", "tennis", "soccer", "hiking", "basketball"))
    page = client.get("/").data.decode()
    assert "Showing your 5 sports" in page and "Change sports" in page


def test_home_and_club_tabs_stay_under_the_header(client):
    """Scrolled a little, the sticky purple header covered Feed / Play / My events, so the tab row looked empty."""
    css = client.get("/static/style.css").data.decode()
    assert "body.has-app-nav .home-tabs { position: sticky; top: 60px;" in css



def test_posting_and_opening_replies_stay_on_the_page(accounts, client, app):
    """Posting from the post box and 💬 reloaded the page or left it: now the post box refreshes just the list
    under it, and 💬 opens the replies inside the card (app.js)."""
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    post(client, body="Hello")
    with app.app_context():
        post_id = get_db().execute("SELECT id FROM posts").fetchone()[0]
    feed = client.get("/feed").data.decode()
    assert 'data-inplace data-swap-target="#feed-list"' in feed and 'id="feed-list"' in feed
    assert f'data-replies="replies-{post_id}"' in feed
    assert 'id="club-posts-list"' in client.get(f"/clubs/{club}").data.decode()      # pins swap it in place
    reply = client.post(f"/posts/{post_id}/replies", data={"body": "Hi"})
    assert reply.headers["Location"].endswith(f"#replies-{post_id}")
    js = client.get("/static/app.js").data.decode()
    assert "a[data-replies]" in js and "form.dataset.swapTarget" in js


def test_the_post_box_never_touches_the_first_post(client):
    css = client.get("/static/style.css").data.decode()
    assert ".composer, .update-composer, .clubs-for-you { margin-bottom: 12px; }" in css
    assert "#feed-list > :first-child { margin-top: 0; }" in css


def test_the_plus_button_opens_the_post_sheet(accounts, client):
    """Like Instagram: the feed starts with posts. The ＋ at the bottom right opens the post box as a sheet,
    × / a tap outside / Esc closes it (what you wrote stays). Photos and text in posts are smaller, to fit more."""
    accounts.signup(sports=("running",))
    feed = client.get("/feed").data.decode()
    assert 'class="post-sheet" id="post"' in feed and "data-open-post" in feed and "data-close-post" in feed
    assert feed.index('id="post"') < feed.index('id="feed-list"')
    assert 'href="/feed#post"' in client.get("/").data.decode()                  # ＋ on other pages too
    js = client.get("/static/app.js").data.decode()
    assert "[data-open-post]" in js and "closePostSheet" in js
    css = client.get("/static/style.css").data.decode()
    assert ".feed-photos.is-single .feed-photo, .feed-photos.is-single .feed-photo img, .feed-video { max-height: 340px; }" in css


def test_feed_like_twitter_clubs_menu_and_profile_posts_first(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("tennis",))
    club = approved_club(app, "officer@uw.edu", name="UW Tennis Club", sport="tennis")
    post(client, as_club=str(club), sport="tennis", body="Ladder night")
    accounts.logout()
    accounts.signup(email="maya@uw.edu", name="Maya Chen", sports=("running",))
    post(client, body="Morning 10K")
    feed = client.get("/feed").data.decode()
    assert 'href="/feed?show=myclubs"' in feed and "What's happening?" in feed           # one row of chips
    assert 'class="page-title"' not in feed and "Hey, Maya" not in feed                 # no big title
    clubs = client.get("/feed?show=clubs").data.decode()
    assert "Ladder night" in clubs and "Morning 10K" not in clubs                         # All clubs: only clubs
    assert "Ladder night" not in client.get("/feed?show=myclubs").data.decode()           # not following it
    assert "Ladder night" not in client.get("/feed?show=clubs&sport=running").data.decode()
    back = client.post("/posts/new", data={"sport": "running", "body": "x", "show": "clubs"},
                       content_type="multipart/form-data")
    assert back.headers["Location"].endswith("/feed?show=clubs")
    maya = user_id(app, "maya@uw.edu")
    profile = client.get(f"/u/{maya}").data.decode()
    assert profile.index('data-tab-button="posts"') < profile.index('data-tab-button="games"')
    assert "Morning 10K" in profile


def test_one_card_pattern_no_canceled_games_and_quick_buttons(accounts, client, app):
    """Every card looks the same, canceled games leave the feed, a plan's game doesn't repeat the post, and the
    post box offers photos and a plan. There's one way to make each thing."""
    accounts.signup(email="maya@uw.edu", sports=("basketball",))
    post(client, sport="basketball", body="who's down", plan="1", starts_at=form_time(timedelta(days=1)),
         duration="60", location="IMA (Intramural Activities Building)", spots="3")
    with app.app_context():
        game = get_db().execute("SELECT id, title FROM events").fetchone()
    assert game["title"] == "Basketball at the IMA"
    feed = client.get("/feed").data.decode()
    assert "who&#39;s down" in feed and 'name="plan"' in feed and 'id="post-photos"' in feed
    client.post(f"/events/{game['id']}/cancel")
    assert "who&#39;s down" not in client.get("/feed").data.decode()
    assert client.get("/create").headers["Location"].endswith("/clubs")      # the old Create page is the Clubs tab
    css = client.get("/static/style.css").data.decode()
    assert ".feed-card.is-club { box-shadow: none; }" in css and "object-fit: cover; border-radius: 12px" in css


def test_search_finds_clubs_and_people(accounts, client, app):
    accounts.signup(email="officer@uw.edu", name="Riley Park", sports=("tennis",))
    approved_club(app, "officer@uw.edu", name="UW Tennis Club", sport="tennis")
    accounts.logout()
    accounts.signup(email="maya@uw.edu", sports=("running",))
    page = client.get("/search?q=tennis").data.decode()
    assert "UW Tennis Club" in page and "Verified club" in page
    assert "Riley Park" in client.get("/search?q=riley").data.decode()
    assert "Type at least 2 letters" in client.get("/search?q=r").data.decode()
    assert 'href="/search"' in client.get("/feed").data.decode()                   # 🔍 everywhere


def test_admin_cleans_up_keyboard_mashing(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "boss@uw.edu"
    accounts.signup(email="boss@uw.edu", sports=("running",))
    post(client, body="askdgkahjslhdkljashdkljashkjdhas")
    post(client, body="Sunrise 10K, who's in?")
    club = approved_club(app, "boss@uw.edu", name="ajsghd")
    page = client.get("/admin/cleanup").data.decode()
    assert "askdgkahjslhd" in page and "ajsghd" in page and "Sunrise 10K" not in page
    assert "Sunrise 10K" in client.get("/admin/cleanup?all=1").data.decode()
    with app.app_context():
        junk = get_db().execute("SELECT id FROM posts WHERE body LIKE 'askdg%'").fetchone()[0]
    client.post("/admin/cleanup", data={"posts": [str(junk)], "clubs": [str(club)]})
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT body FROM posts").fetchall()[0][0] == "Sunrise 10K, who's in?"
        assert db.execute("SELECT COUNT(*) FROM clubs").fetchone()[0] == 0
    accounts.logout()
    accounts.signup(email="normal@uw.edu")
    assert client.get("/admin/cleanup").status_code == 404


def test_play_has_a_live_map_of_whats_on_now(accounts, client):
    """Like Snap Map: games starting within an hour, going on, or ended in the last 10, as sport bubbles."""
    accounts.signup(email="host@uw.edu", sports=("soccer",))
    for title, place, start in (("Soon", "Denny Field", timedelta(minutes=20)),
                                ("Later", "Husky Track", timedelta(hours=3))):
        client.post("/events/new", data={"title": title, "sport": "soccer", "location": place, "players": "10",
                                         "starts_at": form_time(start), "ends_at": form_time(start + timedelta(hours=1)),
                                         "note": ""})
    play = client.get("/").data.decode()
    assert 'id="play-map"' in play and '"name": "Denny Field"' in play and "playmap.js" in play
    assert '"state": "soon"' in play and '"Husky Track"' not in play               # 3 hours away: not on the map
    assert "1 place with games now" in play and "Clubs for you" not in play


def test_cleanup_rows_keep_their_text_readable(client):
    """The checkbox took the whole row (global input width), squeezing each item into a one-letter column."""
    css = client.get("/static/style.css").data.decode()
    assert '.cleanup-row input[type="checkbox"] { width: 20px;' in css and ".cleanup-row > span { flex: 1 1 auto;" in css


def test_feed_media_is_small_and_opens_big(accounts, client, app):
    """Photos are small squares (4 shown, "+N" on the last), tapped to see big; a video is a small tile that plays
    in place with a button at its bottom-left, and opens full screen when tapped."""
    from io import BytesIO
    from conftest import make_image
    accounts.signup(sports=("running",))
    photos = [(BytesIO(make_image()), f"p{n}.png") for n in range(6)]
    post(client, body="Race day", photos=photos)
    feed = client.get("/feed").data.decode()
    assert feed.count('class="feed-thumb"') == 4 and ">+2</span>" in feed and "data-photos=" in feed
    js = client.get("/static/app.js").data.decode()
    assert "[data-photo-index]" in js and "[data-video-toggle]" in js and "requestFullscreen" in js
    css = client.get("/static/style.css").data.decode()
    assert ".feed-thumb { position: relative; width: 92px; height: 92px;" in css
    assert ".video-toggle { position: absolute; left: 6px; bottom: 6px;" in css


def test_request_to_join_is_one_clear_form(accounts, client, app):
    """Tapping Request to join turns the button into the form (Send / Cancel); Follow steps aside while it's open
    and works in place; the follow tip is only for people who haven't followed or asked yet."""
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    accounts.logout()
    accounts.signup(email="maya@uw.edu", sports=("running",))
    page = client.get(f"/clubs/{club}").data.decode()
    assert "data-close-details>Cancel</a>" in page and 'data-tip="follow-vs-member"' in page
    assert 'id="follow-toggle"' in page and 'action="/clubs/%d/follow" data-inplace' % club in page
    client.post(f"/clubs/{club}/follow")
    page = client.get(f"/clubs/{club}").data.decode()
    assert 'data-tip="follow-vs-member"' not in page and ">Unfollow<" in page
    css = client.get("/static/style.css").data.decode()
    assert ".join-panel[open] > summary { display: none; }" in css
    assert ".join-actions:has(.join-panel[open]) .follow-toggle { display: none; }" in css


def test_small_clarity_fixes(accounts, client):
    """A map's drag never starts pull-to-refresh; "Seen" in messages is said plainly; Online is for esports."""
    js = client.get("/static/app.js").data.decode()
    assert 'closest(".leaflet-container, [data-spot-map], .play-map")' in js
    accounts.signup()
    assert "Show &#34;Seen&#34; in messages" in client.get("/settings").data.decode() or \
        'Show "Seen" in messages' in client.get("/settings").data.decode()
    assert ">Online (esports)</option>" in client.get("/?scope=all").data.decode()


def test_the_clubs_tab_finds_and_registers_clubs(accounts, client, app):
    """The Clubs tab (where Instagram's search is) is the one place for clubs: search them, see yours, find the
    ones for the sports on your profile, and register yours. The old Create page sends people here."""
    accounts.signup(email="officer@uw.edu", sports=("tennis",))
    approved_club(app, "officer@uw.edu", name="UW Tennis Club", sport="tennis")
    approved_club(app, "officer@uw.edu", name="Husky Rowing", sport="rowing")
    accounts.logout()
    accounts.signup(email="maya@uw.edu", sports=("tennis",))
    page = client.get("/clubs").data.decode()
    assert "＋ Register a club" in page and 'href="/clubs/new"' in page and 'placeholder="Search clubs"' in page
    assert 'href="/clubs?mine=1"' in page and 'href="/clubs?fits=1"' in page and 'class="page-title"' not in page
    assert "UW Tennis Club" in page and "Husky Rowing" in page
    fits = client.get("/clubs?fits=1").data.decode()
    assert "UW Tennis Club" in fits and "Husky Rowing" not in fits
    assert client.get("/create").headers["Location"].endswith("/clubs")
    assert '<span class="tab-label">Clubs<' in page and 'class="tab is-active" href="/clubs"' in page


def test_clubs_pin_a_post_owner_picks_posters_and_members_keep_following(accounts, client, app):
    """The owner: clubs pin a post on their page for a day; the owner gives officers permission to post (not every
    officer runs the socials); members follow the club and leaving the club keeps them following."""
    accounts.signup(email="owner@uw.edu", sports=("running",))
    accounts.logout()
    accounts.signup(email="vp@uw.edu", sports=("running",))
    accounts.logout()
    accounts.signup(email="fan@uw.edu", sports=("running",))
    club = approved_club(app, "owner@uw.edu")
    vp, fan = user_id(app, "vp@uw.edu"), user_id(app, "fan@uw.edu")
    with app.app_context():
        get_db().execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)",
                         (club, vp, "2026-09-01 10:00"))
        get_db().execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'member', ?)",
                         (club, fan, "2026-09-01 10:00"))
        get_db().commit()
    # members follow: the owner and both members are its 3 followers
    assert "<strong>3</strong><span>followers</span>" in client.get(f"/clubs/{club}").data.decode()
    client.post(f"/clubs/{club}/leave")                                  # fan leaves: still follows
    with app.app_context():
        assert get_db().execute("SELECT role FROM club_members WHERE user_id = ?", (fan,)).fetchone()[0] == "follower"

    as_user(accounts, "owner@uw.edu")
    client.post(f"/clubs/{club}/officers/{vp}")                          # a new officer: no posting yet
    as_user(accounts, "vp@uw.edu")
    page = client.get(f"/clubs/{club}").data.decode()
    assert "The owner picks which officers post as the club" in page
    assert 'name="as_club"' not in client.get("/feed").data.decode()
    refused = client.post("/posts/new", data={"sport": "running", "body": "sneaky", "as_club": str(club)},
                          content_type="multipart/form-data")
    assert refused.status_code == 403
    as_user(accounts, "owner@uw.edu")
    assert "Posts: <strong>Off</strong>" in client.get(f"/clubs/{club}/officers").data.decode()
    client.post(f"/clubs/{club}/officers", data={"user": vp, "action": "posting_on"})
    as_user(accounts, "vp@uw.edu")
    post(client, as_club=str(club), body="Track night 6pm")
    post(client, as_club=str(club), body="Newer post")
    with app.app_context():
        first = get_db().execute("SELECT id FROM posts WHERE body = 'Track night 6pm'").fetchone()[0]
    page = client.get(f"/clubs/{club}").data.decode()
    assert page.index("Newer post") < page.index("Track night 6pm") and "📌 Pin for 24 hours" in page
    client.post(f"/posts/{first}/pin")
    page = client.get(f"/clubs/{club}").data.decode()
    assert "📌 Pinned" in page and page.index("Track night 6pm") < page.index("Newer post") and ">Unpin<" in page
    with app.app_context():
        get_db().execute("UPDATE posts SET pinned_until = '2020-01-01 00:00' WHERE id = ?", (first,))  # a day later
        get_db().commit()
    page = client.get(f"/clubs/{club}").data.decode()
    assert "📌 Pinned" not in page and page.index("Newer post") < page.index("Track night 6pm")
    as_user(accounts, "fan@uw.edu")
    assert client.post(f"/posts/{first}/pin").status_code == 403         # only the club's posters pin


def test_long_lists_have_a_search_box(accounts, client):
    """The owner: a search bar in the dropdowns and in choosing your sports. app.js puts a small box above every
    long dropdown (sports, places) and above the sports chips; it hides on short lists (3 places for a sport)."""
    accounts.signup(sports=("running",))
    js = client.get("/static/app.js").data.decode()
    assert 'document.querySelectorAll("[data-chip-search]")' in js and "const LONG = 15;" in js
    assert "watch.takeRecords()" in js          # the places list rebuilt for a sport resets the box
    assert "data-chip-search" in client.get("/profile/edit/sports").data.decode()
    css = client.get("/static/style.css").data.decode()
    assert ".select-search { display: grid;" in css and ".list-search[hidden] { display: none; }" in css


def test_bot_round_the_plus_button_never_covers_the_last_links(accounts, client):
    """Bot round (screen audit): at 320px the ＋ button sat on the footer's links, and the My clubs feed's two
    links ran into each other. The footer gets room under it; the two links wrap instead of overlapping."""
    accounts.signup(sports=("running",))
    css = client.get("/static/style.css").data.decode()
    assert "body.has-app-nav .site-footer { padding-bottom: 84px; }" in css and "padding-right: 74px; } }" in css
    assert ".feed-find-club { margin: -4px 0 10px; display: flex; flex-wrap: wrap;" in css
    page = client.get("/feed?show=myclubs").data.decode()
    assert "Find a club to follow →</a><a " in page


def test_play_map_opens_full_screen_like_snap_map_and_phone_posts_are_dense(accounts, client):
    """The owner: tap the map for a full screen (with a back button), like Snap Map, with real colors; and posts
    were still too big on a phone: there they're flat rows like Twitter (one-line name, small photos)."""
    accounts.signup(sports=("running",))
    play = client.get("/").data.decode()
    assert "data-map-open" in play and "data-map-close" in play and "← Back" in play and "data-map-recenter" in play
    js = client.get("/static/playmap.js").data.decode()
    assert 'history.pushState({ playMap: true }, "", "#map")' in js and "popstate" in js
    assert "dragging: false" in js and "tile.openstreetmap.org" in js           # a still preview, colorful tiles
    assert "cartocdn" not in js                         # CARTO's tiles need a paid key ("API KEY REQUIRED")
    css = client.get("/static/style.css").data.decode()
    assert ".live-map-wrap.is-full { position: fixed; inset: 0;" in css and ".play-map .leaflet-tile-pane { filter: grayscale" not in css
    assert ".feed > .feed-card { margin: 0 -16px; padding: 9px 16px; border-width: 0 0 1px;" in css
    assert ".feed-thumb { width: 72px; height: 72px;" in css


def test_it_looks_like_instagram(accounts, client, app):
    """The owner: "make it look like insta, the pages and segments too, straight up copy it". White top bar with a
    bold wordmark (not cursive), icon-only tabs with your picture as Profile, ♡ / 💬 icons and ⋯ top right on posts, a profile
    with posts · friends · clubs beside the picture, sports as round highlights, icon tabs, grey search boxes."""
    accounts.signup(email="maya@uw.edu", sports=("running", "tennis"))
    me = user_id(app, "maya@uw.edu")
    post(client, body="Track at 6")
    css = client.get("/static/style.css").data.decode()
    assert "--wordmark: var(--display);" in css and "cursive" not in css and ".topbar { background: var(--bg);" in css
    assert "color: var(--purple);\n  letter-spacing: 0; }" in css and ".appnav .brand-accent { color: var(--gold);" in css  # Sportive purple, Circle gold
    assert ".appnav .tab-label { position: absolute;" in css            # icon-only bottom bar on phones
    feed = client.get("/feed").data.decode()
    assert 'class="tab-me"' in feed and '#i-heart"/>' in feed and '#i-chat"/>' in feed
    profile = client.get(f"/u/{me}").data.decode()
    assert 'class="profile-stats"' in profile and "<strong>1</strong><span>post</span>" in profile
    assert 'class="profile-highlights"' in profile and 'href="/settings">Settings' in profile
    assert 'data-tab-button="posts" title="Posts">' in profile and "#i-grid" in profile
    assert '<button class="visually-hidden">Search</button>' in client.get("/search").data.decode()


def test_bot_round_instagram_look_keeps_contrast(client):
    """Bot round after the Instagram look: the landing splash and 🐾 Team used the header color, which turned
    white (white text on white); grey text on grey boxes and the red like count were too light; Sign up was
    hard to read in dark mode; the name gave way before the time on small phones."""
    css = client.get("/static/style.css").data.decode()
    assert ".husky-hero, .team-pill { background: #4b2e83; }" in css
    assert ":root { --muted: #6b6b6b; }" in css and ':root[data-theme="dark"] { --muted: #a8a8a8; }' in css
    assert ".nav-cta, .nav-cta:hover { background: #4b2e83; color: #fff !important; }" in css
    assert "color: #e0245e; }" in css and ".feed-who .feed-name { flex: 0 1 auto; max-width: 68%; }" in css


def test_clubs_are_simple_one_poster_one_row_one_way_to_post(accounts, client, app):
    """The owner: "the QR code has 3 options, that just confuses people: make it as simple and as effective as
    possible for clubs". Share is one poster with one button (the link copies with a tap); officers get one row
    (Edit club · Share · + Event, officers in Edit club); posting is the ＋, which opens set to post as the club."""
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    share = client.get(f"/clubs/{club}/share").data.decode()
    assert share.count('class="btn') == 2 and "Print or save poster" in share and "data-copy=" in share
    assert "Scan the code" in share and ">Flyer<" not in share and ">Share link<" not in share
    assert client.get(f"/flyer?club={club}").headers["Location"].endswith(f"/clubs/{club}/share")
    page = client.get(f"/clubs/{club}").data.decode()
    assert 'class="officer-buttons"' in page and "+ Event" in page and "club-post-form" not in page
    assert f'href="/feed?as={club}#post"' in page and "Tap <strong>＋</strong> to post as" in page
    assert "Manage officers" in client.get(f"/clubs/{club}/edit").data.decode()


def test_no_sideways_scroll_on_iphone_and_posts_are_separate_small_cards(client):
    """The owner: on an iPhone 16 the ＋ sheet had to be moved sideways to see Video (Safari zooms into boxes under
    16px, and long dropdowns could push past the screen); nothing should scroll sideways on any device. And feed
    posts ran together: each is a small card now, with a little gap."""
    css = client.get("/static/style.css").data.decode()
    assert ".list-search, .chip-more select.chip, .post-sheet input, .post-sheet select, .post-sheet textarea { font-size: 16px; }" in css
    assert "html, body { overflow-x: clip; }" in css and ".select-search { grid-template-columns: minmax(0, 1fr); }" in css
    assert ".feed { gap: 8px; }" in css and ".feed > .feed-card { margin: 0; padding: 9px 12px; border: 1px solid var(--line); border-radius: 12px; }" in css


def test_bot_round_edit_club_links_wrap_on_small_phones(accounts, client, app):
    """Bot round: at 320px "Manage officers and who posts →" and "Add a logo →" ran into each other on Edit club.
    They're a wrapping row now (no "·" between them)."""
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    page = client.get(f"/clubs/{club}/edit").data.decode()
    assert "who posts →</a>\n      <a " in page
    css = client.get("/static/style.css").data.decode()
    assert ".edit-links { margin: 0 0 10px; font-size: .9rem; display: flex; flex-wrap: wrap; gap: 4px 16px; }" in css


def test_a_plan_can_be_no_limit_anyone_can_come(accounts, client, app):
    """The owner: making a plan asks how many people you need, but sometimes you just want anyone to come (going to
    the run club's run). "No limit: anyone can come" makes the game with no cap; anyone can tap I'm in."""
    accounts.signup(email="maya@uw.edu", sports=("running",))
    feed = client.get("/feed").data.decode()
    assert 'name="no_limit"' in feed and "No limit: anyone can come" in feed and "data-plan-spots" in feed
    post(client, sport="running", body="Run club 5K, come along", plan="1", starts_at=form_time(timedelta(days=1)),
         duration="60", location="Burke-Gilman Trail", no_limit="1")
    with app.app_context():
        game = get_db().execute("SELECT id, max_players FROM events").fetchone()
    assert game["max_players"] is None
    page = client.get("/feed").data.decode()
    assert "Run club 5K" in page and "<strong>1</strong> going" in page
    refused = post(client, sport="running", body="x", plan="1", starts_at=form_time(timedelta(days=1)),
                   duration="60", location="Burke-Gilman Trail", spots="").data.decode()
    assert "Or tick No limit: anyone can come." in refused
    accounts.logout()
    accounts.signup(email="sam@uw.edu", sports=("running",))
    client.post(f"/events/{game['id']}/join")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (game["id"],)).fetchone()[0] == 2


def test_sport_search_picks_what_you_typed(client):
    """The owner: searching the sport in the post box kept showing the first pick (Archery). In a form the current
    pick no longer stays when it doesn't match, and the best match is picked for you right away: a name starting
    with what you typed first ("ten" -> Tennis, not Table Tennis); no match goes back to "Choose"."""
    js = client.get("/static/app.js").data.decode()
    assert "(autoSubmits && option.selected) || matches(words, option.textContent)" in js
    assert 'const best = real.find(start) || real[0];' in js and 'if (!words.length) select.value = before;' in js


def test_a_club_can_post_for_members_only(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    composer = client.get("/feed").data.decode()
    assert 'name="members_only"' in composer and "🔒 Members only" in composer
    page = post(client, as_club=str(club), body="Team dinner Friday, members only", members_only="1").data.decode()
    assert "Only its members see it." in page and "🔒 Members only" in page
    post(client, as_club=str(club), body="Members track night", members_only="1", plan="1",
         starts_at=form_time(timedelta(days=2)), duration="60", location="Husky Track", spots="10")
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT members_only FROM events WHERE note = 'Members track night'").fetchone()[0] == 1
        post_id = db.execute("SELECT id FROM posts WHERE body LIKE 'Team dinner%'").fetchone()[0]
    accounts.logout()
    accounts.signup(email="outsider@uw.edu", sports=("running",))           # not a member: never sees it
    for url in ("/feed", "/feed?sport=running", f"/clubs/{club}", "/clubs/updates?all=1"):
        assert "Team dinner" not in client.get(url).data.decode()
    assert client.get(f"/posts/{post_id}").status_code == 404
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'member', '2026-01-01')",
                   (club, user_id(app, "outsider@uw.edu")))
        db.commit()
    assert "Team dinner" in client.get("/feed").data.decode()                    # a member does
    assert client.get(f"/posts/{post_id}").status_code == 200
    accounts.logout()
    accounts.signup(email="me@uw.edu", sports=("running",))
    post(client, body="Just me", members_only="1")                              # only clubs can: ignored
    with app.app_context():
        assert get_db().execute("SELECT members_only FROM posts WHERE body = 'Just me'").fetchone()[0] == 0


def test_a_club_shares_its_poster_to_an_instagram_story(accounts, client, app):
    """The owner: the QR is nice for tables, but clubs need "share to Instagram" that opens the story ready to post.
    The phone draws a story picture (the club, its QR code and link) and opens its share menu: Instagram → Story."""
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    share = client.get(f"/clubs/{club}/share").data.decode()
    assert "Share to Instagram story" in share and 'data-story="Run with UW Run Club"' in share
    assert f'data-story-qr="/clubs/{club}/qr.svg"' in share and 'data-story-file="uw-run-club-story.png"' in share
    assert 'data-story-emoji="' in share                                    # no logo yet: the sport's emoji
    js = client.get("/static/app.js").data.decode()
    assert "navigator.share({ files: [file] })" in js and "canvas.width = 1080; canvas.height = 1920;" in js
    assert "a.download = file.name;" in js                                  # laptops save the picture instead


def test_officers_sign_up_straight_to_their_club(accounts, client, app):
    page = client.get("/signup").data.decode()
    assert "Club officer? Register your club" in page and 'href="/signup?club=1"' in page
    page = client.get("/signup?club=1").data.decode()
    assert "Register your club" in page and "Club officer?" not in page and "Step 1 of 3" in page
    response = client.post("/signup", data={"full_name": "Olive Officer", "email": "olive@uw.edu",
                                            "password": "purple-and-gold", "password2": "purple-and-gold",
                                            "birth_date": "2004-03-01", "grad_year": ""})
    assert response.headers["Location"] == "/verify"                      # no sports step, no texts step
    assert "Step 2 of 3" in client.get("/verify").data.decode()
    response = client.post("/verify", data={"code": accounts.code_for("olive@uw.edu")})
    assert response.headers["Location"] == "/clubs/new"
    page = client.get("/clubs/new").data.decode()                           # no photo step in the way
    assert "Now your club. Your profile can wait" in page and 'name="name"' in page
    assert "Your profile can wait" in client.get("/notifications").data.decode()
    assert client.get("/signup?club=1").headers["Location"] == "/clubs/new"  # already in: to the club form
    accounts.logout()
    client.get("/signup?club=1")
    client.get("/signup")                                                    # "Not an officer?": the usual steps
    response = client.post("/signup", data={"full_name": "Sam Student", "email": "sam@uw.edu",
                                            "password": "purple-and-gold", "password2": "purple-and-gold",
                                            "birth_date": "2004-03-01", "grad_year": ""})
    assert response.headers["Location"] == "/signup/sports"
    for page in ("/clubs", "/"):
        assert 'href="/signup?club=1"' in client.get(page).data.decode()
