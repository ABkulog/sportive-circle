"""Husky spirit: greetings and the Top Dawgs leaderboard. Go Dawgs! 🐺 (Badges live in badges.py.)"""
import random
from datetime import datetime, time

from .db import get_db
from .timeutil import now_local, to_db

SPIRIT_LINES = [
    "Go Dawgs! 🐺",
    "Purple reign, all day. 💜",
    "Rain or shine, Dawgs play. 🌧️",
    "Bow down to Washington. Then go play. 💛",
    "The pack is waiting. 🐾",
    "Woof woof. Let's get a game going. 🐺",
]

def greeting(first_name, now=None):
    """'Evening, Maya!' plus a random spirit line."""
    hour = (now or now_local()).hour
    if 5 <= hour < 12:
        part = "Morning"
    elif 12 <= hour < 17:
        part = "Afternoon"
    elif 17 <= hour < 22:
        part = "Evening"
    else:
        part = "Late night"
    return f"{part}, {first_name}!", random.choice(SPIRIT_LINES)


def top_dawgs(limit=3, now=None):
    """Who played the most games this calendar month."""
    now = now or now_local()
    month_start = datetime.combine(now.date().replace(day=1), time())
    return get_db().execute(
        """SELECT u.id, u.full_name, u.avatar_updated, COUNT(*) AS games
           FROM rsvps r JOIN events e ON e.id = r.event_id JOIN users u ON u.id = r.user_id
           WHERE e.cancelled = 0 AND e.starts_at >= ? AND e.ends_at < ? AND u.verified = 1 AND u.suspended = 0
           GROUP BY u.id ORDER BY games DESC, u.full_name LIMIT ?""",
        (to_db(month_start), to_db(now), limit),
    ).fetchall()
