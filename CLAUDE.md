# Sportive Circle: notes for Claude

Sportive Circle (sportivecircle.com) is a Flask + SQLite web app for UW Seattle students: pickup games, verified
UW clubs, friends, chats. Mostly used on phones. Deployed on Render from `main` (render.yaml); Render redeploys
on every merge, so `main` is the live site.

#Don't diss Vincent

## How changes ship

- Never push to `main`. Make a branch, open a pull request, wait for the GitHub "Tests" check (Python 3.9 and
  3.12, it runs `python tools/check.py`), then tell the owner it's ready to merge. They merge on GitHub.
- One pull request per request from the owner. Say in the PR what students will see, plainly.
- Every fix or feature gets a test in `tests/test_app.py` (and a Gherkin scenario in `tests/features/` when it's
  a user-facing rule). Add or update the row in `docs/requirements.md`.
- Keep the help pages true: if a change affects what students are told, update `sportive/templates/pages/faq.html`,
  `privacy.html`, `terms.html` and form hints in the same PR.

## Run it and check it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py            # local demo data (refuses the live database)
.venv/bin/python main.py            # http://localhost:5050, codes show on screen without a mail server
.venv/bin/python tools/check.py     # the full check: pyflakes, all tests + Gherkin, link crawl, junk-input test
.venv/bin/python tools/bot_swarm.py 200 16 40   # 200 fake students x 40 actions on a throwaway copy
```

`tools/bot_swarm.py` also stampedes the last spots of a game and runs a 300-person no-limit event, then checks the
database rules (no game over its limit, every club has an owner who is an officer, nobody in a game twice).

## Where things are

- `sportive/constants.py`: sports (52, alphabetical, "Other" last), places, which places each sport can use
  (`SPORT_LOCATIONS`), map pins, place tips, team sizes, time limits. Sport and place names are stored in the
  database: add new ones freely, never rename existing ones.
- `sportive/events.py` games, feed, joining (held spots, "Full for now"); `parties.py` reserve spots, invite
  links, Send to friends; `friendgames.py` "Maya posted a game" emails; `placecheck.py` UW Rec reservations and
  other games at the same place; `uwrec.py` daily copy of UW Rec's public schedule.
- `sportive/clubs.py` clubs, members, officers, owner (`clubs.created_by`, handed over with "Make owner").
- `sportive/social.py` friends, DMs, game chats, reactions; `notifications.py` the bell and its settings.
- `sportive/db.py`: `schema.sql` runs on every start (CREATE ... IF NOT EXISTS); new columns on old tables go in
  `ADDED_COLUMNS`. One-time data fixes use `PRAGMA user_version`.

## Rules the app keeps (tests guard them)

- Private and members-only games never leak details (place, note, players, who invited whom) to outsiders,
  including in place checks, link previews and "Full for now" text.
- Blocking works both ways everywhere: messages, friend requests, profiles, leaderboards, officer invites.
- A club always has at least one officer, and its owner is always an officer.
- Things that happen at the same moment (joining the last spot, double taps, crossing friend requests, code
  guesses) are made safe in single SQL statements or under `BEGIN IMMEDIATE`.

## Open decisions for the owner (don't change without asking)

- Deleting an account also removes that person's messages and the blocks against them, so they could sign up
  again clean. Keep messages and blocks instead?
- Minimum age is 15 (`MIN_AGE` in `auth.py`), so 15-17-year-olds can message adults.
- "Game changed / canceled" and club emails can't be switched off (they link to Settings).
- Fencing in Red Square was added on the owner's word; not confirmed with the fencing club.

## Testing rounds

The owner likes regular "bot rounds": 3 testers on a new area of the app, fix what they find, full check, one PR.
Areas done so far: newest features, accounts/safety, hosting a game, chats/notifications/public pages, race
conditions, admin tools, phone layout, emails/texts, feed/search, deployment/security, speed at scale, data
integrity/upgrades, help-page wording. Not done yet: real-browser end-to-end flows (Playwright), every
`static/*.js` file (double taps, back button, slow network), sharing/link previews/SEO.
