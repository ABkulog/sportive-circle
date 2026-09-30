# Sportive Circle @ UW: System map

How the pieces fit together. The diagrams are [Mermaid](https://mermaid.js.org/), which GitHub
draws automatically.

## 1. Architecture

```mermaid
flowchart LR
    subgraph Phone["Student's phone or laptop (browser)"]
        UI["Pages (HTML + CSS)"]
        JS["Small scripts: app.js, map.js, chat.js, forms.js, wizard.js, tabs.js"]
        GPS["Location (Where am I?)<br/>stays in the browser"]
    end

    subgraph Server["Flask app (Python)"]
        direction TB
        MW["Before every request:<br/>CSRF check · load user · photo check"]
        BP["Blueprints<br/>auth · events · parties · profile · social<br/>clubs · moderation · notifications · feedback · pages"]
        LOGIC["Logic<br/>invites · badges · spirit · photos<br/>timeutil · links · mail"]
        HDR["After every request:<br/>security headers (CSP...)"]
        CLI["Scheduled commands<br/>send-reminders · sport-stats"]
    end

    DB[("SQLite database<br/>schema.sql")]
    SMTP["Email provider (SMTP)"]
    OSM["OpenStreetMap tiles + cdnjs (Leaflet)"]
    MAPS["Google / Apple Maps"]

    UI -- "HTTPS pages + forms" --> MW --> BP --> LOGIC
    BP --> HDR --> UI
    JS -- "chat polling (JSON)" --> BP
    LOGIC --> DB
    CLI --> DB
    LOGIC -- "codes, reminders, game changes, club notices" --> SMTP
    JS -- "map images" --> OSM
    UI -- "Directions link" --> MAPS
    GPS -.-> JS
```

**Why this shape?** Server-rendered pages work on any phone, need no app store, and keep the code
small enough for one student to maintain. Each area of the app is its own module (a Flask
*blueprint*), so a change to clubs can't break messaging.

## 2. Code map

| File | What it does |
|---|---|
| `sportive/__init__.py` | Builds the app: settings, blueprints, error pages, security headers. |
| `sportive/constants.py` | Sports, campus places, map pins, usual game sizes. **Edit this to add a sport or place.** |
| `sportive/schema.sql`, `db.py` | Database tables and automatic upgrades for existing databases. |
| `sportive/auth.py` | Sign up, email codes, log in/out, forgot password, CSRF. |
| `sportive/events.py` | Feed and filters, events (private, team vs team), Need players, joining, change notices, calendar files. |
| `sportive/invites.py`, `parties.py` | Invites and held spots (30 min), Party up, "You down?", host approval in private games, team challenges. |
| `sportive/notifications.py` | Tab numbers, the bell, notices (invites, game changes), notification settings. |
| `sportive/badges.py` | Badges (earned, seasonal, and given ones like Tester). |
| `sportive/clubs.py` | Club directory, registration, membership, updates, admin review. |
| `sportive/social.py` | Friends, name/NetID search, blocking, direct messages, event chats. |
| `sportive/profile.py` | Profiles (pronouns, gender, socials), photos, badge locker, settings, change password, delete account. |
| `sportive/moderation.py` | Reports and the admin page (review, suspend). |
| `sportive/feedback.py` | Suggestions and trending topics for admins. |
| `sportive/pages.py` | How it works, FAQ, Privacy, Terms, the Create menu. |
| `sportive/sms.py`, `phones.py`, `announcements.py` | Texts (Twilio): codes, limits, updates; phone numbers with a country picker; the one-time "texts are here" announcement. |
| `sportive/placecheck.py` | "What else is on at this place?": UW Rec reservations (and the admin page to add them) and other games. |
| `sportive/settings.py` | Settings pages: notifications, look (theme), reminders, texts, password, blocked people. |
| `sportive/photos.py` | Profile photos and club logos: cropped, resized, hidden info removed. |
| `sportive/spirit.py` | The Home greeting and Top Dawgs. |
| `sportive/mail.py`, `links.py` | Sending email; full links to the live site for emails, calendar files and share buttons. |
| `sportive/timeutil.py`, `textutil.py` | Seattle time and "5 min ago" style times; cleaning up typed text. |
| `sportive/reminders.py`, `stats.py` | Game reminders (a loop inside the app on Render, or `/tasks/send-reminders`) and usage stats. |
| `sportive/templates/` | Pages. `base.html` has the navigation; `_macros.html` has shared pieces. |
| `sportive/static/` | Stylesheet, icons, and the small scripts. |
| `tests/` | Unit tests (`test_app.py`) and Gherkin scenarios (`features/*.feature`). |

## 3. Screen map

The same four tabs everywhere: a bottom bar on phones and a sidebar on laptops.

```mermaid
flowchart TB
    Landing["Landing (logged out)"] --> Signup["Sign up"] --> Verify["Email code<br/>resend countdown"] --> Photo["Add photo<br/>(or Add later → pop-up)"] --> Home
    Landing --> Login["Log in"] --> Forgot["Forgot password"] --> Reset["Code + new password"]
    Landing --> ClubsPublic["Clubs (browse without an account)"]

    subgraph Tabs["Main tabs"]
        Home["🏠 Home<br/>For you · My events"]
        Clubs["🏛️ Clubs<br/>Find clubs · Updates"]
        Create["➕ Create"]
        Profile["👤 Profile"]
    end

    Home --> Event["Event page<br/>join (password if private) · You down? · teams · map · share · calendar"]
    Event --> Chat["Group chat"]
    Event --> Party["Party up / Challenge<br/>pick friends, spots held 30 min"]
    Event --> Edit["Edit / cancel (host)<br/>players get a notice"]
    Create --> Quick["Need players"]
    Create --> NewEvent["New event"]
    Create --> RegisterClub["Register a club (5 steps)"]
    Clubs --> Club["Club page<br/>About · Updates · Events · Members"]
    Club --> Join["Follow / request / tryouts"]
    Profile --> EditProfile["Edit profile<br/>photo · sports · password · log out · delete"]
    Profile --> Locker["Badge locker"]

    TopIcons["Top icons: ❓ FAQ · 🔔 Bell · 👥 Friends · ✉️ Messages"]
    TopIcons --> FAQ["FAQ"]
    TopIcons --> Bell["Notifications<br/>invites · game changes · new messages"]
    TopIcons --> Friends["Friends<br/>search by name or NetID · requests"]
    TopIcons --> Inbox["Messages"] --> Thread["Conversation"]
    Thread --> Report["Report"]
    Admin["🛡️ Admin (only ADMIN_EMAILS)"] --> Reports["Reports + suspend"]
    Admin --> ClubReview["Club requests"]
```

## 4. Data model

```mermaid
erDiagram
    users ||--o{ user_sports : likes
    users ||--o| avatars : has
    users ||--o{ events : hosts
    users ||--o{ rsvps : joins
    events ||--o{ rsvps : has
    events ||--o{ event_messages : chat
    users ||--o{ user_badges : earns
    events ||--o{ invites : "held spots"
    users ||--o{ invites : "invites / is invited"
    users ||--o{ notices : "bell"
    users ||--o{ friendships : "requests/accepts"
    users ||--o{ blocks : blocks
    users ||--o{ direct_messages : "sends/receives"
    clubs ||--o{ club_members : "followers, waiting, members, officers"
    users ||--o{ club_members : "is in"
    clubs ||--o{ club_posts : posts
    clubs ||--o{ events : "club events"
    users ||--o{ reports : "reports / is reported"

    users {
        int id PK
        text email UK "must be UW"
        text password_hash
        text full_name
        int grad_year
        text birth_date
        int verified
        int suspended
        text pronouns "optional"
        text instagram "optional socials"
    }
    events {
        int id PK
        int host_id FK
        text sport
        text location
        text starts_at "Seattle time"
        text ends_at
        text skill_level
        int max_players
        int is_quick "Need players"
        int cancelled
        int club_id FK
        int is_private
        text password "private games"
        int team_size "team vs team"
    }
    invites {
        int id PK
        int event_id FK
        int inviter_id FK
        int guest_id FK
        int team
        text status "pending / requested / accepted / declined / canceled"
        text expires_at "spot held until"
        text note "for the host"
    }
    clubs {
        int id PK
        text name UK
        text status "pending / approved / rejected"
        text verification_url "old: HuskyLink or UW Rec (no longer asked)"
        text joining "open / tryouts / application"
    }
    club_members {
        int club_id PK
        int user_id PK
        text role "follower / requested / tryout / member / officer"
    }
```

Times are stored as Seattle local time (`YYYY-MM-DD HH:MM`), which sorts correctly as text.
Deleting a user cascades to their data; reports and club posts keep the text with the name removed.

## 5. Key flows

### Joining a game (without overbooking)

```mermaid
sequenceDiagram
    actor S as Student
    participant A as Flask app
    participant D as Database
    S->>A: POST /events/7/join (with CSRF token)
    A->>A: Logged in? Game not canceled or over? Private: invited or right password? Team game: invited?
    A->>D: INSERT rsvp ... WHERE going + extra + spots held for others < max_players (and team not full), one statement
    alt a spot was free
        D-->>A: 1 row
        A-->>S: "You're in!" + confetti, warns about time clashes
    else someone took the last spot first
        D-->>A: 0 rows
        A-->>S: "Sorry, this game is full"
    end
```

### Party up (playing with friends)

```mermaid
sequenceDiagram
    actor M as Maya (player)
    participant A as Flask app
    participant D as Database
    actor J as Jordan (friend)
    M->>A: Party up: pick Jordan and Sam
    A->>D: BEGIN IMMEDIATE (lock)
    A->>D: enough room for Maya (if not in yet) + 2? then add Maya, invites held 30 min
    A->>D: COMMIT
    A-->>J: 🔔 "Maya wants you in Sunday hoops. You down?"
    alt I'm in
        J->>A: yes → takes the held spot
        A-->>M: 🔔 "Jordan is in"
    else Can't make it
        J->>A: no → spot free for anyone
        A-->>M: 🔔 "Jordan can't make it"
    else no answer in 30 min
        Note over D: the hold ends by itself; the invite still works if there's room
    end
```

In a private game, friends that a player (not the host) brings start as *requests* with a note; the
host approves (then the spot is held) or declines. In team vs team, the host's party is team 1 and a
second group claims team 2 with the same flow ("Challenge").

### Club verification

```mermaid
stateDiagram-v2
    [*] --> pending: officer registers (official page + all details)
    pending --> approved: admin checks its social accounts
    pending --> rejected: admin sends a note
    rejected --> pending: officer fixes and resubmits
    approved --> pending: name or official page changes
    approved --> [*]
```

### Becoming a club member

```mermaid
stateDiagram-v2
    [*] --> follower: Follow
    [*] --> requested: Request to join / Apply
    [*] --> tryout: Sign up for tryouts
    follower --> requested
    follower --> tryout
    requested --> member: officer confirms
    tryout --> member: officer marks "made the team"
    requested --> follower: officer declines (kind message sent)
    tryout --> follower: "not this time"
    member --> officer: an officer promotes them
    member --> [*]: leaves or is removed
```

### "Where am I?"

```mermaid
flowchart TD
    T["Tap Where am I?"] --> SC{"Secure page (https)?"}
    SC -- no --> M1["Say: needs https, use Directions"]
    SC -- yes --> P["Ask the browser for precise location (8 s)"]
    P -- got it --> D["Blue dot + distance + walking time"]
    P -- blocked --> H["Show steps to turn it on for this device<br/>(iPhone / Mac Safari / Android / other)"]
    P -- timed out / unavailable --> R["Retry with rough Wi-Fi location (15 s)"]
    R -- got it --> D
    R -- failed --> F["Say: try outside, or tap Directions"]
    D --> N["Location never sent to the server"]
```

## 6. Deployment

```mermaid
flowchart LR
    Dev["Your laptop<br/>python main.py"] -- git push --> GH["GitHub<br/>tests run in Actions"]
    GH -- deploy --> Host["Host (e.g. Render / Railway / Fly.io)<br/>gunicorn wsgi:app<br/>BEHIND_PROXY=1"]
    Host --- Disk[("Persistent disk:<br/>sportive_circle.db")]
    Host -- "every 5 min: reminder emails" --> Host
```

See [deployment.md](deployment.md) for step-by-step instructions.
