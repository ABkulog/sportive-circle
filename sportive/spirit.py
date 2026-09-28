"""The Home greeting and the Top Dawgs leaderboard. (Badges live in badges.py.)"""
from datetime import datetime, time

from .db import get_db
from .timeutil import now_local, to_db

def greeting(first_name):
    """Plain and friendly. (Testers found "Late night, Maya!" confusing and the slogans corny.)"""
    return f"Hey, {first_name}"


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
