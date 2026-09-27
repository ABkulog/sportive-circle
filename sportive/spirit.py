"""Husky spirit: greetings, badges and the Top Dawgs leaderboard. Go Dawgs! 🐺"""
import random
from datetime import datetime, time

from .db import get_db
from .timeutil import from_db, now_local, to_db

SPIRIT_LINES = [
    "Go Dawgs! 🐺",
    "Purple reign, all day. 💜",
    "Rain or shine, Dawgs play. 🌧️",
    "Bow down to Washington. Then go play. 💛",
    "The pack is waiting. 🐾",
    "Woof woof. Let's get a game going. 🐺",
]

# key: (emoji, name, how to earn it). Order = display order.
BADGES = {
    "first_game": ("🐾", "First Game", "Play your first game"),
    "regular": ("🔥", "Regular", "Play 10 games"),
    "pack_leader": ("🐺", "Pack Leader", "Host 5 games"),
    "rain_or_shine": ("🌧️", "Rain or Shine", "Play during Seattle's rainy season (Oct–Mar)"),
    "early_dawg": ("🌅", "Early Dawg", "Play a game that starts before 8 AM"),
    "night_dawg": ("🌙", "Night Dawg", "Play a game that starts at 9 PM or later"),
    "all_rounder": ("🎯", "All-Rounder", "Play 3 different sports"),
    "explorer": ("🧭", "Campus Explorer", "Play at 5 different places"),
}


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


def played_games(user_id):
    """Finished, non-cancelled games this person was part of (as a player or the host)."""
    return get_db().execute(
        """SELECT e.* FROM events e JOIN rsvps r ON r.event_id = e.id
           WHERE r.user_id = ? AND e.cancelled = 0 AND e.ends_at < ?""",
        (user_id, to_db(now_local())),
    ).fetchall()


def earned_badges(user_id):
    """Set of badge keys this person has earned."""
    games = played_games(user_id)
    starts = [from_db(g["starts_at"]) for g in games]
    hosted = sum(1 for g in games if g["host_id"] == user_id)
    earned = set()
    if games:
        earned.add("first_game")
    if len(games) >= 10:
        earned.add("regular")
    if hosted >= 5:
        earned.add("pack_leader")
    if any(s.month in (10, 11, 12, 1, 2, 3) for s in starts):
        earned.add("rain_or_shine")
    if any(s.hour < 8 for s in starts):
        earned.add("early_dawg")
    if any(s.hour >= 21 for s in starts):
        earned.add("night_dawg")
    if len({g["sport"] for g in games}) >= 3:
        earned.add("all_rounder")
    if len({g["location"] for g in games}) >= 5:
        earned.add("explorer")
    return earned


def top_dawgs(limit=3, now=None):
    """Who played the most games this calendar month."""
    now = now or now_local()
    month_start = datetime.combine(now.date().replace(day=1), time())
    return get_db().execute(
        """SELECT u.id, u.full_name, u.avatar_updated, COUNT(*) AS games
           FROM rsvps r JOIN events e ON e.id = r.event_id JOIN users u ON u.id = r.user_id
           WHERE e.cancelled = 0 AND e.starts_at >= ? AND e.ends_at < ? AND u.verified = 1
           GROUP BY u.id ORDER BY games DESC, u.full_name LIMIT ?""",
        (to_db(month_start), to_db(now), limit),
    ).fetchall()
