# Sportive Circle @ UW 🐾

A web app that helps University of Washington students find people to play sports with:
pickup games, verified UW clubs, running partners, ski trips and more.

It started as a Turkish desktop app (Python + tkinter + SQLite) that I built to bring people
together through sports. This version rebuilds it as a mobile-friendly web app for UW students.
It is a student project, not an official University of Washington service.

## Features

**Playing**
- **Home feed** of games for your sports, with filters (sport, day, place, level) and a
  "happening soon" row at the top.
- **Need players:** "we have 8, need 2 for soccer in 15 minutes" becomes a post in seconds.
- **Events:** create, edit or cancel (everyone who joined gets an email); join or leave; player limits
  that can't be overbooked; campus places per sport with a map, "Where am I?", walking directions and
  calendar export.
- **Group chat** for everyone going to a game, and **email reminders** an hour before.

**Clubs**
- **Verified UW clubs only.** Officers register with their club's HuskyLink or UW Recreation page;
  an admin approves it before it's public.
- Each club page shows everything a new member needs: how to join, tryouts, dues, experience,
  practices, contact info and officers.
- **Follow** instantly; **membership is confirmed by officers** (request, application or tryouts).
- **Club updates** feed with posts from clubs you follow.

**People**
- **UW-only accounts** (`@uw.edu`, or older `@u.washington.edu` addresses), verified with a 6-digit code.
  Forgot-password and change-password flows.
- Profiles with photos (cropped, shrunk, and stripped of location data).
- **Friends:** search by name, or add people you've played with. Direct messages with anti-spam rules.
- **Ranks per sport** (Casual → Intermediate → Competitive → Legend) earned by playing and by
  teammate vouches; tryout spots and "+1" invites so skill levels can mix; chill mode hides ranks.
- **Badges**, including limited ones that retire each quarter; show your top 3.
- **Husky news** from every UW Division I team (headlines link to GoHuskies.com).

**Safety**
- Report profiles and messages (with a saved copy), block people, and an admin page to review
  reports and suspend accounts.
- Privacy and Terms pages in plain language.

## Documentation

| Document | What's in it |
|---|---|
| [Requirements](docs/requirements.md) | Functional and non-functional requirements, each with an ID and status. |
| [System map](docs/system-map.md) | Architecture, code map, screen map, data model and key flows (diagrams). |
| [Gherkin scenarios](tests/features) | Plain-English test cases for every major requirement, run automatically. |
| [Deployment](docs/deployment.md) | Step-by-step guide to putting the app online for students. |

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py      # optional: demo students, games and (clearly labeled) demo clubs
.venv/bin/python main.py      # http://localhost:5050
```

`seed.py` prints a demo login. With no email server set up, verification codes are shown on screen
instead of emailed.

## Tests

```bash
.venv/bin/python -m pytest -q
```

This runs about 190 checks:
- **Unit tests** (`tests/test_app.py`): every route and rule, including edge cases.
- **Gherkin scenarios** (`tests/features/*.feature`, run by `tests/test_features.py` with
  [pytest-bdd](https://pytest-bdd.readthedocs.io/)): user stories written in plain English, tagged
  with the requirement they check, for example:

  ```gherkin
  @FR-EVT-5
  Scenario: A full game can't be overbooked
    Given "Maya" hosts a tennis game for 2 players tomorrow
    And "Jordan" joins Maya's game
    And "Sam" is a Husky
    When "Sam" joins Maya's game
    Then they see "Sorry, this event is full"
  ```

GitHub Actions runs everything on every push (`.github/workflows/tests.yml`).

## Project layout

```
main.py               starts the app locally (debug mode)
wsgi.py               starts the app on a server:  gunicorn wsgi:app
seed.py               demo data for local development
.env.example          the settings a live server needs
sportive/
  __init__.py         app setup, settings, security headers, error pages
  constants.py        sports, campus places, map pins, player limits  <- edit these
  schema.sql          database tables
  db.py               database helpers and automatic column upgrades
  auth.py             sign up, email codes, log in/out, forgot password, CSRF
  events.py           feed, events, Need players, joining, tryouts, +1s, props & vouches, calendar
  clubs.py            club directory, registration, membership, updates, admin review
  social.py           friends and name search, blocking, direct messages, event chats
  profile.py          profiles, photos, badge showcase, settings, account deletion
  moderation.py       reports, the admin reports page, suspending accounts
  ranks.py, badges.py per-sport ranks and badges
  news.py             Husky news from GoHuskies.com feeds
  pages.py            How it works, Privacy, Terms, the Create menu
  reminders.py        "send-reminders" command (run every 10 minutes)
  stats.py            "sport-stats" command (to tune player limits)
  links.py, mail.py, photos.py, spirit.py, timeutil.py   helpers
  templates/          pages (Jinja)
  static/             styles, icons, and small scripts (no inline JavaScript anywhere)
docs/                 requirements, system map, deployment guide
tests/                unit tests and Gherkin scenarios
Sportive Sircle.py    the original Turkish desktop app
sportive_circle_en.py the original app translated to English
```

## Settings for a public deployment

See [`.env.example`](.env.example) and [docs/deployment.md](docs/deployment.md). The important ones:

```
SECRET_KEY    a long random string (the app refuses to start publicly without it)
PUBLIC_URL    the site's https address, used in email links, calendar files and share links
BEHIND_PROXY  1 on hosts like Render/Railway/Fly.io
DATABASE      where the database file lives (use a persistent disk)
ADMIN_EMAILS  who can review reports and club registrations, e.g. you@uw.edu (comma-separated)
MAIL_SERVER, MAIL_PORT (default 587), MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM
```

## Roadmap

- [ ] Deploy publicly and pilot with a few UW clubs
- [ ] Push notifications ("someone needs players for your sport")
- [ ] Intramural (IM) team pages
- [ ] Reliability ratings (did people show up?)
- [ ] Usage stats: sign-ups, games played, club members found
