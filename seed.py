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
    ("demo.priya@uw.edu", "Priya Nair", 2029, ["tennis", "volleyball", "esports"], ""),
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
    (3, "Doubles at the courts", "tennis", "IMA (Intramural Activities Building)", (3, 16, 0), 1.5, "Intermediate", 4, 0,
     "", 0),
    (1, "Ultimate scrimmage", "ultimate", "Denny Field", (4, 17, 30), 2, "Competitive", 14, 0,
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
        db.commit()
        print(f"Added {len(USERS)} demo users and {len(EVENTS)} events.")
        print(f"Log in as {USERS[0][0]} with password {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
