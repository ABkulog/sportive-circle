"""Search: clubs and people in one box (the 🔍 in the top bar). Clubs are like accounts you follow: this is
how you find one."""
from flask import Blueprint, g, render_template, request

from .auth import login_required
from .constants import SPORTS
from .db import get_db
from .social import MIN_SEARCH_LENGTH, search_people
from .textutil import fold

bp = Blueprint("search", __name__)


def search_clubs(q, limit=20):
    """Verified clubs whose name, description or sport matches every word (accents and capitals ignored)."""
    words = fold(q).split()[:5]
    if len(q) < MIN_SEARCH_LENGTH or not words:
        return []
    where, params = ["c.status = 'approved'"], {"me": g.user["id"], "limit": limit}
    for n, word in enumerate(words):
        params[f"w{n}"] = "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sports = [key for key, name in SPORTS.items() if word in fold(name)]
        by_sport = f" OR c.sport IN ({', '.join(repr(s) for s in sports)})" if sports else ""
        where.append(f"(fold(c.name || ' ' || c.description) LIKE :w{n} ESCAPE '\\'{by_sport})")
    return get_db().execute(
        f"""SELECT c.id, c.name, c.sport, c.logo_updated, c.description,
                   (SELECT COUNT(*) FROM club_members m WHERE m.club_id = c.id AND m.role IN ('member', 'officer'))
                       AS member_count,
                   (SELECT m.role FROM club_members m WHERE m.club_id = c.id AND m.user_id = :me) AS my_role
            FROM clubs c WHERE {' AND '.join(where)}
            ORDER BY fold(c.name) LIKE :w0 DESC, member_count DESC, fold(c.name) LIMIT :limit""", params).fetchall()


@bp.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()[:100]
    return render_template("search.html", q=q, clubs=search_clubs(q) if q else [],
                           people=search_people(g.user["id"], q, limit=20) if q else [],
                           too_short=bool(q) and len(q) < MIN_SEARCH_LENGTH)
