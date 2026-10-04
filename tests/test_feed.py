"""The feed: posts with a sport tag, photos, plans with "I'm in", and what clubs and games add to it."""
import re
from datetime import timedelta
from io import BytesIO

from conftest import make_image
from sportive.db import get_db
from sportive.timeutil import now_local, to_db

def approved_club(app, officer_email, name="UW Run Club", sport="running"):
    """A verified club with one officer (made directly: the sign-up form is tested in test_app.py)."""
    with app.app_context():
        db = get_db()
        officer = db.execute("SELECT id FROM users WHERE email = ?", (officer_email,)).fetchone()[0]
        club = db.execute(
            """INSERT INTO clubs (name, sport, description, created_by, status, created_at)
               VALUES (?, ?, 'Weekly runs, all paces.', ?, 'approved', ?)""",
            (name, sport, officer, to_db(now_local()))).lastrowid
        db.execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, 'officer', ?)",
                   (club, officer, to_db(now_local())))
        db.commit()
    return club


def user_id(app, email):
    with app.app_context():
        return get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]


def as_user(accounts, email):
    accounts.logout()
    accounts.login(email=email)


def post(client, **fields):
    data = {"sport": "running", "body": "", **fields}
    return client.post("/posts/new", data=data, content_type="multipart/form-data", follow_redirects=True)


def form_time(delta):
    return (now_local() + delta).strftime("%Y-%m-%dT%H:%M")


def test_posts_reach_people_who_play_that_sport(accounts, client, app):
    accounts.signup(email="maya@uw.edu", name="Maya Chen", sports=("running",))
    page = post(client, body="First 10K under 50 minutes! 🏃").data.decode()
    assert "Posted!" in page and "First 10K under 50 minutes!" in page and "#running" in page
    accounts.logout()
    accounts.signup(email="runner@uw.edu", sports=("running", "hiking"))
    assert "First 10K under 50 minutes!" in client.get("/feed").data.decode()          # same sport: in the feed
    accounts.logout()
    accounts.signup(email="hooper@uw.edu", sports=("basketball",))
    assert "First 10K under 50 minutes!" not in client.get("/feed").data.decode()      # not their sport
    channel = client.get("/feed?sport=running").data.decode()                          # but the #running channel
    assert "First 10K under 50 minutes!" in channel and 'aria-current="page"' in channel


def test_a_post_needs_a_sport_and_something_to_say(accounts, client):
    accounts.signup()
    assert "Tag your post with a sport." in post(client, sport="", body="hi").data.decode()
    assert "Write something, or add a photo or a video." in post(client, body="   ").data.decode()
    assert "up to 1000 characters" in post(client, body="x" * 1001).data.decode()


def test_up_to_ten_photos_cleaned_and_only_for_people_who_can_see_the_post(accounts, client, app):
    accounts.signup(email="maya@uw.edu", sports=("weightlifting",))
    photos = [(BytesIO(make_image()), f"pump{n}.png") for n in range(3)]
    page = post(client, sport="weightlifting", body="Leg day PR", photos=photos).data.decode()
    assert "Posted!" in page and "1/3" in page and "3/3" in page
    with app.app_context():
        post_id = get_db().execute("SELECT id FROM posts").fetchone()[0]
    image = client.get(f"/posts/{post_id}/photos/2")
    assert image.status_code == 200 and image.mimetype == "image/jpeg" and image.data[:2] == b"\xff\xd8"
    too_many = [(BytesIO(make_image()), f"p{n}.png") for n in range(11)]
    assert "up to 10 photos" in post(client, sport="weightlifting", photos=too_many).data.decode()
    assert "Write something" not in post(client, sport="weightlifting", photos=[(BytesIO(make_image()), "a.png")]).data.decode()
    accounts.logout()
    assert client.get(f"/posts/{post_id}/photos/2").status_code == 302                  # logged out: log in first


def test_a_plan_post_is_a_real_game_people_can_join(accounts, client, app):
    accounts.signup(email="maya@uw.edu", name="Maya Chen", sports=("hiking",))
    page = post(client, sport="hiking", body="Hiking Mt Si tomorrow, have a car, need 2 more",
                plan="1", starts_at=form_time(timedelta(days=1)), duration="480",
                location="Off campus (see note)", spots="2").data.decode()
    assert "People can tap I&#39;m in" in page and "Hosting" in page and "1</strong>/3 going" in page
    with app.app_context():
        db = get_db()
        event = db.execute("SELECT * FROM events").fetchone()
        assert db.execute("SELECT event_id FROM posts").fetchone()[0] == event["id"]
    assert event["title"] == "Hiking Mt Si tomorrow, have a car, need 2 more" and event["max_players"] == 3
    assert "Hiking Mt Si" in event["note"]
    accounts.logout()
    accounts.signup(email="sam@uw.edu", sports=("hiking",))
    feed = client.get("/feed").data.decode()
    assert "I'm in</button>" in feed and "posted a game" not in feed                # shown once, as the post
    client.post(f"/events/{event['id']}/join")
    assert "You're in</span>" in client.get("/feed").data.decode()


def test_plans_are_checked_like_games(accounts, client):
    accounts.signup(sports=("basketball",))
    plan = dict(plan="1", sport="basketball", body="Run it back", duration="120", spots="3")
    assert "can&#39;t be played at" in post(client, **plan, starts_at=form_time(timedelta(days=1)),
                                             location="Burke-Gilman Trail").data.decode()
    assert "hasn&#39;t passed" in post(client, **plan, starts_at=form_time(timedelta(hours=-2)),
                                       location="IMA (Intramural Activities Building)").data.decode()
    assert "How many more people" in post(client, **{**plan, "spots": "0"}, starts_at=form_time(timedelta(days=1)),
                                          location="IMA (Intramural Activities Building)").data.decode()


def test_blocked_and_suspended_people_disappear_from_the_feed(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="troll@uw.edu", sports=("running",))
    post(client, body="Troll post")
    troll = user_id(app, "troll@uw.edu")
    accounts.logout()
    accounts.signup(email="me@uw.edu", sports=("running",))
    assert "Troll post" in client.get("/feed").data.decode()
    client.post(f"/block/{troll}")
    assert "Troll post" not in client.get("/feed").data.decode()
    accounts.logout()
    accounts.signup(email="other@uw.edu", sports=("running",))
    assert "Troll post" in client.get("/feed").data.decode()
    accounts.logout()
    accounts.signup(email="admin@uw.edu", sports=("running",))
    client.post(f"/admin/users/{troll}/suspend")
    as_user(accounts, "other@uw.edu")
    assert "Troll post" not in client.get("/feed").data.decode()


def test_report_and_delete_posts(accounts, client, app):
    app.config["ADMIN_EMAILS"] = "admin@uw.edu"
    accounts.signup(email="maya@uw.edu", sports=("running",))
    post(client, body="Something not OK", photos=[(BytesIO(make_image()), "a.png")])
    with app.app_context():
        post_id = get_db().execute("SELECT id FROM posts").fetchone()[0]
    accounts.logout()
    accounts.signup(email="sam@uw.edu", sports=("running",))
    feed = client.get("/feed").data.decode()
    assert f"/report/post/{post_id}" in feed and f"/posts/{post_id}/delete" not in feed   # not theirs to delete
    assert client.post(f"/posts/{post_id}/delete").status_code == 403
    client.post(f"/report/post/{post_id}", data={"reason": "sexual"})
    accounts.logout()
    accounts.signup(email="admin@uw.edu", sports=("running",))
    queue = client.get("/admin/reports").data.decode()
    assert "Feed post" in queue and "Something not OK" in queue and "📷 [1 photo]" in queue
    assert f"/posts/{post_id}" in queue
    assert f"/posts/{post_id}/delete" in client.get(f"/posts/{post_id}").data.decode()    # admins can delete it
    client.post(f"/posts/{post_id}/delete")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM post_photos").fetchone()[0] == 0     # photos go too


def test_authors_delete_their_posts_and_a_plan_keeps_its_game(accounts, client, app):
    accounts.signup(sports=("hiking",))
    post(client, sport="hiking", body="Hike Saturday", plan="1", starts_at=form_time(timedelta(days=2)),
         duration="240", location="Off campus (see note)", spots="3")
    with app.app_context():
        post_id = get_db().execute("SELECT id FROM posts").fetchone()[0]
    page = client.post(f"/posts/{post_id}/delete", follow_redirects=True).data.decode()
    assert "Post deleted. The plan&#39;s game is still on" in page
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM events WHERE cancelled = 0").fetchone()[0] == 1


def test_posting_is_limited_per_hour(accounts, client):
    accounts.signup(sports=("running",))
    for n in range(10):
        post(client, body=f"Post {n}")
    assert "up to 10 times an hour" in post(client, body="One more").data.decode()


def test_club_posts_and_new_games_fill_the_feed(accounts, client, app):
    accounts.signup(email="officer@uw.edu", sports=("running",))
    club = approved_club(app, "officer@uw.edu")
    client.post(f"/clubs/{club}/posts", data={"body": "Tuesday run moved to Green Lake 🏃"})
    accounts.logout()
    accounts.signup(email="hooper@uw.edu", sports=("basketball",))
    client.post("/events/new", data={"title": "Pickup 5v5", "sport": "basketball",
                                     "location": "IMA (Intramural Activities Building)", "skill_level": "Casual",
                                     "starts_at": form_time(timedelta(days=1)),
                                     "ends_at": form_time(timedelta(days=1, hours=2)), "players": "10", "note": ""})
    accounts.logout()
    accounts.signup(email="fresh@uw.edu", sports=("running", "basketball"))
    feed = client.get("/feed").data.decode()
    assert "Tuesday run moved to Green Lake" in feed and "UW Run Club" in feed and "Club ·" in feed
    assert "posted a game" not in feed and "Pickup 5v5" not in feed                    # games are on Play
    followed = client.post(f"/clubs/{club}/follow", data={"next": "/feed"})
    assert followed.headers["Location"] == "/feed"                                       # + Follow stays on the feed
    assert 'class="head-follow"' not in client.get("/feed").data.decode()


def test_feed_is_home_and_has_rules(accounts, client):
    accounts.signup()
    home = client.get("/feed").data.decode()
    assert 'class="tab is-active" href="/feed"' in home and ">Feed <" in home and ">Play<" in home
    assert "Make it a plan" in home and 'href="/rules"' in home and 'data-max-files="10"' in home
    rules = client.get("/rules").data.decode()
    assert "Athletic, not thirsty" in rules and "18 and older" in rules


def test_older_posts_page_by_page(accounts, client, app):
    accounts.signup(sports=("running",))
    me = user_id(app, "dubs@uw.edu")
    with app.app_context():
        db = get_db()
        for n in range(30):
            db.execute("INSERT INTO posts (author_id, sport, body, created_at) VALUES (?, 'running', ?, ?)",
                       (me, f"Run number {n}", to_db(now_local() - timedelta(minutes=30 - n))))
        db.commit()
    first = client.get("/feed").data.decode()
    assert "Run number 29" in first and "Run number 2<" not in first
    older = re.search(r'href="(/feed\?before=[^"]+)"', first).group(1).replace("&amp;", "&")
    second = client.get(older).data.decode()
    assert "Run number 2<" in second and "Run number 29" not in second


def test_home_shows_how_many_new_posts_until_you_open_the_feed(accounts, client):
    accounts.signup(email="me@uw.edu", sports=("running",))
    accounts.logout()
    accounts.signup(email="maya@uw.edu", sports=("running",))
    post(client, body="Sunrise run anyone?")
    post(client, body="Track at 7")
    post(client, sport="basketball", body="Not my sport")                 # not counted for a runner
    as_user(accounts, "me@uw.edu")
    games = client.get("/").data.decode()
    assert re.search(r'href="/feed"[^>]*>.*?<span class="count-dot">2</span>', games, re.S)  # on the Home tab
    assert "LIVE" in games
    client.get("/feed")                                                    # seen
    assert '<span class="count-dot">2</span>' not in client.get("/").data.decode()


def test_paging_never_skips_posts_from_the_same_minute(accounts, client, app):
    accounts.signup(sports=("running",))
    me = user_id(app, "dubs@uw.edu")
    same_minute = to_db(now_local() - timedelta(minutes=5))
    with app.app_context():
        db = get_db()
        for n in range(40):                                    # 40 posts in one minute: across two pages
            db.execute("INSERT INTO posts (author_id, sport, body, created_at) VALUES (?, 'running', ?, ?)",
                       (me, f"Lap {n}.", same_minute))
        db.commit()
    seen = []
    page = client.get("/feed").data.decode()
    while True:
        seen += re.findall(r"Lap (\d+)\.", page)
        more = re.search(r'href="(/feed\?before=[^"]+)"', page)
        if not more:
            break
        page = client.get(more.group(1).replace("&amp;", "&")).data.decode()
    assert sorted(map(int, seen)) == list(range(40))          # every one, once
