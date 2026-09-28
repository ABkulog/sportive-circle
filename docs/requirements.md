# Sportive Circle @ UW: Requirements

What the app must do (functional requirements) and how well it must do it (non-functional
requirements). Every requirement has an ID. The Gherkin scenarios in
[`tests/features/`](../tests/features) are tagged with these IDs (for example `@FR-AUTH-1`), and
`pytest` runs them, so each requirement is checked automatically.

**Status:** ✅ done and tested · 🟡 done, partly tested · ⬜ planned

**Priority:** **Must** (required for launch) · **Should** (important) · **Could** (nice to have)

---

## 1. Users and goals

| User | Goal |
|---|---|
| **Student (Husky)** | Find a game or a club for their sport and level, and show up without awkwardness. |
| **Host** | Fill a game quickly ("need 2 more") or plan one ahead. |
| **Club officer** | Get their verified club found, manage who joins, and post updates. |
| **Admin** | Keep the community safe (reports, suspensions) and only list real, active UW clubs. |

---

## 2. Functional requirements

### Accounts (AUTH)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-AUTH-1 | Only `@uw.edu` or `@u.washington.edu` emails can sign up. | Must | ✅ |
| FR-AUTH-2 | New accounts must confirm their email with a 6-digit code (expires in 15 min, max 5 wrong tries, 60 s between resends). | Must | ✅ |
| FR-AUTH-3 | Users must be 15 or older (checked from date of birth). | Must | ✅ |
| FR-AUTH-4 | Log in with email + password. 10 wrong passwords in a row lock the account for 15 minutes. | Must | ✅ |
| FR-AUTH-5 | "Forgot password?" emails a code to set a new password, and never reveals whether an email has an account. | Must | ✅ |
| FR-AUTH-6 | Logged-in users can change their password (current password required). | Must | ✅ |
| FR-AUTH-7 | Users can delete their account after an "Are you sure?" page, typing DELETE, and their password. A club's only officer must hand over first. | Must | ✅ |
| FR-AUTH-8 | Suspended accounts can't log in. | Must | ✅ |

### Profile (PROF)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-PROF-1 | Every user is asked for a profile photo after signing up ("Add later" allowed; they're reminded). | Must | ✅ |
| FR-PROF-2 | Photos are cropped to a square, shrunk to 256 px, and stripped of hidden metadata (like GPS). | Must | ✅ |
| FR-PROF-3 | Users can edit name, class year, bio, sports, photo, reminder emails and chill mode (hide ranks). Edit and Change photo buttons are on their own profile. | Must | ✅ |
| FR-PROF-4 | A user's email is shown only to themselves and people they've played a game with. | Must | ✅ |
| FR-PROF-5 | On the photo page, Save without picking a new photo goes back to the profile, and users can remove their photo (with an "Are you sure?"). | Should | ✅ |

### Games and events (EVT)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-EVT-1 | Create an event with a name, sport, place, start/end time, level, optional player limit and note. | Must | ✅ |
| FR-EVT-2 | Each sport can only use places where it can really be played (e.g. rowing only at the WAC, pickleball at the IMA courts, IMA Gym B or Green Lake), with good-to-know tips such as court numbers and drop-in hours. | Must | ✅ |
| FR-EVT-3 | Each sport has a player cap (e.g. basketball 10); an event can't exceed it. | Must | ✅ |
| FR-EVT-4 | "Need players": post a game that starts within 2 hours in a few taps; it goes to the top of every feed. | Must | ✅ |
| FR-EVT-5 | Join and leave games. A full game can't be overbooked, even when two people tap Join at once. | Must | ✅ |
| FR-EVT-6 | Games that are over stay in your history: you can't leave them. | Should | ✅ |
| FR-EVT-7 | Hosts can edit or cancel. Canceling emails everyone who joined. | Must | ✅ |
| FR-EVT-8 | The feed shows upcoming games for your sports, with filters for sport, day (today / week / month), place and level. | Must | ✅ |
| FR-EVT-9 | Event pages have a map, walking directions (Google or Apple Maps), "Where am I?" with distance, share, and "Add to calendar" (.ics). | Should | ✅ |
| FR-EVT-10 | "Where am I?" explains how to turn location on when the browser blocks it, retries with rough location if precise location times out, and still works if the map can't load. | Should | ✅ |
| FR-EVT-11 | Everyone going to a game gets an email reminder an hour before (can be turned off). | Should | ✅ |
| FR-EVT-12 | Everyone going to a game can use its group chat. | Should | ✅ |

### Ranks and badges (RANK)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-RANK-1 | Each sport has a rank: Casual → Intermediate → Competitive → Legend. Everyone starts at Casual. | Should | ✅ |
| FR-RANK-2 | Intermediate and Competitive games are only for players at that rank or higher. | Should | ✅ |
| FR-RANK-3 | After a game (for 7 days), players can give teammates 🤝 props and ⬆️ vouches. | Should | ✅ |
| FR-RANK-4 | Tryout spots let lower-ranked players into harder games; 3 vouches from players at a level move you up (placement). | Should | ✅ |
| FR-RANK-5 | Ranked players can bring one friend as a +1 (max 2 per game). | Could | ✅ |
| FR-RANK-6 | Badges are earned by playing; limited (seasonal) badges retire forever. Users pick 3 to show. | Could | ✅ |

### Clubs (CLUB)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-CLUB-1 | Only officers can register a club, with its official HuskyLink or UW Recreation page, and every field filled in except social media. | Must | ✅ |
| FR-CLUB-2 | A club is only public after an admin approves it. Rejections include a note on what to fix. | Must | ✅ |
| FR-CLUB-3 | Anyone (even logged out) can browse verified clubs and search or filter them (sport, beginner-friendly, free, no tryouts). | Must | ✅ |
| FR-CLUB-4 | Students can follow a club, or request to join / apply / sign up for tryouts. They're a member only after an officer confirms them. | Must | ✅ |
| FR-CLUB-5 | Officers can post updates, create club events, confirm or decline people, remove members and add officers. | Must | ✅ |
| FR-CLUB-6 | Students can message a club's officers before joining. | Should | ✅ |

### Friends and messages (SOC)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-SOC-1 | Search for people by name and send a friend request. | Must | ✅ |
| FR-SOC-2 | Accept, decline, cancel requests and unfriend. People you've played with are suggested. | Must | ✅ |
| FR-SOC-3 | Direct messages are allowed only between friends, people who played together, a student and a club officer, or when replying to someone who wrote first. | Must | ✅ |
| FR-SOC-4 | Blocking stops messages, friend requests and joining each other's games, both ways, and hides you from their search and feed. | Must | ✅ |

### Notifications (NOTIF)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-NOTIF-1 | Tabs and icons show how many new things are waiting: messages, friend requests, game chats (Home), club updates and join requests (Clubs), badges (Profile), news (News). A number clears when you open that place. | Must | ✅ |
| FR-NOTIF-2 | For each kind, users choose "Tab icon", "On my screen" (the What's new box on Home), both or neither. No pop-ups or extra emails. | Must | ✅ |
| FR-NOTIF-3 | Sensible, quiet defaults: news is off, Need players posts show on the screen but not the tab. New accounts start with nothing to catch up on. | Should | ✅ |

### Safety and admin (SAFE)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-SAFE-1 | Report a profile, a direct message or a chat message (a copy is saved); optionally block at the same time. The reported person isn't told who reported them. | Must | ✅ |
| FR-SAFE-2 | Admins (set by `ADMIN_EMAILS`) review reports, see people reported by 3+ others, and can suspend or restore accounts. Suspending cancels games they host and hides their profile from students. | Must | ✅ |
| FR-SAFE-3 | Admins review club registrations. | Must | ✅ |
| FR-SAFE-4 | The people who run the app (admins) show a gold 🐾 Team label on their profile, in game lists and in messages, plus a 💜 Sportive Circle Team badge. It can't be earned or faked, and goes away if someone stops being an admin. | Should | ✅ |

### Info pages (INFO)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-INFO-1 | A How it works page explains the app in plain words, with a glossary. | Must | ✅ |
| FR-INFO-2 | Privacy and Terms pages, linked from every page and from sign-up. | Must | ✅ |
| FR-INFO-3 | Husky news from GoHuskies.com, filtered to your sports or any team. | Could | ✅ |
| FR-INFO-4 | A Suggestions link in the footer: logged-in students send ideas or problems (optionally anonymous, max 5 an hour); only admins can read them. Suggestions are scanned for keywords, and admins are notified only when 3+ different people bring up the same topic within 30 days. | Should | ✅ |

---

## 3. Non-functional requirements

### Security (NFR-SEC)

| ID | Requirement | How it's met | Status |
|---|---|---|---|
| NFR-SEC-1 | Passwords are never stored in readable form. | PBKDF2-SHA256, 600,000 rounds (Werkzeug). | ✅ |
| NFR-SEC-2 | Every form is protected against cross-site request forgery. | A secret token in every POST form, checked on the server. | ✅ |
| NFR-SEC-3 | Text people type can never run as code (XSS). | Jinja escapes everything; no inline JavaScript at all; Content-Security-Policy allows scripts only from our files and cdnjs. | ✅ |
| NFR-SEC-4 | No SQL injection. | Every user value goes through query parameters, never string building. | ✅ |
| NFR-SEC-5 | Login cookies are HttpOnly, SameSite=Lax, and HTTPS-only when the site uses HTTPS. The app refuses to start publicly without a real `SECRET_KEY`. | Config in `create_app`. | ✅ |
| NFR-SEC-6 | Limits against abuse: code attempts, resend cooldown, login lockout, 20 messages/minute, 10 reports/hour, 3 pending clubs per person, length limits on every text field and search, and double-tap protection on forms. | Checked on the server (and in the browser for double taps). | ✅ |
| NFR-SEC-7 | Security headers on every response. | CSP, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `frame-ancestors 'none'`. | ✅ |
| NFR-SEC-8 | Redirects after login only go to pages on this site. | `safe_next()` blocks `//evil.com`. | ✅ |

### Privacy (NFR-PRIV)

| ID | Requirement | Status |
|---|---|---|
| NFR-PRIV-1 | Location from "Where am I?" never leaves the browser. | ✅ |
| NFR-PRIV-2 | Photo metadata is removed. | ✅ |
| NFR-PRIV-3 | Deleting an account deletes the person's data (reports keep a copy for safety, without the reporter's name). | ✅ |
| NFR-PRIV-4 | No ads, no tracking cookies, no selling data. Only a login cookie. | ✅ |
| NFR-PRIV-5 | The database file is never committed to Git (`.gitignore`). | ✅ |

### Usability and accessibility (NFR-UX)

| ID | Requirement | Status |
|---|---|---|
| NFR-UX-1 | Works on phones (bottom tabs), tablets and laptops (sidebar), with the same 5 sections everywhere. | ✅ |
| NFR-UX-2 | Plain words: short sentences, no unexplained jargon (glossary on How it works). | ✅ |
| NFR-UX-7 | Long pages are split into clear sections by soft full-width bands; items inside a section are split by thin lines. | ✅ |
| NFR-UX-3 | Keyboard and screen-reader friendly: labels on every field, skip link, visible focus, `aria-current` on tabs, alt text rules, and text contrast of at least 4.5:1 (WCAG AA). | ✅ |
| NFR-UX-4 | Light and dark mode; animations are skipped for "reduce motion". | ✅ |
| NFR-UX-5 | Error messages say what went wrong and how to fix it. Friendly pages for 400/403/404/405/413/500. | ✅ |
| NFR-UX-6 | Husky look and feel: UW purple and gold, paw logo, Husky wording, without using UW's trademarked logos. | ✅ |

### Performance and reliability (NFR-PERF)

| ID | Requirement | Status |
|---|---|---|
| NFR-PERF-1 | Pages load fast on campus Wi-Fi: no frontend framework, one small stylesheet; the map library loads only on event pages that have a map. | ✅ |
| NFR-PERF-2 | Database indexes on the common lookups (events by time, RSVPs by person, messages, club members, friendships, vouches). | ✅ |
| NFR-PERF-3 | GoHuskies news is cached for 30 minutes and the page still works if their site is down. | ✅ |
| NFR-PERF-4 | One failed email never blocks an action or anyone else's reminder (errors are logged). Bad input never crashes the server: 1,000+ junk requests return friendly errors. | ✅ |
| NFR-PERF-5 | SQLite is fine for thousands of students; move to PostgreSQL if the app grows well beyond one UW campus. | 🟡 |

### Maintainability (NFR-MAINT)

| ID | Requirement | Status |
|---|---|---|
| NFR-MAINT-1 | Automated tests (unit tests + Gherkin scenarios) run with one command and in GitHub Actions on every push. | ✅ |
| NFR-MAINT-2 | Sports, places and caps live in one file (`constants.py`). | ✅ |
| NFR-MAINT-3 | Database upgrades happen automatically (`ADDED_COLUMNS` in `db.py`). | ✅ |
| NFR-MAINT-4 | Small modules, one per area (auth, events, clubs, social...), with docstrings that explain *why*. | ✅ |

### Compatibility (NFR-COMP)

| ID | Requirement | Status |
|---|---|---|
| NFR-COMP-1 | Current Safari (iPhone and Mac), Chrome, Firefox and Edge. | ✅ |
| NFR-COMP-2 | Python 3.9 or newer. | ✅ |

### Legal and branding (NFR-LEGAL)

| ID | Requirement | Status |
|---|---|---|
| NFR-LEGAL-1 | Says clearly on every page that it's a student project, not an official UW service. | ✅ |
| NFR-LEGAL-2 | Uses no UW logos (the "W", Husky dog marks). Only UW colors and place names. | ✅ |
| NFR-LEGAL-3 | GoHuskies content: only headlines and links, credited, opening on their site. | ✅ |
| NFR-LEGAL-4 | Have someone review the Privacy and Terms pages before a large public launch. | ⬜ |

---

## 4. Out of scope for now

- Push notifications (email only for now).
- Reserving courts or fields (UW Recreation handles that).
- Intramural (IM) league scores and schedules.
- Native iPhone and Android apps (the website works on phones and can be added to the home screen).
