"""Fill the local database with demo students and events (local development only).

    python seed.py

Every demo account uses the password below. Running it again adds nothing new.
"""
from datetime import timedelta
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from werkzeug.security import generate_password_hash

from sportive import create_app
from sportive.db import get_db, set_user_sports
from sportive.photos import make_avatar
from sportive.timeutil import now_local, to_db

DEMO_PASSWORD = "huskies-demo-2026"

USERS = [
    ("demo.maya@uw.edu", "Maya Chen", 2027, ["basketball", "running", "hiking"], "Pickup hoops most evenings."),
    ("demo.jordan@uw.edu", "Jordan Rivera", 2028, ["soccer", "ultimate", "gym"], "Looking for a gym buddy for 7am lifts."),
    ("demo.sam@uw.edu", "Sam Okafor", 2026, ["climbing", "snow", "hiking"], "Weekend trips to Stevens Pass."),
    ("demo.priya@uw.edu", "Priya Nair", 2029, ["tennis", "pickleball", "volleyball", "esports"], ""),
]

# (host index, title, sport, location, start = timedelta from now or (days ahead, hour, minute), hours long, skill, max players, extra, note, quick)
EVENTS = [
    (0, "Need 3 for 5v5", "basketball", "IMA (Intramural Activities Building)", timedelta(minutes=40), 1.5,
     "All levels", 10, 6, "Court 2, look for the purple shirts", 1),
    (1, "Sunday pickup soccer", "soccer", "Denny Field", (2, 11, 0), 2, "Casual", 22, 0,
     "Bring a light and a dark shirt.", 0),
    (2, "Bouldering night", "climbing", "IMA (Intramural Activities Building)", (1, 19, 30), 2,
     "Intermediate", 8, 0, "Meet at the climbing wall front desk.", 0),
    (0, "Easy 5K on the Burke-Gilman", "running", "Burke-Gilman Trail", (1, 7, 30), 1, "Casual",
     20, 0, "About 9:30/mile pace. Meet at the trail by the UW Tower.", 0),
    (2, "Stevens Pass day trip", "snow", "Off campus (see note)", (6, 6, 0), 12, "All levels", 5, 0,
     "Carpool from the U District at 6am. Split gas.", 0),
    (3, "Doubles at the courts", "tennis", "IMA South Tennis Courts", (3, 16, 0), 1.5, "Casual", 4, 0,
     "", 0),
    (3, "Pickleball doubles", "pickleball", "IMA North Tennis Courts", (2, 15, 0), 1.5, "All levels", 8, 0,
     "Court 12. Paddles to share, bring your own if you have one.", 0),
    (1, "Ultimate scrimmage", "ultimate", "Denny Field", (4, 17, 30), 2, "Intermediate", 14, 0,
     "", 0),
    (3, "Valorant 5-stack", "esports", "Online", (1, 21, 0), 2, "All levels", 5, 1, "Discord link in note after you join (coming soon!)", 0),
]


COLORS = ["#4b2e83", "#b7a57a", "#2e6f83", "#83402e"]


def demo_picture(name, color):
    """A colored square with the person's initials, standing in for a real photo."""
    image = Image.new("RGB", (256, 256), color)
    initials = "".join(part[0] for part in name.split())[:2]
    ImageDraw.Draw(image).text((128, 128), initials, fill="white", anchor="mm",
                                font=ImageFont.load_default(size=110))
    output = BytesIO()
    image.save(output, "PNG")
    return make_avatar(output.getvalue())


# Past games so demo players already have ranks: (host index, sport, place, how many games)
HISTORY = [
    (0, "basketball", "IMA (Intramural Activities Building)", 9),  # Maya -> Intermediate in basketball
    (2, "climbing", "IMA (Intramural Activities Building)", 8),    # Sam -> Intermediate in climbing
    (1, "ultimate", "Denny Field", 8),                             # Jordan -> Intermediate in ultimate
    (3, "tennis", "IMA South Tennis Courts", 3),                   # Priya -> still Casual
]


# Demo clubs (clearly marked as demos, never pretending to be a real UW club).
DEMO_CLUBS = [
    dict(name="Demo Spikeball Club", sport="spikeball", focus="recreational", joining="open", experience="none",
         who_can_join="everyone", gear="Nets provided", competes=0, member_estimate=35,
         meets="Tuesdays 5-7 PM", location="The Quad", officer=0,
         description="A demo club for trying out Sportive Circle: casual roundnet on the Quad, all levels welcome.",
         how_to_join="Just show up to any Tuesday session!", dues="Free",
         join_question="Have you played roundnet before?", club_email="demo-spikeball@example.com",
         contact_url="https://example.com/demo-spikeball"),
    dict(name="Demo Club Ultimate", sport="ultimate", focus="competitive", joining="tryouts", experience="some",
         who_can_join="everyone", dues="$60/quarter", gear="Cleats", competes=1, member_estimate=28,
         meets="Mon, Wed & Fri 6-8 PM", location="Recreation Field 1 (by the IMA)", officer=1,
         description="A demo competitive team: we travel to college tournaments. Tryouts happen in autumn quarter.",
         how_to_join="Come to our open tryout practices during the first two weeks of the quarter.",
         join_question="What position do you play, and where have you played before?",
         club_email="demo-ultimate@example.com", contact_url="https://example.com/demo-ultimate"),
    dict(name="Demo Climbing Crew", sport="climbing", focus="instructional", joining="open", experience="none",
         who_can_join="everyone", dues="$15/quarter", gear="Shoes available to borrow", competes=0, member_estimate=50,
         meets="Thursdays 7-9 PM", location="IMA (Intramural Activities Building)", officer=2,
         description="A demo club that teaches bouldering and top-roping from zero. Beginners are our favorite people.",
         how_to_join="Sign up for a Thursday intro session.",
         join_question="Have you climbed before? (It's totally fine if not!)",
         club_email="demo-climbing@example.com", contact_url="https://example.com/demo-climbing"),
]


def add_clubs(db, ids, now):
    for demo in DEMO_CLUBS:
        club = dict(demo)  # a copy, so seeding twice (e.g. in tools/check.py) works
        officer = ids[club.pop("officer")]
        cur = db.execute(
            f"""INSERT INTO clubs ({", ".join(club)}, club_kind, verification_url, officer_role, status,
                                   created_by, created_at)
                VALUES ({", ".join("?" for _ in club)}, 'rso', 'https://huskylink.washington.edu/organizations',
                        'President', 'approved', ?, ?)""",
            (*club.values(), officer, to_db(now)))
        for user_id in ids:
            db.execute("INSERT INTO club_members (club_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
                       (cur.lastrowid, user_id, "officer" if user_id == officer else "member", to_db(now)))


def add_history(db, ids, now):
    for host, sport, place, games in HISTORY:
        for n in range(games):
            day = now - timedelta(days=n + 2)
            starts = day.replace(hour=18, minute=0)
            cur = db.execute(
                "INSERT INTO events (host_id, title, sport, location, starts_at, ends_at, skill_level, max_players)"
                " VALUES (?, ?, ?, ?, ?, ?, 'Casual', 10)",
                (ids[host], f"{sport.title()} run #{n + 1}", sport, place, to_db(starts),
                 to_db(starts + timedelta(hours=1))))
            for user_id in ids:  # everyone played
                db.execute("INSERT INTO rsvps (event_id, user_id, created_at, reminder_sent) VALUES (?, ?, ?, 1)",
                           (cur.lastrowid, user_id, to_db(starts - timedelta(days=1))))
        for other in ids:  # the other three vouch for the host
            if other != ids[host] and games >= 8:
                db.execute("INSERT OR IGNORE INTO vouches VALUES (?, ?, ?, ?)", (sport, other, ids[host], to_db(now)))


def main():
    app = create_app({"DEBUG": True})
    with app.app_context():
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE email = ?", (USERS[0][0],)).fetchone():
            print("Demo data is already there.")
            return
        ids = []
        for email, name, grad_year, sports, bio in USERS:
            cur = db.execute(
                "INSERT INTO users (email, password_hash, full_name, grad_year, birth_date, bio, verified)"
                " VALUES (?, ?, ?, ?, '2005-04-01', ?, 1)",
                (email, generate_password_hash(DEMO_PASSWORD, app.config["PASSWORD_HASH_METHOD"]), name, grad_year, bio),
            )
            ids.append(cur.lastrowid)
            set_user_sports(cur.lastrowid, sports)
            db.execute("INSERT INTO avatars (user_id, image) VALUES (?, ?)",
                       (cur.lastrowid, demo_picture(name, COLORS[len(ids) % len(COLORS)])))
            db.execute("UPDATE users SET avatar_updated = 'seed' WHERE id = ?", (cur.lastrowid,))

        now = now_local()
        for host, title, sport, location, offset, hours, skill, max_players, extra, note, quick in EVENTS:
            if isinstance(offset, timedelta):
                starts = (now + offset).replace(minute=(now + offset).minute // 15 * 15)
            else:
                days, hour, minute = offset
                starts = (now + timedelta(days=days)).replace(hour=hour, minute=minute)
            cur = db.execute(
                "INSERT INTO events (host_id, title, sport, location, starts_at, ends_at, skill_level,"
                " max_players, extra_players, note, is_quick) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ids[host], title, sport, location, to_db(starts), to_db(starts + timedelta(hours=hours)),
                 skill, max_players, extra, note, quick),
            )
            joined = to_db(now - timedelta(days=1))
            db.execute("INSERT INTO rsvps (event_id, user_id, created_at) VALUES (?, ?, ?)", (cur.lastrowid, ids[host], joined))
            for other in ids:  # a few people join a few events
                if other != ids[host] and (cur.lastrowid + other) % 3 == 0:
                    db.execute("INSERT INTO rsvps (event_id, user_id, created_at) VALUES (?, ?, ?)", (cur.lastrowid, other, joined))
        add_history(db, ids, now)
        add_clubs(db, ids, now)
        db.commit()
        print(f"Added {len(USERS)} demo users and {len(EVENTS)} events, with past games and ranks.")
        print(f"Log in as {USERS[0][0]} with password {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
