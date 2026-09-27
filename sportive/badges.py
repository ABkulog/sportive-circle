"""Husky badges: permanent ones, plus limited ones that retire forever (the OG flex).

Badges are saved the moment they're earned (with the date), so a badge never disappears
later, and retired badges can't be earned by anyone new.
"""
from collections import namedtuple
from datetime import date

from .db import get_db
from .ranks import FIRST_LEVEL_OF, user_ranks
from .timeutil import from_db, now_local, to_db

Badge = namedtuple("Badge", "key emoji name how until")  # until = last day it can be earned (None = forever)

FOUNDING_DEADLINE = date(2026, 12, 31)
FIRST_SEASON = (2026, "Autumn")  # the app launched in Autumn Quarter 2026

# UW-style quarters (approximate dates): (name, emoji, first month/day, last month/day)
SEASONS = [
    ("Winter", "❄️", (1, 1), (3, 21)),
    ("Spring", "🌸", (3, 22), (6, 14)),
    ("Summer", "☀️", (6, 15), (9, 20)),
    ("Autumn", "🍂", (9, 21), (12, 31)),
]

PERMANENT = [
    Badge("first_game", "🐾", "First Game", "Play your first game", None),
    Badge("regular", "🔥", "Regular", "Play 10 games", None),
    Badge("veteran", "🎖️", "Veteran", "Play 50 games", None),
    Badge("pack_leader", "🐺", "Pack Leader", "Host 5 games", None),
    Badge("good_sport", "🤝", "Good Sport", "Get 10 props from teammates", None),
    Badge("hype_dawg", "📣", "Hype Dawg", "Give 10 props to teammates", None),
    Badge("level_up", "⬆️", "Level Up", "Reach Intermediate in any sport", None),
    Badge("competitor", "💎", "Competitor", "Reach Competitive in any sport", None),
    Badge("legend", "👑", "Legend", "Reach Legend in any sport", None),
    Badge("multi_threat", "⭐", "Multi-Threat", "Reach Intermediate in 2 different sports", None),
    Badge("rain_or_shine", "🌧️", "Rain or Shine", "Play during Seattle's rainy season (Oct–Mar)", None),
    Badge("early_dawg", "🌅", "Early Dawg", "Play a game that starts between 5 and 8 AM", None),
    Badge("night_dawg", "🌙", "Night Dawg", "Play a game that starts at 9 PM or later (after midnight counts!)", None),
    Badge("all_rounder", "🎯", "All-Rounder", "Play 3 different sports", None),
    Badge("explorer", "🧭", "Campus Explorer", "Play at 5 different places", None),
]


def season_of(day):
    for name, _, (m1, d1), (m2, d2) in SEASONS:
        if (m1, d1) <= (day.month, day.day) <= (m2, d2):
            return day.year, name
    raise ValueError(day)


def season_badge(year, name):
    emoji, _, (m2, d2) = next((e, s, end) for n, e, s, end in SEASONS if n == name)
    return Badge(f"season-{year}-{name.lower()}", emoji, f"{name} {year}",
                 f"Play a game during {name} Quarter {year}", date(year, m2, d2))


def season_badges(today=None):
    """One limited badge per quarter, from launch until now."""
    today = today or now_local().date()
    order = [name for name, *_ in SEASONS]
    year, name = FIRST_SEASON
    badges = []
    while (year, order.index(name)) <= (season_of(today)[0], order.index(season_of(today)[1])):
        badges.append(season_badge(year, name))
        index = order.index(name) + 1
        year, name = (year + 1, order[0]) if index == len(order) else (year, order[index])
    return badges


def catalog(today=None):
    """Every badge that exists so far: limited ones first (newest first), then permanent."""
    limited = [Badge("founding_dawg", "✨", "Founding Dawg", "Join Sportive Circle before 2027", FOUNDING_DEADLINE)]
    return list(reversed(season_badges(today))) + limited + PERMANENT


def is_retired(badge, today=None):
    return badge.until is not None and (today or now_local().date()) > badge.until


def eligible(user_id):
    """Keys of every badge this person qualifies for right now."""
    db = get_db()
    now = now_local()
    user = db.execute("SELECT created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    games = db.execute(
        """SELECT e.* FROM events e JOIN rsvps r ON r.event_id = e.id
           WHERE r.user_id = ? AND e.cancelled = 0 AND e.ends_at < ?""",
        (user_id, to_db(now)),
    ).fetchall()
    starts = [from_db(game["starts_at"]) for game in games]
    hosted = sum(1 for game in games if game["host_id"] == user_id)
    props_in = db.execute("SELECT COUNT(*) FROM props WHERE receiver_id = ?", (user_id,)).fetchone()[0]
    props_out = db.execute("SELECT COUNT(*) FROM props WHERE giver_id = ?", (user_id,)).fetchone()[0]
    levels = [rank.level for rank in user_ranks(user_id).values()]

    keys = set()
    checks = {
        "first_game": len(games) >= 1,
        "regular": len(games) >= 10,
        "veteran": len(games) >= 50,
        "pack_leader": hosted >= 5,
        "good_sport": props_in >= 10,
        "hype_dawg": props_out >= 10,
        "level_up": any(level >= FIRST_LEVEL_OF["Intermediate"] for level in levels),
        "competitor": any(level >= FIRST_LEVEL_OF["Competitive"] for level in levels),
        "legend": any(level >= FIRST_LEVEL_OF["Legend"] for level in levels),
        "multi_threat": sum(level >= FIRST_LEVEL_OF["Intermediate"] for level in levels) >= 2,
        "rain_or_shine": any(s.month in (10, 11, 12, 1, 2, 3) for s in starts),
        "early_dawg": any(5 <= s.hour < 8 for s in starts),
        "night_dawg": any(s.hour >= 21 or s.hour < 5 for s in starts),
        "all_rounder": len({game["sport"] for game in games}) >= 3,
        "explorer": len({game["location"] for game in games}) >= 5,
        # created_at is stored by SQLite in UTC; the date is close enough for a deadline.
        "founding_dawg": user is not None and date.fromisoformat(user["created_at"][:10]) <= FOUNDING_DEADLINE,
    }
    keys.update(key for key, earned in checks.items() if earned)
    # Season badges: played a game during that quarter (only quarters since launch count).
    valid_seasons = {badge.key for badge in season_badges()}
    for start in starts:
        key = season_badge(*season_of(start.date())).key
        if key in valid_seasons:
            keys.add(key)
    return keys


def sync_badges(user_id):
    """Save any newly earned badges. Returns the Badge objects that were just unlocked."""
    db = get_db()
    have = {row["badge"] for row in db.execute("SELECT badge FROM user_badges WHERE user_id = ?", (user_id,))}
    by_key = {badge.key: badge for badge in catalog()}
    new = [by_key[key] for key in eligible(user_id) - have if key in by_key]
    today = to_db(now_local())
    db.executemany("INSERT OR IGNORE INTO user_badges (user_id, badge, earned_at) VALUES (?, ?, ?)",
                   [(user_id, badge.key, today) for badge in new])
    db.commit()
    return new


def earned_badges(user_id):
    """{badge key: date earned} for badges this person has."""
    return {row["badge"]: from_db(row["earned_at"]).date() for row in get_db().execute(
        "SELECT badge, earned_at FROM user_badges WHERE user_id = ?", (user_id,))}


def rarity():
    """{badge key: percent of Huskies who have it}."""
    db = get_db()
    total = db.execute("SELECT COUNT(*) FROM users WHERE verified = 1").fetchone()[0] or 1
    return {row["badge"]: round(100 * row["n"] / total) for row in db.execute(
        "SELECT badge, COUNT(*) AS n FROM user_badges GROUP BY badge")}


SHOWCASE_SLOTS = 3


def showcase(user_id):
    """The (up to) 3 badges shown on a profile. Until someone picks, show their 3 rarest."""
    db = get_db()
    earned = earned_badges(user_id)
    by_key = {badge.key: badge for badge in catalog()}
    row = db.execute("SELECT showcase FROM users WHERE id = ?", (user_id,)).fetchone()
    if row and row["showcase"] is not None:
        keys = [key for key in row["showcase"].split(",") if key in earned and key in by_key]
    else:
        percent = rarity()
        keys = sorted(earned, key=lambda key: (percent.get(key, 100), key))
        keys = [key for key in keys if key in by_key]
    return [by_key[key] for key in keys[:SHOWCASE_SLOTS]]


def set_showcase(user_id, keys):
    """Save which badges to show. Returns an error message, or None when saved."""
    earned = earned_badges(user_id)
    keys = list(dict.fromkeys(keys))  # drop duplicates, keep order
    if len(keys) > SHOWCASE_SLOTS:
        return f"You can only show {SHOWCASE_SLOTS} badges. Pick your top {SHOWCASE_SLOTS}!"
    if any(key not in earned for key in keys):
        return "You can only show badges you've earned."
    db = get_db()
    db.execute("UPDATE users SET showcase = ? WHERE id = ?", (",".join(keys), user_id))
    db.commit()
    return None
