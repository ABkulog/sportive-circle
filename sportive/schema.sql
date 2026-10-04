-- Sportive Circle @ UW database schema.
-- Every statement is "IF NOT EXISTS", so this runs safely on every startup.

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,          -- must be @uw.edu
    password_hash   TEXT NOT NULL,                 -- never the plain password
    full_name       TEXT NOT NULL,
    grad_year       INTEGER,
    birth_date      TEXT,                          -- YYYY-MM-DD (age check, birthday greeting)
    bio             TEXT NOT NULL DEFAULT '',
    pronouns        TEXT NOT NULL DEFAULT '',      -- optional, e.g. "she/her"
    gender          TEXT NOT NULL DEFAULT '',      -- optional: '' / woman / man / nonbinary / other (profile.GENDERS)
    instagram       TEXT NOT NULL DEFAULT '',      -- optional socials: usernames without the @
    snapchat        TEXT NOT NULL DEFAULT '',
    tiktok          TEXT NOT NULL DEFAULT '',
    x_handle        TEXT NOT NULL DEFAULT '',
    linkedin        TEXT NOT NULL DEFAULT '',      -- the part after linkedin.com/in/
    phone           TEXT NOT NULL DEFAULT '',      -- optional, for texts: +12065550142 (sms.py)
    phone_verified  INTEGER NOT NULL DEFAULT 0,    -- 1 once they typed the code we texted
    sms_updates     INTEGER NOT NULL DEFAULT 0,    -- 1 = they said yes to texts (and can turn it off)
    sms_consent_at  TEXT,                          -- when they said yes
    sms_code        TEXT,
    sms_code_expires TEXT,
    sms_code_attempts INTEGER NOT NULL DEFAULT 0,
    sms_sent_at     TEXT,
    texts_card_done INTEGER NOT NULL DEFAULT 0,    -- 1 = closed the "New: texts" card on Home
    texts_announced_at TEXT,                       -- when tools/announce_texts.py emailed them about texts
    verified        INTEGER NOT NULL DEFAULT 0,    -- 1 once the email code is confirmed
    verify_code     TEXT,                          -- 6-digit code for signing up or resetting a password
    verify_expires  TEXT,
    verify_attempts INTEGER NOT NULL DEFAULT 0,
    verify_sent_at  TEXT,                          -- for the "wait before resending" limit
    failed_logins   INTEGER NOT NULL DEFAULT 0,    -- wrong passwords in a row
    locked_until    TEXT,                          -- set after too many wrong passwords
    email_reminders INTEGER NOT NULL DEFAULT 1,    -- 0 = don't email me before events
    email_friend_games INTEGER NOT NULL DEFAULT 1, -- 0 = don't email me when friends/my clubs post a game
    avatar_updated  TEXT,                          -- when the profile picture changed (NULL = none yet)
    showcase        TEXT,                          -- up to 3 badge keys shown on the profile, comma-separated
    photo_skipped   INTEGER NOT NULL DEFAULT 0,    -- 1 = chose "Add later" (don't ask again)
    theme           TEXT NOT NULL DEFAULT 'light', -- light / dark / system (settings.THEMES)
    suspended       INTEGER NOT NULL DEFAULT 0,    -- 1 = an admin suspended the account (can't log in)
    session_version INTEGER NOT NULL DEFAULT 0,    -- +1 = every logged-in device is logged out (password change)
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))  -- UTC, unlike the rest: read with timeutil.from_sqlite_utc
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
    revision      INTEGER NOT NULL DEFAULT 0,  -- +1 on every edit or cancel (calendar files' SEQUENCE)
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
    club_id       INTEGER REFERENCES clubs(id) ON DELETE SET NULL,  -- a club's event (always all levels)
    is_private    INTEGER NOT NULL DEFAULT 0,      -- 1 = joining needs the password (or an invite)
    password      TEXT NOT NULL DEFAULT '',        -- a private game's password, shown to the host and players
    team_size     INTEGER,                         -- team vs team: players per team (NULL = a regular game)
    open_to       TEXT NOT NULL DEFAULT 'everyone', -- everyone / women / men / nonbinary (constants.OPEN_TO; older games: women_nb)
    members_only  INTEGER NOT NULL DEFAULT 0,      -- a club event only its members can join
    cancelled     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))  -- UTC: compare with SQLite's datetime('now', ...)
);

CREATE INDEX IF NOT EXISTS idx_events_starts_at ON events(starts_at);

CREATE TABLE IF NOT EXISTS rsvps (
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),  -- the app always passes Seattle time
    reminder_sent INTEGER NOT NULL DEFAULT 0,
    team          INTEGER,                         -- team vs team: 1 = the host's team, 2 = the challengers
    remind_minutes INTEGER NOT NULL DEFAULT 60,    -- reminder email this many minutes before (0 = none)
    PRIMARY KEY (event_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_rsvps_user ON rsvps(user_id);

-- People a host took off their game. They can't join it again by themselves (the host can still invite them).
CREATE TABLE IF NOT EXISTS removed_players (
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    removed_at TEXT NOT NULL,
    PRIMARY KEY (event_id, user_id)
);

-- Invites to a game, from anyone going (a "party"). While `expires_at` hasn't passed, a pending invite
-- holds a spot for that friend, so a group can join together without strangers taking their spots.
-- After that the invite still works if there's room. status: pending / accepted / declined / canceled,
-- or 'requested': in a private game, a player who isn't the host asked to bring a friend (with a note),
-- and the host hasn't said yes yet (nothing is held until they do).
CREATE TABLE IF NOT EXISTS invites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    inviter_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    guest_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team        INTEGER,                        -- team vs team: which team the spot is on
    status      TEXT NOT NULL DEFAULT 'pending',
    note        TEXT NOT NULL DEFAULT '',       -- "this is my roommate", for the host of a private game
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,                  -- the held spot is free again after this
    UNIQUE (event_id, guest_id)
);
CREATE INDEX IF NOT EXISTS idx_invites_event ON invites(event_id, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_invites_guest ON invites(guest_id, status);

-- Wrong passwords for private games, so nobody can guess one by trying thousands.
CREATE TABLE IF NOT EXISTS password_tries (
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tries      INTEGER NOT NULL DEFAULT 0,
    first_try  TEXT NOT NULL,
    PRIMARY KEY (event_id, user_id)
);

-- ---------------------------------------------------------------- badges
-- Badges are saved when earned, so they (and the date) stay forever, even limited ones.
CREATE TABLE IF NOT EXISTS user_badges (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge     TEXT NOT NULL,
    earned_at TEXT NOT NULL,
    PRIMARY KEY (user_id, badge)
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

CREATE INDEX IF NOT EXISTS idx_friendships_addressee ON friendships(addressee_id, status);

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
    read_at      TEXT,
    event_id     INTEGER REFERENCES events(id) ON DELETE SET NULL,  -- a game shared with "Send to friends"
    photo_id     INTEGER REFERENCES chat_photos(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_dm_pair ON direct_messages(sender_id, recipient_id, id);
CREATE INDEX IF NOT EXISTS idx_dm_unread ON direct_messages(recipient_id, read_at);

-- Group chat for each event (everyone going can read and post).
CREATE TABLE IF NOT EXISTS event_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    sender_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    photo_id   INTEGER REFERENCES chat_photos(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_event_messages ON event_messages(event_id, id);

-- The last event-chat message each person has seen (for unread dots).
CREATE TABLE IF NOT EXISTS event_chat_seen (
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    last_id  INTEGER NOT NULL,
    PRIMARY KEY (event_id, user_id)
);

-- ---------------------------------------------------------------- clubs
-- Verified UW clubs. Anyone can browse approved clubs; officers confirm who becomes a member.
CREATE TABLE IF NOT EXISTS clubs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    sport       TEXT NOT NULL,
    description TEXT NOT NULL,
    meets       TEXT NOT NULL DEFAULT '',      -- e.g. "Tuesdays & Thursdays, 7-9 PM"
    location    TEXT NOT NULL DEFAULT '',
    contact_url TEXT NOT NULL DEFAULT '',      -- website, Discord... (https only)
    status           TEXT NOT NULL DEFAULT 'pending',  -- 'pending' until an admin approves it, then 'approved' ('rejected' = sent back, 'denied' = spam)
    club_kind        TEXT NOT NULL DEFAULT '',  -- 'rec_club' (UW Recreation Rec Club) or 'rso' (Registered Student Organization)
    verification_url TEXT NOT NULL DEFAULT '',  -- no longer asked (clubs are checked through their socials); kept for old clubs
    contact_phone    TEXT NOT NULL DEFAULT '',  -- the applicant's phone, +12065550142: only admins see it
    officer_role     TEXT NOT NULL DEFAULT '',  -- the applicant's role, e.g. President
    member_estimate  INTEGER NOT NULL DEFAULT 0,  -- roughly how many active members
    focus            TEXT NOT NULL DEFAULT '',  -- competitive / recreational / instructional / mixed (UW Rec's categories)
    joining          TEXT NOT NULL DEFAULT 'open',  -- open / tryouts / application
    experience       TEXT NOT NULL DEFAULT 'none',  -- none / some / experienced
    who_can_join     TEXT NOT NULL DEFAULT 'everyone',  -- everyone / women / men / nonbinary (older: women_nb)
    dues             TEXT NOT NULL DEFAULT '',  -- 'Free' or e.g. '$40/quarter'
    gear             TEXT NOT NULL DEFAULT '',  -- e.g. 'Provided' or 'Bring cleats'
    competes         INTEGER NOT NULL DEFAULT 0,  -- 1 = plays other schools
    how_to_join      TEXT NOT NULL DEFAULT '',  -- first steps for new members
    join_question    TEXT NOT NULL DEFAULT '',  -- asked to people who want to join, e.g. "What position do you play?"
    tiktok           TEXT NOT NULL DEFAULT '',  -- optional socials (handles/usernames, or page links for FB/YouTube)
    snapchat         TEXT NOT NULL DEFAULT '',
    x_handle         TEXT NOT NULL DEFAULT '',
    facebook         TEXT NOT NULL DEFAULT '',
    youtube          TEXT NOT NULL DEFAULT '',
    club_email       TEXT NOT NULL DEFAULT '',
    instagram        TEXT NOT NULL DEFAULT '',  -- handle without the @
    logo_updated     TEXT,                      -- when the officers last changed the club's logo (NULL = none)
    review_note      TEXT NOT NULL DEFAULT '',  -- admin's note (e.g. why it was rejected)
    reviewed_at      TEXT,
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL
);

-- Club logos: 256x256 JPEGs (like profile pictures), uploaded by officers.
CREATE TABLE IF NOT EXISTS club_logos (
    club_id INTEGER PRIMARY KEY REFERENCES clubs(id) ON DELETE CASCADE,
    image   BLOB NOT NULL
);

-- role:
--   'follower'  - following the club (announcements & events), NOT a member
--   'requested' - asked to join; waiting for an officer to confirm
--   'tryout'    - signed up for tryouts; an officer marks the result
--   'member'    - confirmed by an officer
--   'officer'   - can edit the club, post announcements, create club events, confirm members
CREATE TABLE IF NOT EXISTS club_members (
    club_id   INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role      TEXT NOT NULL DEFAULT 'member',
    message   TEXT NOT NULL DEFAULT '',     -- their answer to the club's join question
    joined_at TEXT NOT NULL,
    PRIMARY KEY (club_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_club_members_user ON club_members(user_id);

-- Announcements from club officers.
CREATE TABLE IF NOT EXISTS club_posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    club_id    INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
    author_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    event_id   INTEGER REFERENCES events(id) ON DELETE SET NULL  -- posted automatically for a new club event
);
CREATE INDEX IF NOT EXISTS idx_club_posts ON club_posts(club_id, id);

-- ---------------------------------------------------------------- notifications
-- Which notifications each person wants on their tab icons and on their screen. Only changes from
-- the defaults (in notifications.py) are stored.
CREATE TABLE IF NOT EXISTS notification_settings (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind    TEXT NOT NULL,
    badge   INTEGER NOT NULL,   -- 1 = show a number on the tab icon
    screen  INTEGER NOT NULL,   -- 1 = show it in the bell
    PRIMARY KEY (user_id, kind)
);

-- When someone last looked at each place (the newest club post id, news time...), so only newer
-- things count as new.
CREATE TABLE IF NOT EXISTS seen_markers (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind    TEXT NOT NULL,
    value   TEXT NOT NULL,
    PRIMARY KEY (user_id, kind)
);

-- One-off notices for one person, shown in their bell: "Maya changed the time of Sunday soccer",
-- invites, "Add a profile photo". kind is one of notifications.NOTICE_KINDS.
CREATE TABLE IF NOT EXISTS notices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    text       TEXT NOT NULL,
    url        TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at    TEXT,
    key        TEXT                   -- a newer notice with the same key replaces the older one
);
CREATE INDEX IF NOT EXISTS idx_notices_user ON notices(user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_notices_recent ON notices(user_id, created_at);  -- the bell: newest first

-- ---------------------------------------------------------------- suggestions
-- Ideas and problems people send from the footer link. Only admins can read them.
-- anonymous = 1: admins don't see who sent it (user_id is kept only for the hourly limit).
CREATE TABLE IF NOT EXISTS suggestions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    anonymous  INTEGER NOT NULL DEFAULT 0,
    kind       TEXT NOT NULL,              -- 'idea', 'bug' or 'other'
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_suggestions_user ON suggestions(user_id, created_at);

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

-- Every text we send (or try to), for the per-day limits and troubleshooting.
CREATE TABLE IF NOT EXISTS sms_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE CASCADE,
    phone      TEXT NOT NULL,
    kind       TEXT NOT NULL,        -- 'code' or 'update'
    ok         INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sms_log_user ON sms_log(user_id, created_at);

-- UW Recreation's own reservations (IM leagues, club practices, rentals), copied in by admins from UW Rec's
-- schedule (Admin -> UW Rec). Shown to hosts so they know the courts/field are taken then (placecheck.py).
CREATE TABLE IF NOT EXISTS rec_reservations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    location   TEXT NOT NULL,
    starts_at  TEXT NOT NULL,
    ends_at    TEXT NOT NULL,
    label      TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'admin',   -- 'admin' (typed in) or 'feed' (if UW Rec ever shares one)
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
-- Club pages and the clubs list count each club's upcoming events.
CREATE INDEX IF NOT EXISTS idx_events_club ON events(club_id, ends_at);
CREATE INDEX IF NOT EXISTS idx_rec_reservations ON rec_reservations(location, starts_at);

-- Every email code we send (sign-up and password reset), for the per-day limit: a few codes a day means
-- a few wrong guesses a day, so nobody can guess their way into an account or a UW address.
CREATE TABLE IF NOT EXISTS email_codes (
    inbox   TEXT NOT NULL,           -- the NetID part of the email (netid@uw.edu and @u.washington.edu share it)
    sent_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_email_codes ON email_codes(inbox, sent_at);

-- When we last emailed a club's officers about someone asking to join, so asking, leaving and asking again
-- doesn't flood their inbox (one email per person per club per day; the request still shows in the club).
CREATE TABLE IF NOT EXISTS club_join_emails (
    club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (club_id, user_id)
);

-- Wrong passwords at login, by device address. A lockout only blocks the address the wrong guesses came from,
-- so nobody can lock someone else out of their account by typing wrong passwords for it.
CREATE TABLE IF NOT EXISTS login_failures (
    ip        TEXT NOT NULL,
    email     TEXT NOT NULL,
    failed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_failures ON login_failures(ip, failed_at);

-- Logins that were logged out (the cookie's id), so a copied cookie stops working after "Log out".
CREATE TABLE IF NOT EXISTS ended_sessions (
    sid      TEXT PRIMARY KEY,
    ended_at TEXT NOT NULL
);

-- Feeds and profiles only look at games that haven't ended; without this they'd read every game ever made.
CREATE INDEX IF NOT EXISTS idx_events_ends_at ON events(ends_at);

-- Small bits the app remembers about itself (e.g. when UW Rec's schedule was last copied: uwrec.py).
CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Photos sent in messages and game chats (resized, hidden info removed: photos.make_chat_photo).
CREATE TABLE IF NOT EXISTS chat_photos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    uploader_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    image      BLOB NOT NULL,
    created_at TEXT NOT NULL
);

-- Reactions on chat messages (like WhatsApp): one per person per message. kind: 'dm' or 'game'.
CREATE TABLE IF NOT EXISTS message_reactions (
    kind       TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    emoji      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (kind, message_id, user_id)
);

-- "Maya posted a game" emails sent (friendgames.py): one per person per game, and a daily cap per person.
CREATE TABLE IF NOT EXISTS game_alerts (
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    sent_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, event_id)
);
CREATE INDEX IF NOT EXISTS idx_game_alerts_user ON game_alerts(user_id, sent_at);

-- "Changed: <game>" emails and texts sent, so a host editing over and over can't flood players (events.py).
CREATE TABLE IF NOT EXISTS change_alerts (
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    sent_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_change_alerts ON change_alerts(event_id, user_id, sent_at);
-- Games by host (profiles, "posted a game" limits, the hourly posting limit).
CREATE INDEX IF NOT EXISTS idx_events_host ON events(host_id, created_at);

-- ---------------------------------------------------------------- the feed
-- What students post on the feed: a sport tag, words and/or up to 10 photos. A "plan" post ("hiking Mt Si
-- tomorrow, need 2") is a real game behind the scenes (event_id), so "I'm in" gives it a headcount and a chat.
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sport      TEXT NOT NULL,                       -- the sport tag (constants.SPORTS key)
    body       TEXT NOT NULL DEFAULT '',
    event_id   INTEGER REFERENCES events(id) ON DELETE SET NULL,  -- a plan post's game
    created_at TEXT NOT NULL                        -- Seattle time
);
CREATE INDEX IF NOT EXISTS idx_posts_sport ON posts(sport, id);
CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_id, id);

-- A post's photos, in order (resized, hidden info removed: photos.make_chat_photo).
CREATE TABLE IF NOT EXISTS post_photos (
    post_id  INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,                      -- 1 to 10
    image    BLOB NOT NULL,
    PRIMARY KEY (post_id, position)
);
