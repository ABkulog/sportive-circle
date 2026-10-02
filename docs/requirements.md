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
| **Student (Husky)** | Find a game or a club for their sport, alone or with friends, and show up without awkwardness. |
| **Host** | Fill a game quickly ("need 2 more"), plan one ahead, or run a private or team vs team game. |
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
| FR-AUTH-9 | Sign-up forgives going back: a problem shows on a normal page (typed details kept, passwords not), so the phone's Back button works; going back to fix details with the same email keeps the code already sent; the code page has "Wrong email? Fix it". Changing your password cancels any pending reset code. | Must | ✅ |

### Profile (PROF)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-PROF-1 | New users are asked for a profile photo once. "Add later" shows a "No problem" pop-up, is remembered (no asking at every login, no banner), and leaves one reminder in the bell. | Must | ✅ |
| FR-PROF-2 | Photos are cropped to a square, shrunk to 256 px, and stripped of hidden metadata (like GPS). | Must | ✅ |
| FR-PROF-3 | Users can edit name, class year, bio, sports, photo and reminder emails. Their own profile has one Edit profile button, plus Add photo only when there's no photo; initials sit centered when there's no photo. | Must | ✅ |
| FR-PROF-4 | A user's email is shown only to themselves and people they've played a game with. | Must | ✅ |
| FR-PROF-5 | On the photo page, Save without picking a new photo goes back to the profile, and users can remove their photo (with an "Are you sure?"). | Should | ✅ |
| FR-PROF-6 | Optional pronouns, gender (says it's only used for games open to women or men), and Instagram / Snapchat / TikTok / X usernames right under the bio in Edit profile, shown on the profile only if filled in. | Should | ✅ |
| FR-PROF-7 | Emails shown to people you've played with are hidden once either of you blocks the other. Top Dawgs ties share a place and medal. | Must | ✅ |
| FR-PROF-8 | Someone you blocked (or who blocked you) sees only your name and photo, not your bio, pronouns, gender, class year, sports, badges or socials; suspended people's photos aren't served. Pronouns and names can't hide behind invisible or right-to-left characters. Pasted social links keep the full username (long links aren't cut off), pasted short links like vm.tiktok.com/… are refused (a username like maya.co is fine), and long handles wrap on a phone. | Must | ✅ |

### Games and events (EVT)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-EVT-1 | Create an event with a name, sport, place, start/end time, level, a player count (a dropdown that starts at the sport's usual size and stops at its max) and an optional note. | Must | ✅ |
| FR-EVT-2 | Each sport can only use places where it can really be played (e.g. rowing only at the WAC, pickleball at the IMA courts, IMA Gym B or Green Lake), with good-to-know tips such as court numbers and drop-in hours. | Must | ✅ |
| FR-EVT-3 | The host picks how many players they need (2 to 1000), whatever the sport, or ticks "No limit" so anyone can join (hall runs, club socials); each sport only suggests a usual size (e.g. basketball 10). Need players posts always use a number. | Must | ✅ |
| FR-EVT-4 | "Need players": post a game that starts within 2 hours in a few taps; it goes to the top of every feed. Both create forms ask "Players" and "Who's coming?" (friends from the app, friends not on the app) and show the math: "You + 2 friends = 3 of 10 · need 7 more". Friends picked are counted once, inside the player count. | Must | ✅ |
| FR-EVT-5 | Join and leave games. A full game can't be overbooked, even when two people tap Join at once. | Must | ✅ |
| FR-EVT-6 | Games that are over stay in your history: you can't leave them. | Should | ✅ |
| FR-EVT-7 | Hosts can edit or cancel. Canceling tells everyone who joined (email + bell). | Must | ✅ |
| FR-EVT-8 | The feed shows upcoming games for your sports, with filters for sport, day (today / week / month), place, level and open spots. Sports and places are listed alphabetically. | Must | ✅ |
| FR-EVT-9 | Event pages have a map, walking directions (Google or Apple Maps), "Where am I?" with distance, share, and "Add to calendar" (.ics). | Should | ✅ |
| FR-EVT-10 | "Where am I?" explains how to turn location on when the browser blocks it, retries with rough location if precise location times out, and still works if the map can't load. | Should | ✅ |
| FR-EVT-11 | Everyone going to a game gets an email reminder: 1 hour before by default; each player can pick 30 min or no reminder on the game page (and turn all of them off in Settings). The app checks every 5 minutes by itself (no outside scheduler), and nobody gets the same reminder twice. | Should | ✅ |
| FR-EVT-12 | Everyone going to a game can use its group chat. | Should | ✅ |
| FR-EVT-13 | When the host changes the time, place, sport or note, everyone who joined gets a notice in the bell; a time or place change also sends an email. | Must | ✅ |
| FR-EVT-14 | The skill level is a label chosen by the host, not a gate: anyone can join any game. The note says what the host is looking for. | Must | ✅ |
| FR-EVT-15 | "N+ open spots" filter, for groups looking for a game together. | Should | ✅ |
| FR-EVT-16 | Games have a sensible maximum length: 6 hours for court and field sports, 12 for running, rowing and esports, 3 days for trips. | Should | ✅ |
| FR-EVT-17 | Game pages have a Back button that returns to where you came from (never into the game's own chat). | Should | ✅ |
| FR-EVT-18 | Open games can be "Open to" anyone, women, men, nonbinary players or Other (like UW Recreation's women-only hours). People whose profile gender is outside the group can't join and don't see it in their feed; people who left gender blank confirm instead. Hosts can remove a player (who gets a notice). | Should | ✅ |
| FR-EVT-19 | Creating a game (New event and Need players) shows a heads-up: check you can use the courts / field / trail (the word follows the sport) then, since it could be booked, full or closed for an event. Sportive Circle doesn't reserve or check places; the host does. The Terms say the same. | Must | ✅ |
| FR-EVT-21 | A game that's over can't be edited (it stays in everyone's history as it was). Time math uses real elapsed time on the nights clocks change: sport length limits, Need players start times (never in the skipped hour) and reminders (sent at the right moment, with the right minutes). | Must | ✅ |
| FR-EVT-23 | When a host changes a game, the email and notice say what changed (new time, now ends at, new place, new note) and show the full time; friends with a spot held get their invite updated too. A canceled game doesn't show spots left. | Must | ✅ |
| FR-EVT-24 | Need players checks the place at the right Seattle time even on a phone set to another time zone. | Must | ✅ |
| FR-EVT-20 | While making a game, and on its page, people see what else is on at that place then: **UW Rec reservations** ("UW Rec: reserved 6–10 PM · IM flag football", you probably can't play there) and **other Sportive Circle games** (busy, not taken: you can still post, or join theirs). Private games show only as "a private game". UW Rec places link to UW Rec's schedule. UW Rec's bookings are copied automatically once a day from its public Facility Schedule; admins can add their own entries (Admin → UW Rec reservations, weekly repeats). | Should | ✅ |
| FR-EVT-22 | The UW Rec copy holds up to bad data: a space that sends nothing or junk keeps its place's last copy (and so does a place that suddenly lost most bookings); an odd booking is left out and reported, not the whole copy; times with "Z" or an offset are read correctly; a place we no longer read loses its old bookings; admins see when the last good copy was saved (a run where nothing could be read doesn't count); past the 4 weeks copied, the form says it can't tell yet. | Must | ✅ |

### Parties, private games, team vs team (PARTY, PRIV, TEAM)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-PARTY-1 | "Reserve spots for friends": the host can tick friends while creating a New event or Need players post, and anyone in a game can tap Reserve spots later; each friend gets a "You down?" notice. Someone not in yet can "Join + reserve spots for friends" in one step (all or nothing). | Must | ✅ |
| FR-PARTY-2 | Each invite holds a spot for 30 minutes, so strangers can't take it. "I'm in" takes it; "Can't make it" frees it and tells the inviter. Holds end by themselves. | Must | ✅ |
| FR-PARTY-3 | Not just the host: any player can invite friends. Only friends can be invited. | Must | ✅ |
| FR-PARTY-4 | Everyone in a game has "Send invite link": "Jordan wants you in their Sportive Circle game: … Tap to sign up and you're in." Signing up through it puts the person in that game and makes them friends with the sender; someone already on the app gets the game and sends the sender a friend request instead (so an old link can't undo an unfriend or a declined request). It never gets back in someone the host took off the game. The link is signed (can't be forged) and lets friends into a private game without the password. The Friends page has the same link for the app itself. | Must | ✅ |
| FR-PARTY-5 | A game that's full only because spots are held for invited friends says "Full for now", how many are held and by whose invite, and the time the soonest hold ends; the page updates by itself then. Trying to join says the same instead of a bare "full". | Must | ✅ |
| FR-PARTY-8 | Reserve spots and Send to friends list the same people: all your friends. Anyone you can't pick says why (already in, spot held for X more min, waiting for the host's OK, the host took them off). A held spot that ran out (30 min, no answer) says so and can be reserved again. The game page shows the host (and each inviter, for their own) what happened to invites that didn't work out: can't make it, joined then left, taken off, or taken back. | Must | ✅ |
| FR-PARTY-6 | "Send to friends" on any open public game (going or not): pick friends and they get a direct message with a card that opens the game. Nothing is held for them. Not for private games (they use the invite link and password). | Should | ✅ |
| FR-PARTY-7 | An invite link's page (and its preview in iMessage, Discord and the like) never shows a private or members-only game's place: it says "Place shown once you're in". Members-only invites say the game is for club members and don't promise a spot. Invite pages aren't listed by search engines. Public games and club links preview with what they are (sport, time, place; the club's description). | Must | ✅ |
| FR-PRIV-1 | New events and Need players posts can be private: a lock in the list, and joining needs the host's password (shown to the host and players). Wrong passwords are limited to 10 an hour. | Must | ✅ |
| FR-PRIV-2 | Friends the host invites to a private game don't need the password. | Must | ✅ |
| FR-PRIV-3 | In a private game, friends other players want to bring are requests with a note; the host approves or declines. | Should | ✅ |
| FR-PRIV-4 | Creating a game asks "Who can join? Anyone / Private". Private shows a ready-made password and "Invite friends", and hides what doesn't fit (we have / we need, skill level, team vs team, reserving). Its game page has a Share invite button (link + password) and Invite friends. Private Need players posts don't go to the top of everyone's feed. | Must | ✅ |
| FR-PRIV-5 | Tapping Join on a private game without typing the password isn't counted as a wrong try. A host saying yes to bringing someone who already got in doesn't hold an extra spot. | Must | ✅ |
| FR-TEAM-1 | Team vs team ("Format", on New event and Need players), only in sizes that fit the sport (e.g. basketball 2v2-5v5, none for running): the host's party is one team, another group challenges as the other team. Nobody walks in alone. | Should | ✅ |

### Badges (BADGE)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-BADGE-1 | Badges are earned by playing; limited (seasonal) badges retire forever. Users pick 3 to show. | Could | ✅ |
| FR-BADGE-2 | Admins can give the 🧪 Tester badge to the people who tested the app. It can't be earned. | Could | ✅ |

Ranks, props, vouches, tryout spots and +1s were removed after the first tester session ("ranks should go
until demanded"). The last version with them is the git tag `ranks-and-news-v1`.

### Clubs (CLUB)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-CLUB-1 | Only officers can register a club. A social media account or a website is required, either one or both (how admins check it's real); and the HuskyLink / UW Recreation page isn't asked (people put their website there and got stuck). | Must | ✅ |
| FR-CLUB-2 | A club is only public after an admin approves it. Rejections include a note on what to fix. | Must | ✅ |
| FR-CLUB-3 | Anyone (even logged out) can browse verified clubs and search or filter them (sport, beginner-friendly, free, no tryouts). | Must | ✅ |
| FR-CLUB-4 | Students can follow a club, or request to join / apply / sign up for tryouts. They're a member only after an officer confirms them. | Must | ✅ |
| FR-CLUB-5 | Officers can post updates, create club events, confirm or decline people, remove members and add officers. | Must | ✅ |
| FR-CLUB-6 | Students can message a club's officers before joining. | Should | ✅ |
| FR-CLUB-7 | Officers upload the club's logo (square, 256 px); it shows on the club page, in the club list, on Home and in Club updates. | Should | ✅ |
| FR-CLUB-8 | Every verified club has a Share page with its link and a printable QR code ("Scan to join") for flyers and the involvement fair. | Should | ✅ |
| FR-CLUB-9 | Club events can repeat weekly (up to 12 weeks, for practices) and can be for members only (only members see them in their feed or can join; others see "Join the club"). | Must | ✅ |
| FR-CLUB-10 | A new club event is posted to the club's updates automatically, with a link, so followers and members hear about it. | Should | ✅ |
| FR-CLUB-11 | Officers see members' UW emails, can copy them all and download the roster as a spreadsheet (CSV). Members don't see each other's emails. | Should | ✅ |
| FR-CLUB-12 | The person who registered a club is its owner: only they add officers (searching anyone on the app by name or UW NetID, on Manage officers) or take officer rights away; they always stay an officer. Other officers edit the club, post, make club events and confirm members. The owner can hand the club to another officer (Make owner); they stay an officer. If the owner is no longer an officer, any officer can manage officers. | Must | ✅ |
| FR-CLUB-13 | Club events belong to the club: any current officer can edit or cancel them and take players off, and an officer who leaves or steps down can't anymore. Someone who leaves the club or is removed is taken out of its upcoming members-only events (they stop seeing the note, players and chat). | Must | ✅ |
| FR-CLUB-14 | Weekly practices: the last week must be within a year. Turning a club event members-only takes people who aren't members off it (they're told). When another officer edits or cancels a club event, players hear it from that officer and the host is told too. A club going back to review sends each person one on-hold notice, not one per week. | Must | ✅ |

### Friends and messages (SOC)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-SOC-1 | Search for people by name, or by their exact UW NetID, and send a friend request. Results show class year, mutual friends and "Played together", so people with the same name can be told apart. | Must | ✅ |
| FR-SOC-2 | Accept, decline, cancel requests and unfriend. People you've played with are suggested. | Must | ✅ |
| FR-SOC-3 | Direct messages are allowed only between friends, people who played together, a student and a club officer, or when replying to someone who wrote first. | Must | ✅ |
| FR-SOC-4 | Blocking stops messages, friend requests and joining each other's games, both ways, and hides you from their search and feed. | Must | ✅ |
| FR-SOC-5 | Messages lists every friend, including ones with no messages yet ("Start a chat"), and has a search bar: typing filters chats and friends right away, and Search also finds anyone else you can message (people you've played with, club officers). Strangers point to Friends to add first. | Must | ✅ |
| FR-SOC-6 | When someone posts a public game, their friends (and, for a club event, the club's followers and members; members-only events: members only) get a bell notice and an email ("Maya posted a game", with a button to see and join it). Never for private games, blocked or suspended people, people already in it, or a game open only to another gender. At most 3 of these emails a day per person; the email can be turned off in Settings. A weekly practice is announced once. | Should | ✅ |
| FR-SOC-7 | Unfriending or blocking ends the spots held and invites either person sent the other, in any game (and their "You down?" notices). Suspended people don't count as mutual friends in search or suggestions. | Must | ✅ |
| FR-SOC-8 | People search never fails on odd input (only accent marks, emoji, wildcards) and folds letters like ı and ß; friends come first, so Messages search finds a friend even among many people with the same name. Messages with only invisible characters aren't sent; photo-only chats preview as "📷 Photo"; an unsent draft (even all emoji) comes back. | Must | ✅ |
| FR-SOC-9 | Game chats hide people blocked either way (their messages, reactions and unread counts) and suspended people's messages. | Must | ✅ |
| FR-SOC-10 | Suspended people disappear from game player lists (past games too), club member lists, invite lists and open chats. | Must | ✅ |

### Notifications (NOTIF)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-NOTIF-1 | Everything new shows in exactly one place, never twice: messages on ✉️, friend requests on 👥, club news on the Clubs tab, and everything else (invites, game changes, game chats, Need players, badges) in the 🔔 bell, in plain sentences. A number clears when you open that place. | Must | ✅ |
| FR-NOTIF-2 | Settings → Notifications: one on/off switch per kind, saying where it shows up. No pop-ups. | Must | ✅ |
| FR-NOTIF-3 | No repeats: a newer notice about the same thing replaces the older one (a host editing a game three times = one notice). New accounts start with nothing to catch up on. | Should | ✅ |
| FR-NOTIF-4 | Optional emails (Monday email, friends' and clubs' new games, reminders, announcements) have an Unsubscribe link that works without logging in, plus the List-Unsubscribe headers mail apps show a button for. The texts announcement skips people who turned off the Monday email. | Must | ✅ |
| FR-NOTIF-5 | Notices don't outlive what they're about: "Maya posted a game" goes when the game is canceled or either person blocks the other; "You down?" goes when the invite ends (unfriend, block, members-only switch, a suspended host, whose invited friends hear the invite is off). Two officers canceling at once tell players once, and a canceled game can't be edited. | Must | ✅ |
| FR-SMS-1 | Texts are optional: people can add a phone number (at sign-up step 3 or in Settings → Texts), must tick a permission box, and confirm it with a texted code. Email stays required (the UW email is the proof of being a UW student). | Should | ✅ |
| FR-SMS-2 | Confirmed, opted-in numbers get texts for game reminders (at the time each player picked), changed times/places, cancellations, invites and password-reset codes. Texts can be turned off or the number removed anytime; replying STOP is respected; texts are limited per day. | Should | ✅ |
| FR-SMS-3 | People who joined before texts (or skipped them) see a "New: game updates by text" card on Home after logging in: add a number right there, or "Not now" hides it for good. `tools/announce_texts.py` emails everyone without a number once (dry run by default). Club officers also get their club alerts by text. | Should | ✅ |
| FR-SMS-4 | A phone number belongs to one account: if two accounts ask for a code for the same number, only the first to confirm gets it. | Must | ✅ |
| FR-SET-1 | A Settings page, separate from Edit profile: notifications, look (light / dark / match my phone, also chosen at sign-up), reminder emails, password, log out, delete account. Edit profile is only about you (photo, bio, socials, sports). | Must | ✅ |

### Safety and admin (SAFE)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-SAFE-1 | Report a profile, a direct message or a chat message (a copy is saved); optionally block at the same time. The reported person isn't told who reported them. | Must | ✅ |
| FR-SAFE-2 | Admins (set by `ADMIN_EMAILS`) review reports, see people reported by 3+ others, and can suspend or restore accounts. Suspending cancels games they host and hides their profile from students. | Must | ✅ |
| FR-SAFE-3 | Admins review club registrations. | Must | ✅ |
| FR-SAFE-4 | The people who run the app (admins) show a gold 🐾 Team label on their profile, in game lists and in messages, plus a 💜 Sportive Circle Team badge. It can't be earned or faked, and goes away if someone stops being an admin. | Should | ✅ |
| FR-SAFE-5 | Admin tools hold up when busy: the report queue pages 100 at a time; two admins handling the same report don't overwrite each other ("Another admin already handled that report"); suspending a host tells every player of the canceled games, club games on hold included; it warns when they were a club's only officer, and admins can confirm that club's waiting members (the club page shows them the join requests). | Must | ✅ |
| FR-SAFE-6 | A reported message keeps a copy of its words and notes when it had a photo, so admins can tell what was reported. | Must | ✅ |
| FR-SAFE-7 | Admin tools on a phone: a suspended person's profile says so, with Restore and their photo; the only-officer warning links to each club's Officers page (which tells an admin they're managing it as admin); report actions keep the page you were on; removing one UW Rec reservation asks first. | Should | ✅ |

### Info pages (INFO)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-INFO-1 | How it works is 3 steps (Find a game, Start your own, Join a club); the FAQ has its own page behind the ? icon. | Must | ✅ |
| FR-INFO-2 | Privacy and Terms pages, linked from every page and from sign-up. | Must | ✅ |
| FR-INFO-4 | A Suggestions link in the footer: logged-in students send ideas or problems (optionally anonymous, max 5 an hour); only admins can read them. Suggestions are scanned for keywords, and admins are notified only when 3+ different people bring up the same topic within 30 days. | Should | ✅ |
| FR-INFO-5 | Suggestions: only real people count toward a trending topic (not deleted accounts), admins can page through all of them, a trend's link shows every matching suggestion from its 30 days, and invisible characters alone aren't a suggestion. | Should | ✅ |

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
| NFR-SEC-6 | Limits against abuse: code attempts, resend cooldown (with a countdown), login lockout, 10 wrong private-game passwords/hour, 20 messages/minute, 10 reports/hour, 3 pending clubs per person, length limits on every text field and search, and double-tap protection on forms. | Checked on the server (and in the browser for double taps). | ✅ |
| NFR-SEC-7 | Security headers on every response. | CSP, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `frame-ancestors 'none'`. | ✅ |
| NFR-SEC-8 | Redirects after login only go to pages on this site. | `safe_next()` blocks `//evil.com`. | ✅ |
| NFR-SEC-9 | One person can't flood others: at most 30 games posted an hour; at most 5 "posted a game" notices a day from one host to one person; spots reserved for the same friend in at most 5 games a day; "Changed" emails and texts about one game at most 3 a day per player (the bell keeps the latest). | Limits checked on the server. | ✅ |

### Privacy (NFR-PRIV)

| ID | Requirement | Status |
|---|---|---|
| NFR-PRIV-1 | Location from "Where am I?" never leaves the browser. | ✅ |
| NFR-PRIV-2 | Photo metadata is removed. | ✅ |
| NFR-PRIV-7 | Photos come out right from any phone: 16-bit grayscale and see-through PNGs too (on white). | ✅ |
| NFR-PRIV-3 | Deleting an account deletes the person's data (reports keep a copy for safety, without the reporter's name). | ✅ |
| NFR-PRIV-4 | No ads, no tracking cookies, no selling data. Only a login cookie. | ✅ |
| NFR-PRIV-5 | The database file is never committed to Git (`.gitignore`). | ✅ |
| NFR-PRIV-6 | Chats stay correct on a slow connection: one check for new messages at a time, and a message already shown is never added again. | ✅ |

### Usability and accessibility (NFR-UX)

| ID | Requirement | Status |
|---|---|---|
| NFR-UX-1 | Phone first: bottom tabs on phones and tablets, a sidebar on laptops, the same sections everywhere. CSS/JS links carry a version so phones never show an old look after an update. | ✅ |
| NFR-UX-2 | Plain, casual words: about 30 words a screen, decorative emojis only where they work as icons, no corporate tone. | ✅ |
| NFR-UX-7 | Long pages are split into clear sections by soft full-width bands; items inside a section are split by thin lines. | ✅ |
| NFR-UX-3 | Keyboard and screen-reader friendly: labels on every field, skip link, visible focus, `aria-current` on tabs, alt text rules, and text contrast of at least 4.5:1 (WCAG AA). | ✅ |
| NFR-UX-9 | Works with bigger phone text (130–160%) and at 320px: no sideways scrolling, the tab bar and top icons stay on screen. Keyboard and screen-reader users: the chat message panel keeps Tab inside and gives focus back on Esc; Esc closes a message's ⋯; a form problem is read out with its field; a "Full for now" page doesn't reload under someone using a keyboard. | ✅ |
| NFR-UX-4 | Light and dark mode; animations are skipped for "reduce motion". | ✅ |
| NFR-UX-5 | Error messages say what went wrong and how to fix it. Friendly pages for 400/403/404/405/413/500. | ✅ |
| NFR-UX-6 | Husky look and feel: UW purple and gold, paw logo, without using UW's trademarked logos or corny slogans. | ✅ |
| NFR-UX-8 | Feedback from real student testers is turned into requirements (tester session, Sept 28, 2026: FR-EVT-13 to 17, PARTY, PRIV, TEAM, PROF-6, BADGE-2, NOTIF-2). | ✅ |

### Performance and reliability (NFR-PERF)

| ID | Requirement | Status |
|---|---|---|
| NFR-PERF-1 | Pages load fast on campus Wi-Fi: no frontend framework, one small stylesheet; the map library loads only on event pages that have a map. | ✅ |
| NFR-PERF-2 | Database indexes on the common lookups (events by time, RSVPs by person, messages, club members, friendships, invites, notices). | ✅ |
| NFR-PERF-3 | No overbooking under load: joining checks capacity, held spots and team size in one statement; a party's join and holds happen in one locked transaction. | ✅ |
| NFR-PERF-4 | One failed email never blocks an action or anyone else's reminder (errors are logged). Bad input never crashes the server: 1,000+ junk requests return friendly errors. | ✅ |
| NFR-PERF-5 | SQLite is fine for thousands of students; move to PostgreSQL if the app grows well beyond one UW campus. | 🟡 |

### Maintainability (NFR-MAINT)

| ID | Requirement | Status |
|---|---|---|
| NFR-MAINT-1 | Automated tests (unit tests + Gherkin scenarios) run with one command and in GitHub Actions on every push. | ✅ |
| NFR-MAINT-2 | Sports, places and caps live in one file (`constants.py`). | ✅ |
| NFR-MAINT-3 | Database upgrades happen automatically (`ADDED_COLUMNS` in `db.py`). | ✅ |
| NFR-MAINT-4 | Small modules, one per area (auth, events, clubs, social...), with docstrings that explain *why*. | ✅ |
| NFR-MAINT-5 | Safe deploys: the two workers starting together upgrade the database one at a time (no "duplicate column" crash); the deployment guide says a new SECRET_KEY also turns off emailed Unsubscribe links, and how to restore a backup cleanly. | ✅ |

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
| NFR-LEGAL-4 | Have someone review the Privacy and Terms pages before a large public launch. | ⬜ |

---

## 4. Out of scope for now

- Push notifications (email only for now).
- Reserving courts or fields (UW Recreation handles that).
- Intramural (IM) league scores and schedules.
- Native iPhone and Android apps (the website works on phones and can be added to the home screen).
