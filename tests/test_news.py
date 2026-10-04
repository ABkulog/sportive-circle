"""Husky news (GoHuskies.com headlines) in the feed. Nothing is downloaded in tests."""
from datetime import timedelta

import pytest

from sportive import news
from sportive.timeutil import now_local

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Huskies top USC 31-24</title><link>https://gohuskies.com/news/2026/10/03/football-win</link>
  <pubDate>Sat, 03 Oct 2026 22:10:00 PDT</pubDate><category>Football</category></item>
<item><title>Not ours</title><link>https://evil.example/story</link><pubDate>Sat, 03 Oct 2026 22:10:00 PDT</pubDate></item>
</channel></rss>"""


@pytest.fixture
def stories():
    saved = dict(news._cache)
    yield news._cache
    news._cache.clear()
    news._cache.update(saved)


def story(title, team, hours_ago):
    return {"title": title, "link": f"https://gohuskies.com/news/{team}", "teams": [team], "general": False,
            "published": now_local().replace(second=0, microsecond=0) - timedelta(hours=hours_ago)}


def test_only_real_gohuskies_links_are_read():
    parsed = news.parse_feed(RSS)
    assert [s["title"] for s in parsed] == ["Huskies top USC 31-24"] and parsed[0]["teams"] == ["football"]


def test_scores_for_my_sports_show_in_the_feed_and_their_channel(accounts, client, stories):
    stories["stories"] = [story("Huskies top USC 31-24", "football", 2), story("Women's soccer wins 2-0", "wsoc", 3)]
    accounts.signup(sports=("football",))
    feed = client.get("/feed").data.decode()
    assert "Huskies top USC 31-24" in feed and "Husky Football" in feed and "GoHuskies.com" in feed
    assert "Women&#39;s soccer wins" not in feed                                  # not my sport
    assert "Women&#39;s soccer wins 2-0" in client.get("/feed?sport=soccer").data.decode()
    assert 'href="https://gohuskies.com/news/football" target="_blank" rel="noopener"' in feed
