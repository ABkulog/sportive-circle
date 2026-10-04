"""Videos on feed posts: one per post, up to a minute, location scrubbed, within the space quota."""
import os
import struct
from io import BytesIO

from conftest import make_image
from sportive.db import get_db
from sportive.videos import duration_seconds, scrub_location
from test_feed import post


def box(kind, payload):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def mp4(seconds, filler=0):
    mvhd = box(b"mvhd", b"\0\0\0\0" + struct.pack(">IIII", 0, 0, 1000, int(seconds * 1000)) + b"\0" * 80)
    where = box(b"udta", box(b"\xa9xyz", b"\0\x12\x15\xc7+47.6553-122.3035/"))
    return (box(b"ftyp", b"isom\0\0\0\0isomiso2") + box(b"moov", mvhd + where)
            + box(b"mdat", b"\0" * filler))


def test_reading_length_and_scrubbing_location():
    assert duration_seconds(mp4(42.5)) == 42.5
    clean = scrub_location(mp4(10))
    assert b"+47.6553-122.3035/" not in clean and b"+00.0000-000.0000/" in clean and len(clean) == len(mp4(10))


def test_post_a_video_watch_it_and_delete_it(accounts, client, app):
    accounts.signup(email="maya@uw.edu", sports=("basketball",))
    page = post(client, sport="basketball", body="Game winner 🏀", video=(BytesIO(mp4(30)), "clip.mov")).data.decode()
    assert "Posted!" in page and "<video" in page
    with app.app_context():
        post_id, name = get_db().execute("SELECT post_id, filename FROM post_videos").fetchone()
    path = os.path.join(os.path.dirname(app.config["DATABASE"]), "videos", name)
    assert os.path.exists(path) and b"+47.6553" not in open(path, "rb").read()          # GPS gone from the file
    played = client.get(f"/posts/{post_id}/video", headers={"Range": "bytes=0-99"})
    assert played.status_code == 206 and len(played.data) == 100 and played.mimetype == "video/mp4"
    client.post(f"/posts/{post_id}/delete")
    assert not os.path.exists(path)                                                    # the file goes too


def test_videos_are_checked(accounts, client, app):
    accounts.signup(sports=("basketball",))
    long_one = post(client, sport="basketball", video=(BytesIO(mp4(75)), "long.mp4")).data.decode()
    assert "up to 1 minute. This one is 75 seconds" in long_one
    not_video = post(client, sport="basketball", video=(BytesIO(b"hello there, not a video"), "x.mp4")).data.decode()
    assert "isn&#39;t supported" in not_video
    both = post(client, sport="basketball", video=(BytesIO(mp4(5)), "a.mp4"),
                photos=[(BytesIO(make_image()), "a.png")]).data.decode()
    assert "photos or a video, not both" in both
    app.config["VIDEO_QUOTA_MB"] = 0.001                                                # space is full
    assert "Video space is full" in post(client, sport="basketball", video=(BytesIO(mp4(5, 2000)), "a.mp4")).data.decode()
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM post_videos").fetchone()[0] == 0


def test_deleting_an_account_removes_its_video_files(accounts, client, app):
    accounts.signup(email="maya@uw.edu", sports=("basketball",))
    post(client, sport="basketball", video=(BytesIO(mp4(5)), "a.mp4"))
    with app.app_context():
        name = get_db().execute("SELECT filename FROM post_videos").fetchone()[0]
    path = os.path.join(os.path.dirname(app.config["DATABASE"]), "videos", name)
    client.post("/profile/delete", data={"password": "purple-and-gold", "confirm": "DELETE"})
    assert not os.path.exists(path)
