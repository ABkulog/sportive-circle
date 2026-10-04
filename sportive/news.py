"""Husky news in the feed: headlines, scores and results from every UW Division I team, via GoHuskies.com's
public RSS feeds (half of campus doesn't know whether UW won today; this is a reason to open the app daily).

We only show headlines, dates and links; tapping a story opens it on GoHuskies.com. The feeds are downloaded
in the background at most every 30 minutes, so a page never waits on GoHuskies (and keeps the last stories if
it's down). Tests never download anything (app.testing).
"""
import logging
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.request import Request, urlopen

from flask import current_app

from .timeutil import to_db

log = logging.getLogger(__name__)

FEED_URL = "https://gohuskies.com/api/v2/rss/xml?path={code}"
CACHE_SECONDS = 30 * 60
TIMEOUT_SECONDS = 6

# GoHuskies feed code -> (team name as GoHuskies writes it, emoji, our sport key or None)
TEAMS = {
    "football": ("Football", "🏈", "football"),
    "mbball": ("Men's Basketball", "🏀", "basketball"),
    "wbball": ("Women's Basketball", "🏀", "basketball"),
    "msoc": ("Men's Soccer", "⚽", "soccer"),
    "wsoc": ("Women's Soccer", "⚽", "soccer"),
    "wvball": ("Volleyball", "🏐", "volleyball"),
    "wbvball": ("Beach Volleyball", "🏐", "volleyball"),
    "mrow": ("Men's Rowing", "🚣", "rowing"),
    "wrow": ("Women's Rowing", "🚣", "rowing"),
    "mten": ("Men's Tennis", "🎾", "tennis"),
    "wten": ("Women's Tennis", "🎾", "tennis"),
    "cross": ("Cross Country", "🏃", "running"),
    "track": ("Track & Field", "🏃", "running"),
    "softball": ("Softball", "🥎", None),
    "bsb": ("Baseball", "⚾", None),
    "wgym": ("Gymnastics", "🤸", None),
    "mgolf": ("Men's Golf", "⛳", None),
    "wgolf": ("Women's Golf", "⛳", None),
}
TEAM_BY_NAME = {name: code for code, (name, _, _) in TEAMS.items()}
GENERAL_MIN_TEAMS = 4  # a story tagged with this many teams is department-wide news

_cache = {"fetched_at": 0.0, "stories": [], "busy": False}
_lock = threading.Lock()


def _parse_date(text):
    # e.g. "Sat, 26 Sep 2026 23:34:00 PST" (always Pacific time)
    try:
        return datetime.strptime(text.strip()[:25], "%a, %d %b %Y %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def parse_feed(xml_text):
    """Stories from one RSS document: dicts with title, link, published, teams."""
    stories = []
    for item in ET.fromstring(xml_text).findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link.startswith("https://gohuskies.com/"):
            continue  # only real GoHuskies links
        names = [part.strip() for part in (item.findtext("category") or "").split(",") if part.strip()]
        teams = [TEAM_BY_NAME[name] for name in names if name in TEAM_BY_NAME]
        stories.append({"title": title, "link": link, "published": _parse_date(item.findtext("pubDate") or ""),
                        "teams": teams, "general": len(teams) >= GENERAL_MIN_TEAMS or not teams})
    return stories


def _download(code):
    request_ = Request(FEED_URL.format(code=code), headers={"User-Agent": "SportiveCircle/1.0 (UW student project)"})
    with urlopen(request_, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_all():
    """Download every team's feed at once, merge, and drop duplicates."""
    def one(code):
        try:
            return parse_feed(_download(code))
        except Exception as error:  # a single broken feed shouldn't break the page
            log.warning("GoHuskies feed %s failed: %s", code, error)
            return []

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, TEAMS))
    merged = {}
    for stories in results:
        for story in stories:
            merged.setdefault(story["link"], story)
    return sorted(merged.values(), key=lambda s: s["published"] or datetime.min, reverse=True)


def _refresh():
    try:
        fresh = fetch_all()
        if fresh:
            _cache["stories"] = fresh
    finally:
        _cache["fetched_at"] = time.time()
        _cache["busy"] = False


def stories():
    """The stories downloaded so far, starting a background refresh when they're older than 30 minutes."""
    if not current_app.testing:
        with _lock:
            if time.time() - _cache["fetched_at"] > CACHE_SECONDS and not _cache["busy"]:
                _cache["busy"] = True
                threading.Thread(target=_refresh, daemon=True).start()
    return _cache["stories"]


def story_sports(story):
    return {TEAMS[code][2] for code in story["teams"] if TEAMS[code][2]}


def feed_news(sports, before, limit, channel=False):
    """Feed items for stories about these sports (department-wide news only in the full feed), newest first."""
    wanted = set(sports)
    items = []
    for story in stories():
        if not story["published"]:
            continue
        at = to_db(story["published"])
        about = story_sports(story) & wanted
        if at > before or not (about or (story["general"] and not channel)):
            continue
        code = next((c for c in story["teams"] if TEAMS[c][2] in wanted), story["teams"][0] if story["teams"] else None)
        items.append({"kind": "news", "at": at, "story": story,
                      "team": TEAMS[code][0] if code else "Husky Athletics", "emoji": TEAMS[code][1] if code else "🐾",
                      "sport": TEAMS[code][2] if code else None})
        if len(items) >= limit:
            break
    return items
