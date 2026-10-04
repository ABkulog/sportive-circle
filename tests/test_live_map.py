"""Play's live map (like Snap Map): starting within an hour, going on, or ended in the last 10 minutes."""
from datetime import timedelta

from sportive.db import get_db
from sportive.timeutil import now_local, to_db
from test_feed import user_id


def add_game(app, host, title, place, start, end):
    now = now_local()
    with app.app_context():
        db = get_db()
        game = db.execute(
            """INSERT INTO events (host_id, title, sport, location, starts_at, ends_at, skill_level, max_players)
               VALUES (?, ?, 'soccer', ?, ?, ?, 'All levels', 10)""",
            (host, title, place, to_db(now + start), to_db(now + end))).lastrowid
        db.execute("INSERT INTO rsvps (event_id, user_id, created_at) VALUES (?, ?, ?)", (game, host, to_db(now)))
        db.commit()


def test_the_live_window(accounts, client, app):
    accounts.signup(email="host@uw.edu", sports=("soccer",))
    host = user_id(app, "host@uw.edu")
    add_game(app, host, "On now", "Denny Field", timedelta(minutes=-30), timedelta(minutes=30))
    add_game(app, host, "Starting", "Husky Track", timedelta(minutes=55), timedelta(minutes=100))
    add_game(app, host, "Just ended", "The Quad", timedelta(minutes=-70), timedelta(minutes=-5))
    add_game(app, host, "Long over", "Red Square", timedelta(minutes=-120), timedelta(minutes=-20))
    add_game(app, host, "Too far off", "Recreation Field 1 (by the IMA)", timedelta(minutes=70), timedelta(minutes=120))
    play = client.get("/").data.decode()
    assert '"state": "live"' in play and '"label": "Live"' in play and '"Denny Field"' in play
    assert '"Husky Track"' in play and ('"label": "in 55 min"' in play or '"label": "in 54 min"' in play)
    assert '"The Quad"' in play and '"label": "Ended"' in play
    assert '"Red Square"' not in play and '"Recreation Field 1 (by the IMA)"' not in play
