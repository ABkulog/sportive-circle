import sqlite3

from flask import current_app, g


def get_db():
    """One connection per request. Rows behave like dicts: row["email"]."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Columns added after the first version. "CREATE TABLE IF NOT EXISTS" never changes a table
# that already exists, so databases with real data get these added here instead.
# To add a column later: put it in schema.sql AND append it here.
ADDED_COLUMNS = [
    ("users", "verify_sent_at", "TEXT"),
    ("users", "failed_logins", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "locked_until", "TEXT"),
    ("users", "email_reminders", "INTEGER NOT NULL DEFAULT 1"),
    ("rsvps", "reminder_sent", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "avatar_updated", "TEXT"),
    ("users", "showcase", "TEXT"),
    ("users", "show_ranks", "INTEGER NOT NULL DEFAULT 1"),
    ("events", "tryout_spots", "INTEGER NOT NULL DEFAULT 0"),
    ("rsvps", "is_tryout", "INTEGER NOT NULL DEFAULT 0"),
    ("events", "allow_plus_ones", "INTEGER NOT NULL DEFAULT 1"),
    ("rsvps", "plus_one_of", "INTEGER REFERENCES users(id) ON DELETE SET NULL"),
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
