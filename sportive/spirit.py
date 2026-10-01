"""The Home greeting and the Top Dawgs leaderboard. (Badges live in badges.py.)"""
from datetime import datetime, time

from .db import get_db
from .timeutil import now_local, to_db

def greeting(first_name):
    """Plain and friendly. (Testers found "Late night, Maya!" confusing and the slogans corny.)"""
    return f"Hey, {first_name}"


TOP_DAWGS = 10  # spots on the Home leaderboard


def top_dawgs(limit=TOP_DAWGS, now=None, viewer=None):
    """Who played the most games this calendar month (the top 10). A game counts only if someone else played
    it too (posting games alone doesn't climb the board) and its club isn't on hold. People the viewer
    blocked (or who blocked them) aren't shown."""
    now = now or now_local()
    month_start = datetime.combine(now.date().replace(day=1), time())
    return get_db().execute(
        """SELECT u.id, u.full_name, u.avatar_updated, COUNT(*) AS games
           FROM rsvps r JOIN events e ON e.id = r.event_id JOIN users u ON u.id = r.user_id
           LEFT JOIN clubs cl ON cl.id = e.club_id
           WHERE e.cancelled = 0 AND e.starts_at >= :start AND e.ends_at < :now AND u.verified = 1 AND u.suspended = 0
             AND (e.club_id IS NULL OR COALESCE(cl.status, 'approved') = 'approved')
             AND EXISTS (SELECT 1 FROM rsvps o WHERE o.event_id = e.id AND o.user_id != r.user_id)
             AND u.id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = :viewer)
             AND u.id NOT IN (SELECT blocker_id FROM blocks WHERE blocked_id = :viewer)
           GROUP BY u.id ORDER BY games DESC, fold(u.full_name) LIMIT :limit""",
        {"start": to_db(month_start), "now": to_db(now), "limit": limit, "viewer": viewer or 0},
    ).fetchall()
