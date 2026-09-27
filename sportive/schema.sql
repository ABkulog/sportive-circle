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
    showcase        TEXT,                          -- up to 3 badge keys shown on the profile, comma-separated
    show_ranks      INTEGER NOT NULL DEFAULT 1,    -- 0 = chill mode (ranks hidden from others)
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
    tryout_spots  INTEGER NOT NULL DEFAULT 0,      -- spots lower-ranked players can take to prove themselves
    allow_plus_ones INTEGER NOT NULL DEFAULT 1,    -- ranked players may bring one friend (+1)
    club_id       INTEGER REFERENCES clubs(id) ON DELETE SET NULL,  -- a club's event (always all levels)
    cancelled     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_starts_at ON events(starts_at);

CREATE TABLE IF NOT EXISTS rsvps (
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),  -- the app always passes Seattle time
    reminder_sent INTEGER NOT NULL DEFAULT 0,
    is_tryout     INTEGER NOT NULL DEFAULT 0,      -- joined through a tryout spot
    plus_one_of   INTEGER REFERENCES users(id) ON DELETE SET NULL,  -- joined as this friend's +1
    PRIMARY KEY (event_id, user_id)
);

-- ---------------------------------------------------------------- ranks & badges
-- 🤝 Props: after a game, players give each other props (once per person per game).
CREATE TABLE IF NOT EXISTS props (
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    giver_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (event_id, giver_id, receiver_id)
);

-- ⬆️ Vouches: "they're ready for the next level" in a sport (once per person per sport).
CREATE TABLE IF NOT EXISTS vouches (
    sport       TEXT NOT NULL,
    giver_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (sport, giver_id, receiver_id)
);

-- Badges are saved when earned, so they (and the date) stay forever, even limited ones.
CREATE TABLE IF NOT EXISTS user_badges (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge     TEXT NOT NULL,
    earned_at TEXT NOT NULL,
    PRIMARY KEY (user_id, badge)
);

-- The last rank each person has seen per sport, to celebrate rank-ups.
CREATE TABLE IF NOT EXISTS ranks_seen (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sport   TEXT NOT NULL,
    level   INTEGER NOT NULL,
    PRIMARY KEY (user_id, sport)
);

-- ---------------------------------------------------------------- social
-- Friend requests. status: 'pending' until the other person accepts.
CREATE TABLE IF NOT EXISTS friendships (
    requester_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    addressee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    PRIMARY KEY (requester_id, addressee_id)
);

-- Blocking: the blocked person can't message you or send you friend requests.
CREATE TABLE IF NOT EXISTS blocks (
    blocker_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (blocker_id, blocked_id)
);

-- Direct messages between two people.
CREATE TABLE IF NOT EXISTS direct_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    read_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_dm_pair ON direct_messages(sender_id, recipient_id, id);
CREATE INDEX IF NOT EXISTS idx_dm_unread ON direct_messages(recipient_id, read_at);

-- Group chat for each event (everyone going can read and post).
CREATE TABLE IF NOT EXISTS event_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    sender_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_messages ON event_messages(event_id, id);

-- The last event-chat message each person has seen (for unread dots).
CREATE TABLE IF NOT EXISTS event_chat_seen (
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    last_id  INTEGER NOT NULL,
    PRIMARY KEY (event_id, user_id)
);

-- "Bring a friend": a ranked player invites one friend (+1) into a ranked game.
CREATE TABLE IF NOT EXISTS plus_one_invites (
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    sponsor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    guest_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (event_id, guest_id)
);

-- ---------------------------------------------------------------- clubs
-- Clubs are open to everyone: anyone can browse them, any member can join. No ranks here.
CREATE TABLE IF NOT EXISTS clubs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    sport       TEXT NOT NULL,
    description TEXT NOT NULL,
    meets       TEXT NOT NULL DEFAULT '',      -- e.g. "Tuesdays & Thursdays, 7-9 PM"
    location    TEXT NOT NULL DEFAULT '',
    contact_url TEXT NOT NULL DEFAULT '',      -- website, Discord... (https only)
    status           TEXT NOT NULL DEFAULT 'pending',  -- 'pending' until an admin approves it, then 'approved' (or 'rejected')
    club_kind        TEXT NOT NULL DEFAULT '',  -- 'rec_club' (UW Recreation Rec Club) or 'rso' (Registered Student Organization)
    verification_url TEXT NOT NULL DEFAULT '',  -- official HuskyLink or UW Recreation page, checked by an admin
    officer_role     TEXT NOT NULL DEFAULT '',  -- the applicant's role, e.g. President
    member_estimate  INTEGER NOT NULL DEFAULT 0,  -- roughly how many active members
    focus            TEXT NOT NULL DEFAULT '',  -- competitive / recreational / instructional / mixed (UW Rec's categories)
    joining          TEXT NOT NULL DEFAULT 'open',  -- open / tryouts / application
    experience       TEXT NOT NULL DEFAULT 'none',  -- none / some / experienced
    who_can_join     TEXT NOT NULL DEFAULT 'everyone',  -- everyone / women / men / women_nb
    dues             TEXT NOT NULL DEFAULT '',  -- 'Free' or e.g. '$40/quarter'
    gear             TEXT NOT NULL DEFAULT '',  -- e.g. 'Provided' or 'Bring cleats'
    competes         INTEGER NOT NULL DEFAULT 0,  -- 1 = plays other schools
    how_to_join      TEXT NOT NULL DEFAULT '',  -- first steps for new members
    club_email       TEXT NOT NULL DEFAULT '',
    instagram        TEXT NOT NULL DEFAULT '',  -- handle without the @
    review_note      TEXT NOT NULL DEFAULT '',  -- admin's note (e.g. why it was rejected)
    reviewed_at      TEXT,
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL
);

-- role: 'officer' (can edit the club, post announcements, create club events) or 'member'
CREATE TABLE IF NOT EXISTS club_members (
    club_id   INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role      TEXT NOT NULL DEFAULT 'member',
    joined_at TEXT NOT NULL,
    PRIMARY KEY (club_id, user_id)
);

-- Announcements from club officers.
CREATE TABLE IF NOT EXISTS club_posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    club_id    INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
    author_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_club_posts ON club_posts(club_id, id);

-- ---------------------------------------------------------------- reports
-- Reports from students about people or messages. Only admins can see these.
-- `snapshot` keeps a copy of the reported message, so the evidence stays even if it's deleted.
CREATE TABLE IF NOT EXISTS reports (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reported_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    target_type      TEXT NOT NULL,             -- 'user', 'dm' or 'event_message'
    target_id        INTEGER NOT NULL,
    reason           TEXT NOT NULL,
    details          TEXT NOT NULL DEFAULT '',
    snapshot         TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'open',   -- 'open', 'reviewed' or 'dismissed'
    created_at       TEXT NOT NULL,
    reviewed_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, id);
