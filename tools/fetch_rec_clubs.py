"""Refresh sportive/data/uw_rec_clubs.json from UW Recreation's "Clubs Offered" page.

    .venv/bin/python tools/fetch_rec_clubs.py

Reads every Rec Club's name, description and links (website, Instagram, Facebook, X, Discord) and writes them,
with the app's sport for each, to the JSON file. Admins then add the new ones in Admin → Club requests → UW Rec
Clubs. A club UW adds later needs a line in SPORT_OF below (the script stops and says which).
"""
import html
import json
import os
import re
import sys
import urllib.request
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SOURCE = "https://www.washington.edu/ima/rec-clubs/club-offerings/"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sportive", "data", "uw_rec_clubs.json")

# UW's club name -> the app's sport (constants.SPORTS); "other" where the app has no such sport.
SPORT_OF = {
    "Men's Baseball": "baseball", "Men's Lacrosse": "lacrosse", "Men's Rugby": "rugby", "Men's Soccer": "soccer",
    "Men's Ultimate Frisbee": "ultimate", "Men's Volleyball": "volleyball", "Men's Water Polo": "water_polo",
    "Women's Ice Hockey": "ice_hockey", "Women's Lacrosse": "lacrosse", "Women's Rugby": "rugby",
    "Women's Soccer": "soccer", "Women's Ultimate Frisbee": "ultimate", "Women's Volleyball": "volleyball",
    "Women's Water Polo": "water_polo", "Badminton": "badminton", "Canoe Family": "rowing", "Climbing": "climbing",
    "Concrete Canoe": "rowing", "Cycling": "biking", "Equestrian": "equestrian", "Roundnet": "spikeball",
    "Running": "running", "Sailing": "sailing", "Skiing": "snow", "Squash": "squash", "Swimming": "swimming",
    "Table Tennis": "table_tennis", "Tennis": "tennis", "Triathlon": "triathlon", "Union Bay Rowing": "rowing",
    "Washington Yacht Club": "sailing", "Aikido": "other", "Archery": "archery", "Boxing": "boxing",
    "Brazilian Jiu-Jitsu": "bjj", "Judo": "judo", "Karate – Shotokan": "karate", "Kendo": "kendo",
    "Kung Fu / Tai Chi": "other", "Taekwondo": "taekwondo", "Wrestling": "wrestling", "Wushu": "other",
}
# Names that already say what they are; every other club is "UW <name> Club".
APP_NAME = {"Union Bay Rowing": "Union Bay Rowing Club", "Washington Yacht Club": "Washington Yacht Club",
            "Canoe Family": "UW Canoe Family", "Concrete Canoe": "UW Concrete Canoe Team",
            "Karate – Shotokan": "UW Shotokan Karate Club"}
# Links UW's page has wrong (another club's account): left out.
WRONG_LINKS = {"Men's Ultimate Frisbee": ("facebook",)}  # it points at the triathlon club's Facebook
TRACKING = ("fbclid", "mibextid", "hl", "ref_src", "fref", "_rdr", "s", "igsh", "utm_source", "utm_medium",
            "utm_campaign", "utm_term", "v")


def clean(url):
    """https, and without tracking bits (?fbclid=..., ?hl=en): the link people should see."""
    url = html.unescape(url).strip()
    url = "https:" + url if url.startswith("//") else re.sub(r"^http://", "https://", url)
    parts = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k not in TRACKING])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def handle(url, site):
    match = re.match(rf"https://(?:www\.)?(?:{site})/([A-Za-z0-9._]+)/?$", url)
    return match.group(1) if match else ""


def parse(page):
    clubs = []
    for part in re.split(r'<h2 class="h5 modal-title"[^>]*>', page)[1:]:
        name = html.unescape(re.sub(r"<[^>]+>", "", part.split("</h2>", 1)[0])).strip().replace("’", "'")
        body = part.split('<div class="modal-body">', 1)[-1].split('<button type="button" class="btn btn-lg', 1)[0]
        about, _, follow = body.partition("Follow Us on Social Media")
        paragraphs = [html.unescape(re.sub(r"<[^>]+>", "", p)).strip() for p in re.findall(r"<p>(.*?)</p>", about, re.S)]
        club = {"uw_name": name, "description": "\n\n".join(p for p in paragraphs if p), "website": "",
                "instagram": "", "facebook": "", "x_handle": "", "discord": ""}
        for url in map(clean, re.findall(r'<a href="([^"]+)"', follow)):
            host = urlsplit(url).netloc.lower().removeprefix("www.")
            if host == "instagram.com" and not club["instagram"]:
                club["instagram"] = handle(url, r"instagram\.com")
            elif host in ("facebook.com", "fb.com") and not club["facebook"]:
                club["facebook"] = url
            elif host in ("x.com", "twitter.com") and not club["x_handle"]:
                club["x_handle"] = handle(url, r"x\.com|twitter\.com")
            elif host in ("discord.com", "discord.gg") and not club["discord"]:
                club["discord"] = url
            elif url.startswith("https://") and not club["website"] and host != "washington.edu":
                club["website"] = url
        clubs.append(club)
    return clubs


def main():
    request = urllib.request.Request(SOURCE, headers={"User-Agent": "SportiveCircle/1.0 (UW student project)"})
    page = urllib.request.urlopen(request, timeout=30).read().decode("utf-8")
    clubs = parse(page)
    unknown = [club["uw_name"] for club in clubs if club["uw_name"] not in SPORT_OF]
    if unknown:
        sys.exit(f"New clubs on UW's page: add them to SPORT_OF first: {', '.join(unknown)}")
    for club in clubs:
        name = club["uw_name"]
        for key in WRONG_LINKS.get(name, ()):
            club[key] = ""
        club["name"] = APP_NAME.get(name, f"UW {name} Club")
        club["sport"] = SPORT_OF[name]
        club["who_can_join"] = "men" if name.startswith("Men's") else "women" if name.startswith("Women's") else "everyone"
    with open(OUT, "w", encoding="utf-8") as out:
        json.dump({"source": SOURCE, "checked": date.today().isoformat(), "clubs": clubs}, out, indent=1,
                  ensure_ascii=False)
        out.write("\n")
    print(f"{len(clubs)} clubs written to {OUT}")


if __name__ == "__main__":
    main()
