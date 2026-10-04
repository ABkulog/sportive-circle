# Editing Sportive Circle by hand

A beginner's guide: what each file does, what you can safely change yourself, and how to get a change onto
sportivecircle.com without breaking it.

---

## 1. One-time setup on your computer

1. **Install** [VS Code](https://code.visualstudio.com), [Git](https://git-scm.com/downloads) and
   [Python 3.12](https://www.python.org/downloads/) (on Windows, tick "Add Python to PATH" in the installer).
2. **Get the code.** In VS Code: `Ctrl+Shift+P` (Mac: `Cmd+Shift+P`) → "Git: Clone" →
   paste `https://github.com/ABkulog/sportive-circle` → pick a folder → Open.
3. **Open the terminal** in VS Code: menu **Terminal → New Terminal**. Then run, one line at a time:

   Mac:
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/python seed.py
   ```
   Windows:
   ```bash
   py -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   .venv\Scripts\python seed.py
   ```
   `seed.py` fills a **local, fake** database with demo students, games and clubs. It never touches the live site.

## 2. Every time you make a change

1. **Get the latest code:** click the sync arrows at the bottom-left of VS Code (or run `git pull`).
2. **Make a branch** (never work on `main`, because `main` *is* the live site): click the branch name at the
   bottom-left → "Create new branch" → name it, e.g. `add-tennis-courts`.
3. **Edit** the file (see section 3).
4. **Look at it:** run `.venv/bin/python main.py` (Windows: `.venv\Scripts\python main.py`) and open
   <http://localhost:5050>. Log in as `demo.maya@uw.edu` / `huskies-demo-2026`. Stop the app with `Ctrl+C`.
5. **Run the full check:** `.venv/bin/python tools/check.py`. It must end with everything passing. If it
   fails, the message says which page or test broke.
6. **Save to GitHub:** in the Source Control tab (the branch icon on the left), write a short message like
   "Add Green Lake running route", click **Commit**, then **Publish Branch**.
7. **Open a pull request** on GitHub (it shows a yellow "Compare & pull request" button), wait for the green
   **Tests** check, then **Merge**. Render puts it live a few minutes later.

If anything looks wrong after merging, open the merged pull request on GitHub and click **Revert**. That
undoes it.

## 3. What you can add yourself (easiest first)

### Words people see: safe, no code knowledge needed
All the pages are in `sportive/templates/`. They are HTML with some `{{ ... }}` and `{% ... %}` parts mixed in.
**Change the plain English text; leave anything inside `{{ }}` or `{% %}` exactly as it is.**

| What | File |
|---|---|
| FAQ / help answers | `sportive/templates/pages/faq.html` |
| "How it works" page | `sportive/templates/pages/how_it_works.html` |
| The front page people see before logging in | `sportive/templates/landing.html` |
| Privacy and Terms | `sportive/templates/pages/privacy.html`, `terms.html` |
| Club pages, club list, club sign-up form | `sportive/templates/clubs/` (`view.html` = one club's page, `directory.html` = list of clubs, `form.html` = register/edit a club) |
| Game pages and forms | `sportive/templates/events/` |
| Emails the app sends | `sportive/templates/emails/` |
| Menus and layout on every page | `sportive/templates/base.html` |

### Sports, places and map pins: one file, `sportive/constants.py`
This is the file you'll edit most. Each list has comments explaining it.

- **Add a sport:** add a line to `SPORTS` in alphabetical order, like `"cornhole": "Cornhole",`. The part on
  the left is a hidden key (lowercase, no spaces); the right is what students see. Then add the sport to
  `SPORT_LOCATIONS` (where it can be played) and `SPORT_SPACE` (what the host should check is free, e.g. `"courts"`).
- **Add a place** (for example a running route or tennis courts a club uses):
  1. Add its name to `LOCATIONS` (alphabetical; "Off campus" and "Online" stay last).
  2. Add its map pin to `LOCATION_COORDS`. Find it on Google Maps, right-click the spot, click the numbers at
     the top to copy them, paste as `"Place name": (47.65, -122.30),`.
  3. Add it to the sports that use it in `SPORT_LOCATIONS`.
  4. If it has opening hours, add them to `PLACE_HOURS` (copy an existing line and change the times).
- **Never rename or delete** an existing sport key or place name: games already saved in the database use
  them. Changing the label on the right side is fine.
- Usual team sizes: `SPORT_TEAM_SIZES` and `DEFAULT_PLAYERS`. Skill levels: `SKILL_LEVELS`.

### Colors and look: `sportive/static/style.css`
Colors are defined once near the top as variables (lines like `--purple: #4b2e83;`). Change a value there and
it changes everywhere. Check the result on your phone size too: in Chrome, right-click → Inspect → the phone
icon.

### Images and icons: `sportive/static/`
Logos and icons live here. Replace a file with one of the **same name and size**. The QR code flyer is in
`marketing/`.

### Things that are real code: ask the AI first
| Area | File |
|---|---|
| Clubs: officers, members, joining, club events | `sportive/clubs.py` |
| Games: creating, joining, the feed | `sportive/events.py` |
| Accounts: sign up, log in, passwords | `sportive/auth.py` |
| Friends, messages, chats | `sportive/social.py` |
| The bell and notification settings | `sportive/notifications.py` |
| Database tables | `sportive/schema.sql`, `sportive/db.py` |
| Tests that protect all of the above | `tests/test_app.py`, `tests/features/*.feature` (plain-English scenarios) |

You *can* change these, but every change needs a matching test (that's the house rule in `CLAUDE.md`), and a
mistake can affect real users. Describe what you want to the AI in VS Code and let it make the change and
the test, then run `tools/check.py` yourself before committing.

### Files to leave alone
- `render.yaml`, `wsgi.py`, `requirements.txt`, `.github/`: how the site is hosted and tested.
- `.env` / secrets: passwords for email etc. live in Render's dashboard, never in the code.
- `Sportive Sircle.py` and `sportive_circle_en.py`: the old high-school desktop app (Turkish and English).
  The website doesn't use them.

## 4. Other docs in this folder
- `docs/requirements.md`: every rule the app follows, with an ID and whether it's tested.
- `docs/system-map.md`: diagrams of how the pieces fit together.
- `docs/deployment.md`: how the live site on Render is set up.
- `CLAUDE.md` (top folder): the rules AI assistants follow in this project. Worth reading once.
