"""Date/time helpers.

All times are Seattle local time, stored in the database as "YYYY-MM-DD HH:MM"
strings (they sort correctly as text, so SQL can compare them directly).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SEATTLE = ZoneInfo("America/Los_Angeles")
DB_FORMAT = "%Y-%m-%d %H:%M"
FORM_FORMAT = "%Y-%m-%dT%H:%M"  # what <input type="datetime-local"> sends


def now_local():
    return datetime.now(SEATTLE).replace(tzinfo=None, second=0, microsecond=0)


def to_db(dt):
    return dt.strftime(DB_FORMAT)


def from_db(value):
    return datetime.strptime(value, DB_FORMAT)


def parse_form(value):
    return datetime.strptime(value.strip(), FORM_FORMAT)


def exists_in_seattle(dt):
    """False for clock times skipped when daylight saving starts (2:00-2:59 AM on the second Sunday of
    March): no calendar app or reminder can place them."""
    there_and_back = dt.replace(tzinfo=SEATTLE).astimezone(timezone.utc).astimezone(SEATTLE)
    return there_and_back.replace(tzinfo=None) == dt


def from_sqlite_utc(value):
    """A column filled in by SQLite's datetime('now') (UTC, "YYYY-MM-DD HH:MM:SS") -> Seattle local time,
    so it can be compared with everything else in the app."""
    utc = datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return utc.astimezone(SEATTLE).replace(tzinfo=None)


def to_form(value):
    """DB string -> value for a datetime-local input."""
    return from_db(value).strftime(FORM_FORMAT)


def _clock(dt):
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def fmt_when(value):
    """'Sat Sep 27 · 5:30 PM' (adds the year when it isn't this year: 'Fri Jan 8, 2027 · ...')"""
    dt = from_db(value)
    year = f", {dt.year}" if dt.year != now_local().year else ""
    return f"{dt.strftime('%a %b')} {dt.day}{year} · {_clock(dt)}"


def fmt_clock(value):
    return _clock(from_db(value))


def fmt_relative(value):
    """'in 25 min', 'in 3 hr', 'tomorrow', 'in 4 days', 'happening now'."""
    dt = from_db(value)
    now = now_local()
    minutes = int((dt - now).total_seconds() // 60)
    if minutes <= 0:
        return "happening now"
    if minutes < 60:
        return f"in {minutes} min"
    if minutes < 3 * 60:  # "in 1 hr" for 1:55 away sends people out an hour late; show the minutes too
        hours, mins = divmod(round(minutes / 5) * 5, 60)
        return f"in {hours} hr" + (f" {mins} min" if mins else "")
    if minutes < 12 * 60:
        return f"in {round(minutes / 60)} hr"
    days = (dt.date() - now.date()).days
    if days == 0:
        return "later today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def fmt_ago(value):
    """When something happened: 'Just now', '12 min ago', '3 hr ago', 'Yesterday, 4:12 PM', 'Mon, 4:12 PM',
    'Sep 21' (with the year if it's not this year). (fmt_relative is for things still to come.)"""
    dt = from_db(value[:16])  # some rows (made by SQLite) also have seconds
    now = now_local()
    minutes = int((now - dt).total_seconds() // 60)
    if minutes < 1:
        return "Just now"
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 12 * 60 and dt.date() == now.date():
        return f"{minutes // 60} hr ago"
    days = (now.date() - dt.date()).days
    clock = dt.strftime("%I:%M %p").lstrip("0")
    if days == 0:
        return f"Today, {clock}"
    if days == 1:
        return f"Yesterday, {clock}"
    if days < 7:
        return f"{dt.strftime('%a')}, {clock}"
    return f"{dt.strftime('%b')} {dt.day}" + (f", {dt.year}" if dt.year != now.year else "")


def fmt_full(value):
    """'Monday, Sep 21, 4:12 PM' (for a hover / long-press title)."""
    dt = from_db(value[:16])
    return f"{dt.strftime('%A, %b')} {dt.day}, {dt.strftime('%I:%M %p').lstrip('0')}"


def same_day(a, b):
    return from_db(a).date() == from_db(b).date()
