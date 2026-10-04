import re
import sqlite3

from flask import current_app, g

from .textutil import fold

# How long a request waits for another one's write to finish before giving up ("database is locked").
BUSY_TIMEOUT_SECONDS = 15


def get_db():
    """One connection per request. Rows behave like dicts: row["email"]."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=BUSY_TIMEOUT_SECONDS)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.create_function("fold", 1, fold, deterministic=True)  # accent-free, for name search and A-Z
        # WAL: readers never block the writer (and the other way round), so the feed keeps loading while
        # someone joins a game or the reminder loop writes. The setting is saved in the database file.
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Columns added after the first version. "CREATE TABLE IF NOT EXISTS" never changes a table
# that already exists, so databases with real data get these added here instead.
# To add a column later: put it in schema.sql AND append it here.
# (Columns and tables of removed features, like ranks, stay in older databases unused; nothing reads them.)
ADDED_COLUMNS = [
    ("events", "try_it", "INTEGER NOT NULL DEFAULT 0"),  # a club's try-it-out session: new people welcome
    ("direct_messages", "deleted", "INTEGER NOT NULL DEFAULT 0"),  # 1 = its sender deleted it for everyone
    ("event_messages", "deleted", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "verify_sent_at", "TEXT"),
    ("users", "failed_logins", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "locked_until", "TEXT"),
    ("users", "email_reminders", "INTEGER NOT NULL DEFAULT 1"),
    ("rsvps", "reminder_sent", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "avatar_updated", "TEXT"),
    ("users", "showcase", "TEXT"),
    ("events", "club_id", "INTEGER REFERENCES clubs(id) ON DELETE SET NULL"),
    ("clubs", "status", "TEXT NOT NULL DEFAULT 'pending'"),
    ("clubs", "club_kind", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "verification_url", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "officer_role", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "member_estimate", "INTEGER NOT NULL DEFAULT 0"),
    ("clubs", "focus", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "joining", "TEXT NOT NULL DEFAULT 'open'"),
    ("clubs", "experience", "TEXT NOT NULL DEFAULT 'none'"),
    ("clubs", "who_can_join", "TEXT NOT NULL DEFAULT 'everyone'"),
    ("clubs", "dues", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "gear", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "competes", "INTEGER NOT NULL DEFAULT 0"),
    ("clubs", "how_to_join", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "club_email", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "instagram", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "review_note", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "reviewed_at", "TEXT"),
    ("clubs", "join_question", "TEXT NOT NULL DEFAULT ''"),
    ("club_members", "message", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "tiktok", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "snapchat", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "x_handle", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "facebook", "TEXT NOT NULL DEFAULT ''"),
    ("clubs", "youtube", "TEXT NOT NULL DEFAULT ''"),
    ("users", "suspended", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "photo_skipped", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "pronouns", "TEXT NOT NULL DEFAULT ''"),
    ("users", "gender", "TEXT NOT NULL DEFAULT ''"),
    ("users", "instagram", "TEXT NOT NULL DEFAULT ''"),
    ("users", "snapchat", "TEXT NOT NULL DEFAULT ''"),
    ("users", "tiktok", "TEXT NOT NULL DEFAULT ''"),
    ("users", "x_handle", "TEXT NOT NULL DEFAULT ''"),
    ("users", "linkedin", "TEXT NOT NULL DEFAULT ''"),
    ("users", "phone", "TEXT NOT NULL DEFAULT ''"),
    ("users", "phone_verified", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "sms_updates", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "sms_consent_at", "TEXT"),
    ("users", "sms_code", "TEXT"),
    ("users", "sms_code_expires", "TEXT"),
    ("users", "sms_code_attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "sms_sent_at", "TEXT"),
    ("events", "is_private", "INTEGER NOT NULL DEFAULT 0"),
    ("events", "password", "TEXT NOT NULL DEFAULT ''"),
    ("events", "team_size", "INTEGER"),
    ("rsvps", "team", "INTEGER"),
    ("rsvps", "remind_minutes", "INTEGER NOT NULL DEFAULT 60"),
    ("invites", "note", "TEXT NOT NULL DEFAULT ''"),
    ("events", "open_to", "TEXT NOT NULL DEFAULT 'everyone'"),
    ("clubs", "logo_updated", "TEXT"),
    ("clubs", "contact_phone", "TEXT NOT NULL DEFAULT ''"),
    ("events", "members_only", "INTEGER NOT NULL DEFAULT 0"),
    ("club_posts", "event_id", "INTEGER REFERENCES events(id) ON DELETE SET NULL"),
    ("club_posts", "weeks", "INTEGER NOT NULL DEFAULT 1"),  # a post about a weekly series: how many weeks
    ("notices", "key", "TEXT"),
    ("users", "theme", "TEXT NOT NULL DEFAULT 'light'"),
    ("users", "session_version", "INTEGER NOT NULL DEFAULT 0"),
    ("events", "revision", "INTEGER NOT NULL DEFAULT 0"),  # +1 on every edit or cancel (calendar SEQUENCE)
    ("users", "weekly_digest", "INTEGER NOT NULL DEFAULT 1"),
    ("users", "email_friend_games", "INTEGER NOT NULL DEFAULT 1"),  # "Maya posted a game" emails (friendgames.py)  # the Monday "Games this week" email (digest.py)
    ("users", "read_receipts", "INTEGER NOT NULL DEFAULT 1"),  # "Seen" in DMs (off both ways, like WhatsApp)
    ("direct_messages", "photo_id", "INTEGER REFERENCES chat_photos(id) ON DELETE SET NULL"),  # a photo in a chat
    ("event_messages", "photo_id", "INTEGER REFERENCES chat_photos(id) ON DELETE SET NULL"),
    ("users", "texts_card_done", "INTEGER NOT NULL DEFAULT 0"),  # 1 = closed the "New: texts" card on Home
    ("users", "texts_announced_at", "TEXT"),                     # when tools/announce_texts.py emailed them
    ("direct_messages", "event_id", "INTEGER REFERENCES events(id) ON DELETE SET NULL"),
    ("users", "sms_stopped_at", "TEXT"),  # when Twilio said they replied STOP (Settings → Texts explains)
]


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf-8"))
    # The site runs 2 workers that start at the same moment: one at a time from here, so they can't both add the
    # same column (the second one would crash with "duplicate column name" and take the deploy down).
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    for table, column, definition in ADDED_COLUMNS:
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    if db.execute("PRAGMA user_version").fetchone()[0] < 1:  # once per database (version 1 = clubs sorted)
        sort_other_clubs(db)
        db.execute("PRAGMA user_version = 1")
    if db.execute("PRAGMA user_version").fetchone()[0] < 2:  # version 2 = club posts know their weeks
        count_series_weeks(db)
        db.execute("PRAGMA user_version = 2")
    db.commit()


def count_series_weeks(db):
    """Posts about a weekly series, written before posts kept their number of weeks, get it back from their words
    ("... for 4 weeks"), so canceling or editing one week doesn't treat the whole series as one event."""
    for post in db.execute("""SELECT id, body FROM club_posts WHERE weeks = 1 AND (body LIKE 'New: %'
                               OR body LIKE 'New members-only events%' OR body LIKE 'New private events%')""").fetchall():
        post_id, body = post[0], post[1]
        found = re.search(r"for (\d+) weeks", body)
        db.execute("UPDATE club_posts SET weeks = ? WHERE id = ?", (int(found.group(1)) if found else 2, post_id))


# Words in a club's name that mean one of the newer sports. Clubs registered as "Other" before that sport existed
# move to it (e.g. "UW Boxing Club" -> Boxing), once per database. Only "Other" clubs are touched, and only that
# once, so an officer who picks "Other" later keeps it.
CLUB_NAME_SPORTS = [
    ("kickboxing", "muay_thai"), ("boxing", "boxing"), ("jiu-jitsu", "bjj"), ("jiu jitsu", "bjj"), ("bjj", "bjj"),
    ("judo", "judo"),
    ("karate", "karate"), ("kendo", "kendo"), ("muay thai", "muay_thai"),
    ("taekwondo", "taekwondo"), ("wrestling", "wrestling"), ("fencing", "fencing"), ("archery", "archery"),
    ("badminton", "badminton"), ("baseball", "baseball"), ("softball", "softball"), ("bowling", "bowling"),
    ("cricket", "cricket"), ("disc golf", "disc_golf"), ("dodgeball", "dodgeball"), ("equestrian", "equestrian"),
    ("field hockey", "field_hockey"), ("figure skating", "figure_skating"), ("ice hockey", "ice_hockey"),
    ("gymnastics", "gymnastics"), ("handball", "handball"), ("lacrosse", "lacrosse"),
    ("racquetball", "racquetball"), ("rugby", "rugby"), ("sailing", "sailing"), ("skateboard", "skateboarding"),
    ("squash", "squash"), ("swim", "swimming"), ("table tennis", "table_tennis"), ("ping pong", "table_tennis"),
    ("triathlon", "triathlon"), ("water polo", "water_polo"), ("powerlifting", "weightlifting"),
    ("weightlifting", "weightlifting"), ("barbell", "weightlifting"), ("golf", "golf"),
]


def sort_other_clubs(db):
    """Clubs filed under "Other" whose name says the sport (see CLUB_NAME_SPORTS) move to that sport."""
    if db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'clubs'").fetchone() is None:
        return
    for word, sport in CLUB_NAME_SPORTS:  # "disc golf" before "golf", "kickboxing" maps like Muay Thai
        db.execute("UPDATE clubs SET sport = ? WHERE sport = 'other' AND LOWER(name) LIKE ?", (sport, f"%{word}%"))


def user_sports(user_id):
    rows = get_db().execute("SELECT sport FROM user_sports WHERE user_id = ?", (user_id,)).fetchall()
    return [row["sport"] for row in rows]


def set_user_sports(user_id, sports):
    db = get_db()
    db.execute("DELETE FROM user_sports WHERE user_id = ?", (user_id,))
    db.executemany("INSERT INTO user_sports (user_id, sport) VALUES (?, ?)", [(user_id, s) for s in sports])


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
