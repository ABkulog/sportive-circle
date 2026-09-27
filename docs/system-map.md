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
        BP["Blueprints<br/>auth · events · profile · social<br/>clubs · moderation · news · pages"]
        LOGIC["Logic<br/>ranks · badges · spirit · photos<br/>timeutil · links · mail"]
        HDR["After every request:<br/>security headers (CSP...)"]
        CLI["Scheduled commands<br/>send-reminders · sport-stats"]
    end

    DB[("SQLite database<br/>schema.sql")]
    SMTP["Email provider (SMTP)"]
    GH["GoHuskies.com RSS"]
    OSM["OpenStreetMap tiles + cdnjs (Leaflet)"]
    MAPS["Google / Apple Maps"]

    UI -- "HTTPS pages + forms" --> MW --> BP --> LOGIC
    BP --> HDR --> UI
    JS -- "chat polling (JSON)" --> BP
    LOGIC --> DB
    CLI --> DB
    LOGIC -- "codes, reminders, club notices" --> SMTP
    BP -- "headlines (cached 30 min)" --> GH
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
| `sportive/constants.py` | Sports, campus places, map pins, player caps. **Edit this to add a sport or place.** |
| `sportive/schema.sql`, `db.py` | Database tables and automatic upgrades for existing databases. |
| `sportive/auth.py` | Sign up, email codes, log in/out, forgot password, CSRF. |
| `sportive/events.py` | Feed, events, Need players, joining, props, vouches, +1s, tryouts, calendar files. |
| `sportive/ranks.py`, `badges.py` | Rank math and badges. |
| `sportive/clubs.py` | Club directory, registration, membership, updates, admin review. |
| `sportive/social.py` | Friends, name search, blocking, direct messages, event chats. |
| `sportive/profile.py` | Profiles, photos, badge locker, settings, change password, delete account. |
| `sportive/moderation.py` | Reports and the admin page (review, suspend). |
| `sportive/news.py` | GoHuskies headlines. |
| `sportive/pages.py` | How it works, Privacy, Terms, the Create menu. |
| `sportive/reminders.py`, `stats.py` | Commands run on a schedule. |
| `sportive/templates/` | Pages. `base.html` has the navigation; `_macros.html` has shared pieces. |
| `sportive/static/` | Stylesheet, icons, and the small scripts. |
| `tests/` | Unit tests (`test_app.py`) and Gherkin scenarios (`features/*.feature`). |

## 3. Screen map

The same five tabs everywhere: a bottom bar on phones and a sidebar on laptops.

```mermaid
flowchart TB
    Landing["Landing (logged out)"] --> Signup["Sign up"] --> Verify["Email code"] --> Photo["Add photo<br/>(or Add later)"] --> How["How it works"]
    Landing --> Login["Log in"] --> Forgot["Forgot password"] --> Reset["Code + new password"]
    Landing --> ClubsPublic["Clubs (browse without an account)"]

    subgraph Tabs["Main tabs"]
        Home["🏠 Home<br/>For you · My events"]
        Clubs["🏛️ Clubs<br/>Find clubs · Updates"]
        Create["➕ Create"]
        News["📰 News"]
        Profile["👤 Profile"]
    end
    How --> Home

    Home --> Event["Event page<br/>join · map · share · calendar"]
    Event --> Chat["Group chat"]
    Event --> Edit["Edit / cancel (host)"]
    Create --> Quick["Need players"]
    Create --> NewEvent["New event"]
    Create --> RegisterClub["Register a club (5 steps)"]
    Clubs --> Club["Club page<br/>About · Updates · Events · Members"]
    Club --> Join["Follow / request / tryouts"]
    Profile --> EditProfile["Edit profile<br/>photo · sports · password · log out · delete"]
    Profile --> Locker["Badge locker"]

    TopIcons["Top icons: ❓ How it works · 👥 Friends · ✉️ Messages"]
    TopIcons --> Friends["Friends<br/>search by name · requests"]
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
    users ||--o{ props : "gives/gets"
    users ||--o{ vouches : "gives/gets"
    users ||--o{ user_badges : earns
    users ||--o{ ranks_seen : "last seen rank"
    users ||--o{ friendships : "requests/accepts"
    users ||--o{ blocks : blocks
    users ||--o{ direct_messages : "sends/receives"
    events ||--o{ plus_one_invites : "+1 invites"
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
        int show_ranks "0 = chill mode"
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
    }
    clubs {
        int id PK
        text name UK
        text status "pending / approved / rejected"
        text verification_url "HuskyLink or UW Rec"
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
    A->>A: Logged in? Game not canceled or over? Rank allows it (or tryout / +1)?
    A->>D: INSERT rsvp ... WHERE going + extra < max_players (one statement)
    alt a spot was free
        D-->>A: 1 row
        A-->>S: "You're in!" + confetti, warns about time clashes
    else someone took the last spot first
        D-->>A: 0 rows
        A-->>S: "Sorry, this event is full"
    end
```

### Club verification

```mermaid
stateDiagram-v2
    [*] --> pending: officer registers (official page + all details)
    pending --> approved: admin checks HuskyLink / UW Rec
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
    Cron["Scheduler every 10 min"] -- "flask send-reminders" --> Host
```

See [deployment.md](deployment.md) for step-by-step instructions.
