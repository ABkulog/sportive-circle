"""Every UW sports club, read from two public lists (clubsync.py runs this daily; tools/fetch_rec_clubs.py saves a
copy in data/uw_rec_clubs.json for when the sites are down).

1. UW Recreation's "Clubs Offered" page: each Rec Club's name, description and links (website, Instagram,
   Facebook, X, Discord).
2. HuskyLink (UW's list of Registered Student Organizations): every group filed under Sports/Recreation, with its
   mission and link. Many are the same clubs as on UW Rec's page; those only add their HuskyLink id (used to show
   their HuskyLink events). The rest are new clubs (Pickleball, Bowling, Golf, Hiking...).

A club UW Rec adds later is filed under the sport its name says (or Other) until it gets a line in SPORT_OF; a new
HuskyLink group is left out until it gets a line in HUSKYLINK_CLUBS (most aren't sports), and is logged.
"""
import html
import re
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SOURCE = "https://www.washington.edu/ima/rec-clubs/club-offerings/"
HUSKYLINK = "https://huskylink.washington.edu"
HUSKYLINK_LISTS = ("/club_signup?view=all&group_type=25437", "/club_signup?view=all&group_type=10365")  # RSOs, Rec Clubs

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
# HuskyLink's Sports/Recreation groups: the same club as one on UW Rec's page ("=" + its UW Rec name), the app's
# sport for a club that's only on HuskyLink, or None for a group that isn't a sport (poker, origami, a fan club...).
HUSKYLINK_CLUBS = {
    "Alan's Disciples": None, "Barbell Club at the University of Washington": "weightlifting",
    "Brazilian JiuJitsu Club at the University of Washington": "=Brazilian Jiu-Jitsu",
    "Breakfast Ball Golf Club": "golf", "Climbing Club at the University of Washington": "=Climbing",
    "Climbing Team at the University of Washington": "=Climbing",
    "Competitive Leatherball Cricket @ the University of Washington": "cricket", "Dawg Pack": None,
    "Dub Club Baseball": "=Men's Baseball", "Eta Mu Beta Flag Football Club": "football",
    "Figure Skating at UW": "figure_skating", "Fishing Club @ UW": "other", "Girl Gains UW": "gym",
    "Girlz Gone Wild Womxn's Outdoors Collective": "hiking", "GO FOR GO": None,
    "GRIT LIFT Bodybuilding Club @UW": "weightlifting", "Hacky Sack Club": "other", "Harry's Construction Crew": None,
    "Historical Fencing Club at the UW": "fencing", "Humans vs. Zombies Tag": "other",
    "Husky Archery Club": "=Archery", "Husky Badminton Club": "=Badminton", "Husky Bowling Club": "bowling",
    "Husky Cricket Club": "cricket", "Husky Cycling Club": "=Cycling", "Husky Fencing Club @ UW": "fencing",
    "Husky Fly Fishing Club": "other", "Husky Flying Club": None, "Husky High Adventure": "hiking",
    "Husky MMA": "muay_thai", "Husky Pickleball Club": "pickleball", "Husky Poker Club": None,
    "Husky Roundnet Club": "=Roundnet", "Husky Rugby Club": "=Men's Rugby", "Husky Running Club": "=Running",
    "Husky Sailing Team": "=Sailing", "Husky Ski Team": "=Skiing", "Husky Squash Club": "=Squash",
    "Husky Surf Club": "other", "Husky Table Tennis Club": "=Table Tennis", "Husky Taekwondo Club": "=Taekwondo",
    "Husky Tennis Club": "=Tennis", "Husky Triathlon Club": "=Triathlon", "Husky Water Polo": "water_polo",
    "Husky Wiffle Club": "other", "Husky Winter Sports": "snow", "Husky Wrestling Club": "=Wrestling",
    "Husky Wushu Club": "=Wushu", "Ice Hockey Club at the UW": "ice_hockey",
    "Intercollegiate Horse Shows Association Equestrian Team at the UW": "=Equestrian",
    "Judo Club at the University of Washington": "=Judo", "JUST ELITES Basketball Club": "basketball",
    "Kannagara Aikido club at UW": "=Aikido", "Kendo Club at the University of Washington": "=Kendo",
    "Kung Fu/Tai Chi Club at the University of Washington": "=Kung Fu / Tai Chi",
    "Kyokushin Karate Washington Club": "karate", "Lowkey Sports Club": "other", "Martial Arts at UW": "other",
    "Men's Basketball Club @ UW": "basketball", "Men's Soccer Club at the University of Washington": "=Men's Soccer",
    "Men's Volleyball Club at UW": "=Men's Volleyball", "Origami Club": None, "Peaks & Professors at UW": "hiking",
    "QueerTrans Sports Club": "other", "Riichi Mahjong Club at University of Washington": None,
    "Shellhouse Canoe Family at UW": "=Canoe Family", "SKY@UW": None, "snowbee snowboarding club": "snow",
    "Sports Analytics Club at UW": None, "Strawberries & Sudoku at UW": None,
    "Sumo Union Membership Organization": None, "Swim Club at UW": "=Swimming", "Team Bao": None,  # Sumo: watching it on TV
    "The Golf Club at UW": "golf", "The Hiking Club at UW": "hiking", "Union Bay Rowing Club": "=Union Bay Rowing",
    "Washington Husky STUNT": "other", "Washington Men's Gymnastics": "gymnastics",
    "Washington Men's Ultimate Frisbee": "=Men's Ultimate Frisbee",
    "Washington Women's Ultimate Frisbee": "=Women's Ultimate Frisbee", "Washington Yacht Club": "=Washington Yacht Club",
    "Women's Club Baseball at The University of Washington": "baseball",
    "Women's Club Soccer at UW": "=Women's Soccer", "Women's Club Volleyball at UW": "=Women's Volleyball",
    "Women's Field Hockey at the University of Washington": "field_hockey",
    "Women's Ice Hockey Club UW Chapter": "=Women's Ice Hockey", "Women's Run Club @UW": "running",
    "Women's Water Polo Club at University of Washington": "=Women's Water Polo", "Womens Basketball Club": "basketball",
    "Men's Husky Lacrosse Club at the University of Washington": "=Men's Lacrosse",
    "Washington Women's Lacrosse Club": "=Women's Lacrosse", "Women's Rugby at UW": "=Women's Rugby",
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


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "SportiveCircle/1.0 (UW student project)"})
    return urllib.request.urlopen(request, timeout=60).read().decode("utf-8")


def parse_huskylink(page):
    """[(group id, name, link, mission)] for the Sports/Recreation groups on a HuskyLink list page."""
    groups = []
    for block in page.split('<li class="list-group-item" style="padding: 20px 15px;">')[1:]:
        title = re.search(r'<h2 class="media-heading header-cg--h4">\s*<a[^>]*href="\s*([^"]+?)\s*"[^>]*>\s*(.*?)\s*</a>',
                          block, re.S)
        kind = re.search(r'<p class="h5 media-heading grey-element">\s*(.*?)\s*</p>', block, re.S)
        group_id = re.search(r'id="club_(\d+)"', block)
        if not (title and kind and group_id) or "Sports/Recreation" not in kind.group(1):
            continue
        mission = re.search(rf'id="club_{group_id.group(1)}"[^>]*>\s*<strong>Mission</strong><br>(.*?)</p>', block, re.S)
        about = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", mission.group(1))).split()) if mission else ""
        groups.append((int(group_id.group(1)), html.unescape(html.unescape(title.group(2))).strip(), clean(title.group(1)), about))
    return groups


def link_kind(url):
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    return "discord" if host in ("discord.gg", "discord.com") else "website"


def guess_sport(name):
    """A club UW Rec added since SPORT_OF was written: the sport its name says, else Other."""
    from .constants import SPORTS
    lowered = name.lower()
    for key, label in SPORTS.items():
        if key != "other" and any(word.lower() in lowered for word in label.replace("/", " ").split() if len(word) > 3):
            return key
    return "other"


def tidy(text):
    """HuskyLink's missions come with stray line breaks ("\\r\\n"): one paragraph per blank line, single spaces."""
    paragraphs = re.split(r"(?:\s*\n\s*){2,}", text.replace("\\r\\n", "\n").replace("\r\n", "\n"))
    return "\n\n".join(" ".join(p.split()) for p in paragraphs if p.strip())


def links_in_text(text):
    """Links a club put in its own description ("@uwhackysack on Instagram", a Facebook group, an email): they
    chose to make these public, so they go with the club's other links."""
    found = {}
    for url in re.findall(r"https?://[^\s<>\"')]+", text):
        url = clean(url.rstrip(".,!"))
        host = urlsplit(url).netloc.lower().removeprefix("www.")
        if host == "instagram.com" and handle(url, r"instagram\.com"):
            found.setdefault("instagram", handle(url, r"instagram\.com"))
        elif host in ("facebook.com", "fb.com"):
            found.setdefault("facebook", url)
        elif host in ("discord.gg", "discord.com"):
            found.setdefault("discord", url)
        elif host in ("x.com", "twitter.com") and handle(url, r"x\.com|twitter\.com"):
            found.setdefault("x_handle", handle(url, r"x\.com|twitter\.com"))
        else:
            found.setdefault("website", url)
    mention = re.search(r"@([A-Za-z0-9._]{2,30}) on Instagram", text, re.I)
    if mention:
        found.setdefault("instagram", mention.group(1).rstrip("."))
    email = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    if email:
        found.setdefault("club_email", email.group(0))
    return found


def build_listing(log=print):
    """Every UW sports club, read live: {"source", "clubs": [...]}. Raises if a site can't be read."""
    clubs = parse(fetch(SOURCE))
    for club in clubs:
        name = club["uw_name"]
        for key in WRONG_LINKS.get(name, ()):
            club[key] = ""
        if name not in SPORT_OF:
            log(f"New UW Rec club, filed by its name until it's in SPORT_OF: {name}")
        club["name"] = APP_NAME.get(name, f"UW {name} Club")
        club["sport"] = SPORT_OF.get(name) or guess_sport(name)
        club["who_can_join"] = "men" if name.startswith("Men's") else "women" if name.startswith("Women's") else "everyone"
        club["source"], club["huskylink_id"], club["uw_page"] = "uw_rec", None, SOURCE
    by_uw_name = {club["uw_name"]: club for club in clubs}
    unsorted = []
    for path in HUSKYLINK_LISTS:
        for group_id, name, link, about in parse_huskylink(fetch(HUSKYLINK + path)):
            about = tidy(about)
            if name not in HUSKYLINK_CLUBS:
                unsorted.append(name)
                continue
            sport = HUSKYLINK_CLUBS[name]
            if sport is None:
                continue
            if sport.startswith("="):  # the same club as on UW Rec's page: its HuskyLink group, and its mission if
                same = by_uw_name.get(sport[1:])  # UW Rec's page has no description
                if same:
                    same["huskylink_id"] = same["huskylink_id"] or group_id
                    same["description"] = same["description"] or about
                continue
            lowered = name.lower()
            club = {"uw_name": name, "name": name, "sport": sport, "description": about, "website": "", "instagram": "",
                    "facebook": "", "x_handle": "", "discord": "", "source": "huskylink", "huskylink_id": group_id,
                    "uw_page": link if link.startswith(HUSKYLINK) else "",
                    "who_can_join": "men" if "men's" in lowered and "women's" not in lowered
                    else "women" if any(w in lowered for w in ("women", "womxn", "girl")) else "everyone"}
            if not link.startswith(HUSKYLINK):  # their HuskyLink page is uw_page; anything else is their own site
                club[link_kind(link)] = link
            clubs.append(club)
    if unsorted:
        log("New HuskyLink sports groups, left out until they're in HUSKYLINK_CLUBS: " + "; ".join(unsorted))
    for club in clubs:
        club["club_email"] = ""
        for key, value in links_in_text(club["description"]).items():
            if not club[key] and not (key == "website" and value.startswith((HUSKYLINK, SOURCE))):
                club[key] = value
    return {"source": SOURCE, "clubs": clubs}
