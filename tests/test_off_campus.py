"""Off campus: 📍 Where exactly? A dropped pin, a pasted Google / Apple Maps link or an address, so the game page
can show the map and open Google Maps or Apple Maps, and Play's map has a pin for it."""
from datetime import timedelta

from sportive.db import get_db
from sportive.events import read_spot
from test_feed import form_time, post


def game(**fields):
    return {"title": "Hike", "sport": "hiking", "location": "Off campus (see note)", "players": "6", "note": "",
            "starts_at": form_time(timedelta(days=1)), "ends_at": form_time(timedelta(days=1, hours=3)), **fields}


def test_links_pins_and_addresses_are_read():
    assert read_spot({"pin": "47.6553,-122.3035"})[:2] == (47.6553, -122.3035)
    google = "https://www.google.com/maps/place/Green+Lake/@47.6806,-122.3290,15z/data=!3d47.6806!4d-122.329"
    assert read_spot({"place_address": google})[:2] == (47.6806, -122.329)
    assert read_spot({"place_address": "https://maps.apple.com/?ll=47.52,-121.77&q=Rattlesnake"})[:2] == (47.52, -121.77)
    short = read_spot({"place_address": "https://maps.app.goo.gl/AbC123"})
    assert short == (None, None, "https://maps.app.goo.gl/AbC123", None)            # kept, opened as it is
    assert read_spot({"place_address": "Green Lake Park, Seattle"}) == (None, None, "Green Lake Park, Seattle", None)
    assert "Google Maps or Apple Maps" in read_spot({"place_address": "https://evil.example/x"})[3]
    assert read_spot({"pin": "999,5"})[3] and read_spot({"pin": "nope"})[3]


def test_a_pinned_off_campus_game_has_maps_and_a_play_pin(accounts, client, app):
    accounts.signup(sports=("hiking",))
    response = client.post("/events/new", data=game(pin="47.5246,-121.7682", place_address="Rattlesnake Ledge lot",
                                                     starts_at=form_time(timedelta(minutes=30)),
                                                     ends_at=form_time(timedelta(hours=3))))
    page = client.get(response.headers["Location"]).data.decode()
    assert "destination=47.5246,-121.7682" in page and "maps.apple.com/?daddr=47.5246,-121.7682" in page
    assert 'id="event-map"' in page and "Rattlesnake Ledge lot" in page
    play = client.get("/?scope=all").data.decode()
    assert '"lat": 47.5246' in play                                       # starting soon: its own bubble on Play
    form = client.get(response.headers["Location"] + "/edit").data.decode()
    assert 'value="47.5246,-121.7682"' in form and 'data-spot' in form                # kept when editing


def test_an_address_only_off_campus_game_opens_both_maps_apps(accounts, client):
    accounts.signup(sports=("hiking",))
    response = client.post("/events/new", data=game(place_address="Green Lake Park, Seattle"))
    page = client.get(response.headers["Location"]).data.decode()
    assert "google.com/maps/dir/?api=1&amp;destination=Green%20Lake%20Park%2C%20Seattle" in page
    assert "maps.apple.com/?daddr=Green%20Lake%20Park%2C%20Seattle" in page and 'id="event-map"' not in page


def test_plans_and_need_players_take_a_pin_too(accounts, client, app):
    accounts.signup(sports=("running",))
    post(client, sport="running", body="Long run", plan="1", starts_at=form_time(timedelta(days=1)), duration="60",
         location="Off campus (see note)", spots="3", pin="47.68,-122.33")
    with app.app_context():
        assert tuple(get_db().execute("SELECT place_lat, place_lng FROM events").fetchone()) == (47.68, -122.33)
    feed = client.get("/feed").data.decode()
    assert "data-drop-pin" in feed and "spot.js" in feed
    assert "data-drop-pin" in client.get("/need-players").data.decode()
