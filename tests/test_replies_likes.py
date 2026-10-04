"""Replies and 🔥 on feed posts."""
from sportive.db import get_db
from test_feed import as_user, post, user_id


def _post_id(app):
    with app.app_context():
        return get_db().execute("SELECT MAX(id) FROM posts").fetchone()[0]


def test_likes_toggle_count_and_tell_the_author_once(accounts, client, app):
    accounts.signup(email="maya@uw.edu", name="Maya Chen", sports=("running",))
    post(client, body="5K PR!")
    post_id = _post_id(app)
    for email in ("sam@uw.edu", "jo@uw.edu"):
        accounts.logout()
        accounts.signup(email=email, name=email.split("@")[0].title() + " Husky", sports=("running",))
        client.post(f"/posts/{post_id}/like", data={"next": "/feed"})
    feed = client.get("/feed").data.decode()
    assert 'react-button is-on' in feed and "🔥 <span>2</span>" in feed
    client.post(f"/posts/{post_id}/like")                                       # a second tap takes it back
    assert "🔥 <span>1</span>" in client.get("/feed").data.decode()
    as_user(accounts, "maya@uw.edu")
    bell = client.get("/notifications").data.decode()
    assert bell.count("liked your post") == 1 and "Jo and 1 other liked your post" in bell   # one notice, updated


def test_replies_thread_notify_and_can_be_deleted_and_reported(accounts, client, app):
    accounts.signup(email="maya@uw.edu", name="Maya Chen", sports=("hiking",))
    post(client, sport="hiking", body="Best trail for a sunrise hike?")
    post_id = _post_id(app)
    accounts.logout()
    accounts.signup(email="sam@uw.edu", name="Sam Okafor", sports=("hiking",))
    client.post(f"/posts/{post_id}/replies", data={"body": "Rattlesnake Ledge, go early!"})
    page = client.get(f"/posts/{post_id}").data.decode()
    assert "1 reply" in page and "Rattlesnake Ledge, go early!" in page
    assert "💬 <span>1</span>" in client.get("/feed").data.decode()
    assert "Replies are 1 to 500" in client.post(f"/posts/{post_id}/replies", data={"body": " "},
                                                 follow_redirects=True).data.decode()
    with app.app_context():
        reply_id = get_db().execute("SELECT id FROM post_replies").fetchone()[0]
    as_user(accounts, "maya@uw.edu")
    assert "Sam replied to your post: “Rattlesnake Ledge, go early!”" in client.get("/notifications").data.decode()
    client.post(f"/report/reply/{reply_id}", data={"reason": "spam"})
    with app.app_context():
        assert get_db().execute("SELECT target_type FROM reports").fetchone()[0] == "reply"
    client.post(f"/replies/{reply_id}/delete")                                  # the post's author can remove it
    assert "Rattlesnake Ledge" not in client.get(f"/posts/{post_id}").data.decode()


def test_strangers_cant_delete_replies_and_blocks_hide_them(accounts, client, app):
    accounts.signup(email="maya@uw.edu", sports=("hiking",))
    post(client, sport="hiking", body="Hike?")
    post_id = _post_id(app)
    accounts.logout()
    accounts.signup(email="troll@uw.edu", name="Troll Husky", sports=("hiking",))
    client.post(f"/posts/{post_id}/replies", data={"body": "lol no"})
    with app.app_context():
        reply_id = get_db().execute("SELECT id FROM post_replies").fetchone()[0]
    accounts.logout()
    accounts.signup(email="sam@uw.edu", sports=("hiking",))
    assert client.post(f"/replies/{reply_id}/delete").status_code == 403
    assert "lol no" in client.get(f"/posts/{post_id}").data.decode()
    client.post(f"/block/{user_id(app, 'troll@uw.edu')}")
    page = client.get(f"/posts/{post_id}").data.decode()
    assert "lol no" not in page and "No replies yet" in page                    # hidden, and not counted
