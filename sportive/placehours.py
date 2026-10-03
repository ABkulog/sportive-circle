"""Opening hours: a game can't be posted at a place while it's closed (the hours themselves: PLACE_HOURS in
constants.py, with where they come from). Used when a game is posted, edited, posted from Need players, and for
every week of a weekly club practice."""
from datetime import datetime, time

from flask import current_app

from .constants import PLACE_HOURS

DAY_NAMES = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]


# How each place is named in a sentence, and whether it's one place or several ("the courts close").
NAMES = {
    "IMA (Intramural Activities Building)": ("The IMA", False),
    "IMA Archery Room": ("The IMA Archery Room", False),
    "IMA Mat Rooms (martial arts)": ("The IMA Mat Rooms", True),
    "IMA Squash & Racquetball Courts": ("The IMA squash and racquetball courts", True),
    "IMA Pool": ("The IMA Pool", False),
    "IMA South Tennis Courts": ("The IMA South Tennis Courts", True),
    "Fitness Center West (under Elm Hall)": ("Fitness Center West", False),
    "UW Golf Driving Range": ("The UW Golf Driving Range", False),
    "Waterfront Activities Center (WAC)": ("The WAC", False),
    "Green Lake Park pickleball courts": ("The Green Lake pickleball courts", True),
}


def _name(location):
    return NAMES.get(location, (location.split(" (")[0], False))


def _clock(text):
    hour, minute = map(int, text.split(":"))
    return datetime(2000, 1, 1, hour, minute).strftime("%I:%M %p").lstrip("0")


def hours_on(location, day):
    """(opens, closes) as "HH:MM" on this date, None if it's closed all day, or "any" if there's no limit."""
    stamp = day.strftime("%m-%d")
    for (first, last), week in PLACE_HOURS.get(location, []):
        if first <= stamp <= last:
            return week.get(day.weekday(), "any")
    return "any"


def closed_message(location, starts, ends):
    """None if the place is open for the whole game, else what to tell the host (in plain words)."""
    if not current_app.config.get("CHECK_PLACE_HOURS", True):
        return None
    hours = hours_on(location, starts.date())
    if hours == "any":
        return None
    (name, several), day = _name(location), DAY_NAMES[starts.weekday()]
    is_, closes_ = ("are", "close") if several else ("is", "closes")
    if hours is None:
        seasons = [week for (first, last), week in PLACE_HOURS[location]
                   if first <= starts.strftime("%m-%d") <= last]
        if seasons and all(seasons[0].get(n) is None for n in range(7)):
            return f"{name} {is_} closed for the season on {starts.strftime('%b')} {starts.day}. Pick another place or date."
        return f"{name} {is_} closed on {day}. Pick another day or place."
    opens, closes = (time.fromisoformat(value) for value in hours)
    close_at = datetime.combine(starts.date(), closes, tzinfo=starts.tzinfo)
    if starts.time() >= opens and ends <= close_at:
        return None
    if opens == time(0, 0):  # only a closing time (lights off)
        return f"{name} {closes_} at {_clock(hours[1])} on {day}, so the game has to end by then."
    return (f"{name} {is_} open {_clock(hours[0])} – {_clock(hours[1])} on {day}, so the game has to start and end "
            "inside those hours.")


def hours_for_page():
    """Every place's hours for the game form, so it can say "Open 9:00 AM – 8:30 PM on Saturdays" as soon as a
    place and date are picked: {place: [[first "MM-DD", last "MM-DD", {weekday: [opens, closes] or None}], ...]}."""
    if not current_app.config.get("CHECK_PLACE_HOURS", True):
        return {}
    return {place: [[first, last, {str(day): list(hours) if hours else None for day, hours in week.items()}]
                    for (first, last), week in seasons] for place, seasons in PLACE_HOURS.items()}
