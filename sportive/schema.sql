-- Sportive Circle @ UW database schema.
-- Every statement is "IF NOT EXISTS", so this runs safely on every startup.

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,          -- must be @uw.edu
    password_hash   TEXT NOT NULL,                 -- never the plain password
    full_name       TEXT NOT NULL,
    grad_year       INTEGER,
    birth_date      TEXT,                          -- YYYY-MM-DD (for the birthday coupon)
    bio             TEXT NOT NULL DEFAULT '',
    verified        INTEGER NOT NULL DEFAULT 0,    -- 1 once the email code is confirmed
    verify_code     TEXT,
    verify_expires  TEXT,
    verify_attempts INTEGER NOT NULL DEFAULT 0,
    verify_sent_at  TEXT,                          -- for the "wait before resending" limit
    failed_logins   INTEGER NOT NULL DEFAULT 0,    -- wrong passwords in a row
    locked_until    TEXT,                          -- set after too many wrong passwords
    email_reminders INTEGER NOT NULL DEFAULT 1,    -- 0 = don't email me before events
    avatar_updated  TEXT,                          -- when the profile picture changed (NULL = none yet)
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One row per (user, sport) instead of one column per sport,
-- so adding a new sport never needs a database change.
CREATE TABLE IF NOT EXISTS user_sports (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sport   TEXT NOT NULL,
    PRIMARY KEY (user_id, sport)
);

-- Profile pictures: small square JPEGs (256x256), stored in the database so they
-- survive redeploys just like everything else.
CREATE TABLE IF NOT EXISTS avatars (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    image   BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    host_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    sport         TEXT NOT NULL,
    location      TEXT NOT NULL,
    starts_at     TEXT NOT NULL,                   -- YYYY-MM-DD HH:MM, Seattle time
    ends_at       TEXT NOT NULL,
    skill_level   TEXT NOT NULL,
    max_players   INTEGER,                         -- NULL = no limit (includes the host)
    extra_players INTEGER NOT NULL DEFAULT 0,      -- people already playing who aren't on the app
    note          TEXT NOT NULL DEFAULT '',
    is_quick      INTEGER NOT NULL DEFAULT 0,      -- 1 = "Need players" quick post
    cancelled     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_starts_at ON events(starts_at);

CREATE TABLE IF NOT EXISTS rsvps (
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),  -- the app always passes Seattle time
    reminder_sent INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, user_id)
);
