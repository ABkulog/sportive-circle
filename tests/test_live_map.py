"""Play's live map (like Snap Map): starting later today, going on, or ended in the last 10 minutes."""
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
    add_game(app, host, "Too far off", "Recreation Field 1 (by the IMA)", timedelta(hours=25), timedelta(hours=26))
    play = client.get("/").data.decode()
    assert '"state": "live"' in play and '"label": "Live"' in play and '"Denny Field"' in play
    assert '"Husky Track"' in play and ('"label": "in 55 min"' in play or '"label": "in 54 min"' in play)
    assert '"The Quad"' in play and '"label": "Ended"' in play
    pins = play.split('id="play-pins">')[1].split("</script>")[0]  # the game bubbles (every place has a 📍 too)
    assert '"Red Square"' not in pins and '"Recreation Field 1 (by the IMA)"' not in pins


def test_the_map_shows_the_rest_of_today_and_leads_only_when_busy(accounts, client, app):
    """FR-PLAY-30: the map showed only games starting within the hour, so it said "Nothing on right now" almost
    all day. It now shows the rest of today (a game later on says its time), and while nothing's on today the
    Upcoming games list comes first and the map sits below it."""
    from sportive.events import live_status, live_window_end
    now = now_local()
    assert live_window_end(now) >= now + timedelta(hours=1)
    later = now.replace(hour=23, minute=0, second=0, microsecond=0)
    if later - now > timedelta(hours=1):
        game = {"starts_at": to_db(later), "ends_at": to_db(later + timedelta(minutes=30))}
        assert live_status(game, now) == ("soon", "11:00 PM")
    accounts.signup(email="host@uw.edu", sports=("soccer",))
    play = client.get("/").data.decode()
    assert play.index('id="games-title"') < play.index('id="live-map"')       # nothing today: list first
    assert "games today show up here" in play
    add_game(app, user_id(app, "host@uw.edu"), "On now", "Denny Field", timedelta(minutes=-10), timedelta(minutes=50))
    play = client.get("/").data.decode()
    assert play.index('id="live-map"') < play.index('id="games-title"')       # something on: the map leads


def test_golf_range_pin_is_on_the_range_and_the_archery_lawn_is_a_spot(accounts, client):
    """FR-PLAY-35: the golf range's pin sat on NE 45th St; it's now on the range itself (west of Ravenna Creek,
    south of 45th, north of NE Clark Rd). The lawn maps call "Archery Range" (by the Penthouse Theatre, north of
    Denny Field) is a spot for lawn games; archery itself stays in the IMA's archery room."""
    from sportive.constants import ARCHERY_LAWN, DENNY, GOLF_RANGE, LOCATION_COORDS, REC_FIELD_3, SPORT_LOCATIONS
    lat, lng = LOCATION_COORDS[GOLF_RANGE]
    assert 47.6585 < lat < 47.6605 and lng < LOCATION_COORDS[REC_FIELD_3][1]       # south of 45th, west of the fields
    lawn = LOCATION_COORDS[ARCHERY_LAWN]
    assert lawn[0] > LOCATION_COORDS[DENNY][0] and lawn[1] < LOCATION_COORDS[DENNY][1]  # north-west of Denny Field
    assert ARCHERY_LAWN in SPORT_LOCATIONS["ultimate"] and ARCHERY_LAWN not in SPORT_LOCATIONS["archery"]
    accounts.signup(email="maya@uw.edu", sports=("ultimate",))
    assert "Archery Range lawn" in client.get("/").data.decode()


def test_sand_volleyball_and_track_pins_sit_on_the_places(accounts, client):
    """FR-PLAY-36: the sand volleyball pin was east of Rec Field 1; the courts are right behind (west of) the IMA
    North Tennis Courts. The track's pin was on its east end; it's now in the middle of the oval."""
    from sportive.constants import IMA_NORTH_COURTS, LOCATION_COORDS, REC_FIELD_2, SAND_COURTS, TRACK
    sand, north = LOCATION_COORDS[SAND_COURTS], LOCATION_COORDS[IMA_NORTH_COURTS]
    assert sand[1] < north[1] and abs(sand[0] - north[0]) < 0.0006      # just west of the north courts
    track, field2 = LOCATION_COORDS[TRACK], LOCATION_COORDS[REC_FIELD_2]
    assert -122.2988 < track[1] < -122.2976 and track[0] < field2[0] + 0.0012
