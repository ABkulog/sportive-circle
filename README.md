# Sportive Circle @ UW

A web app that helps University of Washington students find people to play sports with:
pickup games, verified UW clubs, running partners, ski trips and more.

It started as a Turkish desktop app (Python + tkinter + SQLite) that I built to bring people
together through sports. This version rebuilds it as a mobile-friendly web app for UW students.
It is a student project, not an official University of Washington service.

## Features

**Playing**
- **Home feed** of games for your sports, with filters (sport, day, place, level) and a
  Stories-style "Now" row for games starting soon.
- **Need players:** "we have 8, need 2 for soccer in 15 minutes" becomes a post in seconds.
- **Events:** create, edit or cancel; join or leave; player limits that can't be overbooked;
  per-sport campus locations with a map, walking directions and calendar export.
- **Group chat** for everyone going to an event, and **email reminders** an hour before.

**Clubs**
- **Verified UW clubs only.** Officers register with their club's official HuskyLink or
  UW Recreation page; an admin approves it before it's public.
- Each club page shows everything a new member needs: how to join, tryouts, dues, experience,
  practices, contact info and officers.
- **Follow** instantly; **membership is confirmed by officers** (request, application or tryouts).
- **Club updates** feed with posts from clubs you follow.

**People**
- **UW-only accounts** (`@uw.edu`, or older `@u.washington.edu` addresses), verified with a 6-digit code.
- Profiles with photos (cropped, shrunk, and stripped of location data), friends, direct messages.
- **Ranks per sport** (Casual → Intermediate → Competitive → Legend) earned by playing and by
  teammate vouches; tryout spots and "+1" invites so skill levels can mix; chill mode hides ranks.
- **Badges**, including limited ones that retire each quarter; show your top 3.
- **Husky news** from every UW Division I team (headlines link to GoHuskies.com).

**Safety & data**
- Report profiles and messages (with a saved copy), block people, and an admin page for reports.
- CSRF protection on every form, hashed passwords, rate limits on codes, logins, messages and reports.
- Delete your account at any time, after an "Are you sure?" step.

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py      # optional: demo students, games and (clearly labeled) demo clubs
.venv/bin/python main.py      # http://localhost:5050
```

`seed.py` prints a demo login. With no email server set up, the verification code is shown on
screen instead of emailed.

Run the tests:

```bash
.venv/bin/python -m pytest -q
```

## Project layout

```
main.py               starts the app (local development)
seed.py               demo data for local development
sportive/
  __init__.py         app setup and settings
  constants.py        sports, campus places, map pins, player limits  <- edit these
  schema.sql          database tables
  db.py               database helpers and automatic column upgrades
  auth.py             sign up, email verification, log in/out, CSRF
  events.py           feed, events, joining, Need players, tryouts, +1s, props & vouches
  clubs.py            club directory, registration, membership, updates, admin review
  social.py           friends, blocking, direct messages, event chats
  profile.py          profiles, photos, badge showcase, account deletion
  ranks.py            per-sport ranks
  badges.py           badges (including limited seasonal ones)
  news.py             Husky news from GoHuskies.com feeds
  moderation.py       reports and the admin reports page
  reminders.py        "send-reminders" command
  stats.py            "sport-stats" command (to tune player limits)
  mail.py, photos.py, spirit.py, timeutil.py   helpers
  templates/          pages (Jinja)
  static/             styles, icons, and small scripts (chat, map, tabs, forms)
tests/                automated tests (pytest)
Sportive Sircle.py    the original Turkish desktop app
sportive_circle_en.py the original app translated to English
```

## Settings for a public deployment

```
SECRET_KEY    a long random string (the app refuses to start publicly without it)
PUBLIC_URL    the site's address, used in email links
ADMIN_EMAILS  who can review reports and club registrations, e.g. you@uw.edu (comma-separated)
MAIL_SERVER, MAIL_PORT (default 587), MAIL_USERNAME, MAIL_PASSWORD
MAIL_FROM     optional; defaults to MAIL_USERNAME
```

Two commands to run on a schedule:

```bash
flask --app "sportive:create_app()" send-reminders   # every 10 minutes
flask --app "sportive:create_app()" sport-stats      # any time, to review player limits
```

## Roadmap

- [ ] Deploy publicly and pilot with a few UW clubs
- [ ] Push notifications ("someone needs players for your sport")
- [ ] Intramural (IM) team pages
- [ ] Reliability ratings (did people show up?)
- [ ] Usage stats: sign-ups, games played, club members found
