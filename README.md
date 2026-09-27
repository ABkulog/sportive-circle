# Sportive Circle @ UW

A web app that helps University of Washington students find people to play sports with:
pickup games, running partners, climbing buddies, ski trips and more.

It started as a Turkish desktop app (Python + tkinter + SQLite) that I built to bring people
together through sports. This version rebuilds it as a mobile-friendly web app for UW students.

## Features

- **UW-only accounts.** Sign up with an `@uw.edu` email, verified with a 6-digit code.
  Passwords are stored as PBKDF2-SHA256 hashes, never as plain text.
- **Personal feed.** Shows events for the sports you picked, and can be filtered by sport,
  day, location and skill level.
- **⚡ Need players.** "We have 8, need 2 for soccer in 15 minutes" becomes a post in seconds
  and is pinned to the top of everyone's feed.
- **Events and RSVPs.** Join or leave events, see who's going, set a player limit. The last
  spot can't be taken twice, even if two people click at once.
- **Hosting.** Hosts can edit or cancel their events, and there's a "My events" page for hosting,
  going and past events.
- **Profiles with pictures.** Everyone adds a profile picture before using the app, so you know who
  you're meeting. Photos are cropped to a square, shrunk, and stripped of hidden location data.
- **How it works page.** A simple step-by-step guide at `/how-it-works`, shown to new users after they
  add their photo.
- **Security.** CSRF protection on every form, a limit on wrong verification codes, and
  protection against open redirects.
- **Reminders.** An email an hour before your events, plus an "Up next" banner on the feed.
- **Safety.** Report profiles and messages (with a saved copy of the message), block people, and review
  reports on an admin-only page that flags anyone reported by several people.
- **Your data.** You can delete your account and everything in it from your profile settings.
- 🎂 The birthday coupon from the original app is still there.

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py      # optional: demo students + events
.venv/bin/python main.py      # http://localhost:5050
```

The demo login is printed by `seed.py`. With no email server set up, dev mode shows the
verification code on screen instead of emailing it.

Run the tests:

```bash
.venv/bin/python -m pytest -q
```

## Project layout

```
main.py               starts the app
seed.py               demo data for local development
sportive/
  __init__.py         app setup + config
  constants.py        sports, campus locations, skill levels  <- edit these
  schema.sql          database tables
  db.py               database helpers
  auth.py             sign up, email verification, log in/out, CSRF
  events.py           feed, create/edit/cancel, join/leave, Need players, My events
  profile.py          profiles
  timeutil.py         Seattle-time helpers
  templates/          HTML pages (Jinja)
  static/style.css    styling (UW purple & gold, dark mode)
tests/                automated tests (pytest)
Sportive Sircle.py    the original Turkish desktop app
sportive_circle_en.py the original app translated to English
```

## Sending real verification emails

Set these environment variables, for example with an email service's SMTP settings:

```
MAIL_SERVER, MAIL_PORT (default 587), MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM
SECRET_KEY   # a long random string; the app refuses to start publicly without it
PUBLIC_URL   # the site's address, e.g. https://sportivecircle.app (used in email links)
ADMIN_EMAILS # who can review reports at /admin/reports, e.g. you@uw.edu (comma-separated)
```

## Event reminders

Everyone going to an event gets an email about an hour before it starts (they can turn this
off in their profile). Schedule this command to run every 10 minutes on the server:

```bash
flask --app "sportive:create_app()" send-reminders
```

The feed also shows an "⏰ Up next" banner for your events in the next 2 hours.

## Roadmap

- [ ] Deploy publicly and test with a few dorms/clubs
- [ ] Chat for each event
- [x] Event reminders
- [ ] Notifications ("someone needs players for your sport")
- [ ] Club and intramural (IM) team pages
- [ ] Reliability ratings (did people show up?)
- [ ] Usage stats: sign-ups, events and games that actually happened
