"""Bot swarm: hundreds of fake Huskies using the app at once, on a throwaway copy (never the live site).

    python tools/bot_swarm.py                 # 200 bots, 12 at a time, 40 actions each
    python tools/bot_swarm.py 400 20 60       # bots, threads, actions per bot

Each bot signs up with a UW email, adds friends, posts games (some private, some "No limit"), joins and leaves,
reserves spots for friends, sends games to friends, messages, searches, registers and joins clubs, and runs its
club's officers (add, remove, hand over ownership). Two stampede tests hit the riskiest spots on purpose:
50 bots grabbing the last 4 spots of a game at the same moment, and 300 bots joining a no-limit run.

At the end it checks the database never broke its own rules (no game over its limit, every club has an owner who
is an officer, no one in a game twice) and lists every page that crashed (HTTP 500). Exit code 1 if anything broke.
"""
import io
import os
import random
import re
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from sportive import create_app  # noqa: E402
from sportive.constants import SPORT_LOCATIONS  # noqa: E402
from sportive.db import get_db  # noqa: E402
from sportive.timeutil import now_local  # noqa: E402

PASSWORD = "bot-password-123"
SPORTS = ["basketball", "soccer", "running", "tennis", "pickleball", "volleyball", "ultimate", "spikeball"]
FIRST = ["Maya", "Jordan", "Sam", "Alex", "Priya", "Diego", "Mei", "Omar", "Lena", "Kai", "Noah", "Ava", "Zoe", "Eli"]
LAST = ["Chen", "Garcia", "Kim", "Nguyen", "Patel", "Lopez", "Smith", "Ito", "Brown", "Ali", "Park", "Lee"]

crashes = []            # (method, path, status)
counts = Counter()      # what the bots did
lock = threading.Lock()


def photo():
    out = io.BytesIO()
    Image.new("RGB", (300, 300), random.choice(["purple", "gold", "teal"])).save(out, "PNG")
    return out.getvalue()


def form_time(delta):
    return (now_local() + delta).strftime("%Y-%m-%dT%H:%M")


class Bot:
    def __init__(self, app, n):
        self.app, self.n = app, n
        self.client = app.test_client()
        self.email = f"bot{n}@uw.edu"
        self.name = f"{random.choice(FIRST)} {random.choice(LAST)}{n}"
        self.id = None

    def call(self, method, path, **kw):
        response = getattr(self.client, method)(path, **kw)
        if response.status_code >= 500:
            with lock:
                crashes.append((method.upper(), path, response.status_code))
        return response

    def signup(self):
        self.call("post", "/signup", data={"full_name": self.name, "email": self.email, "password": PASSWORD,
                                           "password2": PASSWORD, "birth_date": "2005-03-01", "grad_year": "2028"})
        self.call("post", "/signup/sports", data={"sports": random.sample(SPORTS, 3)})
        self.call("post", "/signup/texts", data={"phone": ""})  # skips texts
        with self.app.app_context():
            row = get_db().execute("SELECT id, verify_code FROM users WHERE email = ?", (self.email,)).fetchone()
        self.id = row["id"]
        self.call("post", "/verify", data={"code": row["verify_code"]})
        self.call("post", "/profile/photo", data={"photo": (io.BytesIO(photo()), "me.png")},
                  content_type="multipart/form-data")
        counts["signed up"] += 1


def event_ids(app, where="1=1"):
    with app.app_context():
        return [r[0] for r in get_db().execute(f"SELECT id FROM events WHERE cancelled = 0 AND {where}")]


def club_ids(app, where="1=1"):
    with app.app_context():
        return [r[0] for r in get_db().execute(f"SELECT id FROM clubs WHERE {where}")]


def post_game(bot, others):
    sport = random.choice(SPORTS)
    start = timedelta(hours=random.randint(2, 96))
    data = {"title": f"{sport} run {random.randint(1, 999)}", "sport": sport,
            "location": random.choice(SPORT_LOCATIONS[sport]), "skill_level": "Casual",
            "starts_at": form_time(start), "ends_at": form_time(start + timedelta(hours=1)),
            "players": str(random.choice([4, 6, 10, 20, 500])), "note": "Bring water"}
    roll = random.random()
    if roll < 0.15:
        data["no_limit"] = "1"
    elif roll < 0.25:
        data.update(is_private="1", password="dawgs26")
    if others and random.random() < 0.3:
        data["reserve"] = [str(o.id) for o in random.sample(others, min(2, len(others)))]
    bot.call("post", "/events/new", data=data)
    counts["posted a game"] += 1


def act(bot, bots, app):
    """One random thing a student would do."""
    others = [b for b in bots if b is not bot and b.id]
    roll = random.random()
    games = event_ids(app, "is_private = 0")
    if roll < 0.12:
        post_game(bot, [])
    elif roll < 0.17:
        sport = random.choice(SPORTS)
        bot.call("post", "/need-players", data={"sport": sport, "location": random.choice(SPORT_LOCATIONS[sport]),
                                                "starts_in": "30", "duration": "60", "players": "8",
                                                "skill_level": "All levels"})
        counts["need players"] += 1
    elif roll < 0.40 and games:
        game = random.choice(games)
        bot.call("get", f"/events/{game}")
        bot.call("post", f"/events/{game}/join")
        counts["joined"] += 1
    elif roll < 0.45 and games:
        bot.call("post", f"/events/{random.choice(games)}/leave")
        counts["left"] += 1
    elif roll < 0.55 and others:
        friend = random.choice(others)
        bot.call("post", f"/friends/request/{friend.id}")
        friend.call("post", f"/friends/accept/{bot.id}")
        counts["made a friend"] += 1
    elif roll < 0.62 and others:
        friend = random.choice(others)
        bot.call("post", f"/messages/{friend.id}", data={"body": random.choice(["yo", "you playing?", "gg 🔥"])})
        counts["messaged"] += 1
    elif roll < 0.67 and games:
        game = random.choice(games)
        page = bot.call("get", f"/events/{game}/send").data.decode()
        friends = re.findall(r'name="friend" value="(\d+)"', page)
        if friends:
            bot.call("post", f"/events/{game}/send", data={"friend": friends[:2], "note": "come thru"})
            counts["sent a game to friends"] += 1
    elif roll < 0.72 and games:
        game = random.choice(games)
        page = bot.call("get", f"/events/{game}/party").data.decode()
        friends = re.findall(r'name="friend" value="(\d+)"', page)
        if friends:
            bot.call("post", f"/events/{game}/party", data={"friend": friends[:1]})
            counts["reserved spots"] += 1
    elif roll < 0.76:
        with app.app_context():
            invite = get_db().execute("SELECT event_id FROM invites WHERE guest_id = ? AND status = 'pending'",
                                      (bot.id,)).fetchone()
        if invite:
            bot.call("post", f"/events/{invite[0]}/invite/answer", data={"answer": random.choice(["yes", "no"])})
            counts["answered an invite"] += 1
    elif roll < 0.80:
        bot.call("get", "/messages?q=" + random.choice(FIRST)[:3])
        bot.call("get", "/friends?q=" + random.choice(LAST)[:3])
        counts["searched"] += 1
    elif roll < 0.84:
        sport = random.choice(SPORTS)
        start = timedelta(hours=random.randint(2, 48))
        bot.call("get", "/events/place-check", query_string={
            "location": random.choice(SPORT_LOCATIONS[sport]), "starts_at": form_time(start),
            "ends_at": form_time(start + timedelta(hours=1))})
        counts["checked a place"] += 1
    elif roll < 0.90:
        clubs = club_ids(app, "status = 'approved'")
        if clubs:
            club = random.choice(clubs)
            bot.call("get", f"/clubs/{club}")
            bot.call("post", f"/clubs/{club}/" + random.choice(["follow", "join"]),
                     data={"message": "Have played a bit!"})
            counts["joined a club"] += 1
    elif roll < 0.95:
        clubs = club_ids(app, f"created_by = {int(bot.id)}")
        if clubs and others:
            club, friend = clubs[0], random.choice(others)
            bot.call("post", f"/clubs/{club}/officers", data={"user": friend.id, "action": "add"})
            action = random.choice(["remove", "owner", "none"])
            if action != "none":
                bot.call("post", f"/clubs/{club}/officers", data={"user": friend.id, "action": action})
            counts["managed officers"] += 1
    else:
        for path in ("/", "/?scope=all", "/?scope=full", "/me/events", "/notifications", "/clubs", "/create",
                     "/settings", f"/u/{bot.id}"):
            bot.call("get", path)
        counts["browsed"] += 1


def stampede(app, bots):
    """50 bots tap Join on the last 4 spots at the same moment: exactly 4 may get in."""
    host = bots[0]
    start = timedelta(hours=30)
    response = host.call("post", "/events/new", data={
        "title": "Stampede", "sport": "basketball", "location": "IMA (Intramural Activities Building)",
        "skill_level": "Casual", "starts_at": form_time(start), "ends_at": form_time(start + timedelta(hours=1)),
        "players": "5"})
    game = int(re.search(r"/events/(\d+)", response.headers["Location"]).group(1))
    racers = [b for b in bots[1:] if b.id][:50]
    barrier = threading.Barrier(len(racers))

    def go(bot):
        barrier.wait()
        bot.call("post", f"/events/{game}/join")

    with ThreadPoolExecutor(len(racers)) as pool:
        list(pool.map(go, racers))
    with app.app_context():
        going = get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (game,)).fetchone()[0]
    return going


def big_run(app, bots):
    """A no-limit hall run: everyone joins, nobody is turned away."""
    host = bots[1]
    start = timedelta(hours=40)
    response = host.call("post", "/events/new", data={
        "title": "Elm Hall Run", "sport": "running", "location": "Burke-Gilman Trail", "skill_level": "Casual",
        "starts_at": form_time(start), "ends_at": form_time(start + timedelta(hours=1)), "no_limit": "1"})
    game = int(re.search(r"/events/(\d+)", response.headers["Location"]).group(1))
    with ThreadPoolExecutor(16) as pool:
        list(pool.map(lambda b: b.call("post", f"/events/{game}/join"), [b for b in bots if b.id][2:]))
    host.call("get", f"/events/{game}")
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM rsvps WHERE event_id = ?", (game,)).fetchone()[0]


def check_rules(app):
    """Things that must always be true, however the bots behaved."""
    problems = []
    with app.app_context():
        db = get_db()
        for row in db.execute("""SELECT e.id, e.max_players, e.extra_players, COUNT(r.user_id) AS going FROM events e
                                 LEFT JOIN rsvps r ON r.event_id = e.id WHERE e.max_players IS NOT NULL
                                 GROUP BY e.id HAVING going + e.extra_players > e.max_players"""):
            problems.append(f"game {row['id']} is over its limit: {row['going']} going of {row['max_players']}")
        for row in db.execute("""SELECT c.id FROM clubs c WHERE NOT EXISTS (SELECT 1 FROM club_members m
                                 WHERE m.club_id = c.id AND m.user_id = c.created_by AND m.role = 'officer')"""):
            problems.append(f"club {row['id']}: its owner isn't an officer")
        for row in db.execute("""SELECT c.id FROM clubs c WHERE NOT EXISTS (SELECT 1 FROM club_members m
                                 WHERE m.club_id = c.id AND m.role = 'officer')"""):
            problems.append(f"club {row['id']} has no officers")
        for row in db.execute("SELECT event_id, user_id FROM rsvps GROUP BY event_id, user_id HAVING COUNT(*) > 1"):
            problems.append(f"user {row['user_id']} is in game {row['event_id']} twice")
        for row in db.execute("""SELECT i.event_id, i.guest_id FROM invites i JOIN rsvps r
                                 ON r.event_id = i.event_id AND r.user_id = i.guest_id WHERE i.status = 'pending'"""):
            problems.append(f"user {row['guest_id']} is in game {row['event_id']} and still has a pending invite")
    return problems


def main():
    n_bots = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    threads = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    actions = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    random.seed(26)
    tmp = tempfile.mkdtemp()
    app = create_app({"TESTING": True, "DATABASE": os.path.join(tmp, "bots.db"), "SECRET_KEY": "bots" * 10,
                      "CSRF_ENABLED": False, "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000",
                      "ADMIN_EMAILS": "bot0@uw.edu"})
    app.logger.disabled = True
    import logging
    logging.disable(logging.CRITICAL)
    started = time.time()

    bots = [Bot(app, n) for n in range(n_bots)]
    with ThreadPoolExecutor(threads) as pool:
        list(pool.map(Bot.signup, bots))
    print(f"{counts['signed up']} bots signed up ({time.time() - started:.0f}s)")

    # A few bots register clubs; bot0 (an admin) approves them.
    for bot in bots[2:8]:
        bot.call("post", "/clubs/new", data={
            "name": f"Bot Club {bot.n}", "sport": random.choice(SPORTS), "description": "A club run by bots, for testing.",
            "meets": "Tuesdays 5-7 PM", "location": "The Quad", "contact_url": "https://example.com",
            "club_kind": "rso", "verification_url": f"https://huskylink.washington.edu/organization/bot{bot.n}",
            "officer_role": "President", "member_estimate": "30", "focus": "recreational", "joining": "open",
            "experience": "none", "who_can_join": "everyone", "dues": "Free", "gear": "None",
            "how_to_join": "Show up", "club_email": f"club{bot.n}@uw.edu", "attest": "1",
            "join_question": "Why do you want to join?",
            "contact_phone_country": "US", "contact_phone": "206-555-0142"})
    for club in club_ids(app):
        bots[0].call("post", f"/admin/clubs/{club}/approve")
    for bot in random.sample(bots, 25):
        post_game(bot, [b for b in bots if b is not bot][:5])

    def life(bot):
        for _ in range(actions):
            act(bot, bots, app)

    with ThreadPoolExecutor(threads) as pool:
        list(pool.map(life, bots))
    print(f"{n_bots * actions} actions done ({time.time() - started:.0f}s)")

    going = stampede(app, bots)
    print(f"Stampede: 50 bots tapped Join on the last 4 spots at once -> {going} of 5 in "
          f"({'OK' if going == 5 else 'OVERBOOKED' if going > 5 else 'spots left empty'})")
    runners = big_run(app, bots)
    print(f"No-limit hall run: {runners} runners in (expected {len(bots) - 1})")

    problems = check_rules(app)
    if going != 5:
        problems.append(f"stampede ended with {going} of 5")
    if runners != len(bots) - 1:
        problems.append(f"no-limit run has {runners} of {len(bots) - 1}")
    print("\nWhat the bots did:", ", ".join(f"{k} {v}" for k, v in counts.most_common()))
    print(f"\nCrashed pages (500): {len(crashes)}")
    for (method, path, status), times in Counter(crashes).most_common(20):
        print(f"   {method} {path} -> {status} (x{times})")
    print(f"Broken rules: {len(problems)}")
    for problem in problems[:20]:
        print("  ", problem)
    print(f"\n{'ALL GOOD' if not crashes and not problems else 'PROBLEMS FOUND'} in {time.time() - started:.0f}s")
    sys.exit(1 if crashes or problems else 0)


if __name__ == "__main__":
    main()
