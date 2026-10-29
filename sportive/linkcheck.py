"""Hides club websites that are gone. Once a day (after the club sync), the site opens every club's website; one
that's missing (404, 410), broken (5xx) or doesn't answer two days in a row is left off the club's page until it
works again. Instagram isn't checked (it refuses robots, so every check would "fail"). A site that refuses robots
(401, 403, 405, 429) counts as working: a person can still open it."""
import logging
import urllib.error
import urllib.request

from .db import get_db
from .timeutil import now_local, to_db

log = logging.getLogger(__name__)
DEAD_AFTER = 2           # failed days in a row before a link is hidden
REFUSES_ROBOTS = (401, 403, 405, 406, 429)


def open_status(url):
    """The HTTP status a browser would get, or "no answer" (DNS, refused, timed out, bad certificate)."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SportiveCircle link check)"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return str(response.status)
    except urllib.error.HTTPError as error:
        return str(error.code)
    except Exception:
        return "no answer"


def works(status):
    return status.isdigit() and (int(status) < 400 or int(status) in REFUSES_ROBOTS)


def club_websites():
    """Every website a club page shows (its own site and its UW or HuskyLink page)."""
    rows = get_db().execute("SELECT contact_url, verification_url FROM clubs WHERE status = 'approved'").fetchall()
    return sorted({url for row in rows for url in row if url and url.startswith(("http://", "https://"))})


def check_club_websites(status_of=open_status):
    """Checks each club website once; returns the ones hidden now."""
    db, now, hidden = get_db(), to_db(now_local()), []
    for url in club_websites():
        status = status_of(url)
        if works(status):
            db.execute("DELETE FROM dead_links WHERE url = ?", (url,))
            continue
        db.execute("""INSERT INTO dead_links (url, failures, last_status, last_checked) VALUES (?, 1, ?, ?)
                      ON CONFLICT(url) DO UPDATE SET failures = failures + 1, last_status = excluded.last_status,
                                                     last_checked = excluded.last_checked""", (url, status, now))
        if db.execute("SELECT failures FROM dead_links WHERE url = ?", (url,)).fetchone()[0] >= DEAD_AFTER:
            hidden.append(url)
    db.commit()
    if hidden:
        log.info("Club links hidden (gone %d days in a row): %s", DEAD_AFTER, ", ".join(hidden))
    return hidden


def dead(urls):
    """The ones of these links that are hidden right now."""
    urls = [url for url in urls if url]
    if not urls:
        return set()
    rows = get_db().execute(f"SELECT url FROM dead_links WHERE failures >= ? AND url IN ({', '.join('?' * len(urls))})",
                            (DEAD_AFTER, *urls)).fetchall()
    return {row[0] for row in rows}
