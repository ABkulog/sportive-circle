"""Deleting your own chat messages, for everyone."""
from io import BytesIO
from datetime import timedelta

from conftest import event_id_from, make_image
from sportive.db import get_db
from sportive.timeutil import now_local
from test_feed import as_user, user_id


def _friends(app, a, b):
    with app.app_context():
        get_db().execute("INSERT INTO friendships (requester_id, addressee_id, status, created_at)"
                         " VALUES (?, ?, 'accepted', '2026-09-01 10:00')", (a, b))
        get_db().commit()


def test_delete_a_direct_message_for_everyone(accounts, client, app):
    accounts.signup(email="maya@uw.edu", name="Maya Chen")
    accounts.logout()
    accounts.signup(email="sam@uw.edu", name="Sam Okafor")
    maya, sam = user_id(app, "maya@uw.edu"), user_id(app, "sam@uw.edu")
    _friends(app, maya, sam)
    client.post(f"/messages/{maya}", data={"body": "oops wrong chat"})
    client.post(f"/messages/{maya}", data={"photo": (BytesIO(make_image()), "a.png")}, content_type="multipart/form-data")
    with app.app_context():
        first, photo_msg = [r[0] for r in get_db().execute("SELECT id FROM direct_messages ORDER BY id")]
        photo_id = get_db().execute("SELECT photo_id FROM direct_messages WHERE id = ?", (photo_msg,)).fetchone()[0]
    answer = client.post("/chat/delete", data={"kind": "dm", "id": first}, headers={"Accept": "application/json"})
    assert answer.json == {"id": first, "deleted": True, "body": "🚫 Message deleted"}
    client.post("/chat/delete", data={"kind": "dm", "id": photo_msg})
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM chat_photos WHERE id = ?", (photo_id,)).fetchone()[0] == 0
    as_user(accounts, "maya@uw.edu")
    assert client.post("/chat/delete", data={"kind": "dm", "id": first}).status_code == 404   # not hers to delete
    poll = client.get(f"/messages/{sam}/poll?after=0&from={first}").json
    assert poll["deleted"] == [first, photo_msg]
    assert all(m["body"] == "🚫 Message deleted" and not m["photo"] and m["deleted"] for m in poll["messages"])
    page = client.get(f"/messages/{sam}").data.decode()
    assert "oops wrong chat" not in page and "is-deleted" in page
    assert "🚫 Message deleted" in client.get("/messages").data.decode()                       # inbox preview too


def test_delete_a_game_chat_message(accounts, client, app):
    accounts.signup(email="host@uw.edu")
    event_id = event_id_from(client.post("/events/new", data={
        "title": "Pickup 5v5", "sport": "basketball", "location": "IMA (Intramural Activities Building)",
        "skill_level": "Casual", "starts_at": (now_local() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
        "ends_at": (now_local() + timedelta(days=1, hours=2)).strftime("%Y-%m-%dT%H:%M"), "players": "10", "note": ""}))
    client.post(f"/events/{event_id}/chat", data={"body": "bring the ball"})
    with app.app_context():
        message = get_db().execute("SELECT id FROM event_messages").fetchone()[0]
    client.post("/chat/delete", data={"kind": "game", "id": message})
    poll = client.get(f"/events/{event_id}/chat/poll?after=0&from={message}").json
    assert poll["deleted"] == [message] and poll["messages"][0]["body"] == "🚫 Message deleted"
    assert 'data-delete-url="/chat/delete"' in client.get(f"/events/{event_id}/chat").data.decode()
