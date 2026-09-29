import sqlite3

from flask import current_app, g

# How long a request waits for another one's write to finish before giving up ("database is locked").
BUSY_TIMEOUT_SECONDS = 15


def get_db():
    """One connection per request. Rows behave like dicts: row["email"]."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=BUSY_TIMEOUT_SECONDS)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
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
    ("notices", "key", "TEXT"),
    ("users", "theme", "TEXT NOT NULL DEFAULT 'light'"),
    ("users", "session_version", "INTEGER NOT NULL DEFAULT 0"),
]


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf-8"))
    for table, column, definition in ADDED_COLUMNS:
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    db.commit()


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
