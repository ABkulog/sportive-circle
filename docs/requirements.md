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
| FR-AUTH-3 | Users must be 18 or older (checked from date of birth; the date picker stops at 18 years ago). | Must | ✅ |
| FR-AUTH-4 | Log in with email + password. 10 wrong passwords in a row lock the account for 15 minutes. A button tapped after the login ended (Follow, Join…) sends you to log in and then back to the page it was on. | Must | ✅ |
| FR-AUTH-5 | "Forgot password?" emails a code to set a new password, and never reveals whether an email has an account. | Must | ✅ |
| FR-AUTH-6 | Logged-in users can change their password (current password required). | Must | ✅ |
| FR-AUTH-7 | Users can delete their account after an "Are you sure?" page, typing DELETE, and their password. A club's only officer must hand over first, also when an admin has taken the club off the list for a re-check (its members are still in it). | Must | ✅ |
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
| FR-EVT-25 | A game can only be posted (or moved, or posted from Need players, or repeated weekly) while its place is open: the IMA and its rooms, the IMA Pool, the South tennis courts (lights off), Fitness Center West, the golf range, the WAC and the Green Lake courts have their posted hours by weekday and season (`PLACE_HOURS` in constants.py, with sources). The form shows the hours for the picked place and date. Places with no posted hours (fields, the Quad, Red Square, the trail) have no limit. | ✅ |
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
| FR-PARTY-9 | Members-only games: Reserve spots and Send to friends only offer club members. Invite links: a link stops advertising the game once its sender left or was taken off; a members-only link shows outsiders only "A club members' event"; a blocked person's link doesn't open. | ✅ |
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

### The feed (FEED)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-FEED-8 | Posts have 🔥 (one per person, tap again to take it back) and replies (up to 500 characters, 30 an hour), shown under the post on its own page; the feed shows both counts. The author gets one bell notice per post for 🔥 and one for replies, updated as more come in. Replies can be reported; the reply's author, the post's author or an admin can delete it. Replies from blocked or suspended people are hidden and not counted. | Must | ✅ |
| FR-FEED-9 | Husky news in the feed: headlines, scores and results from UW's Division I teams in your sports (GoHuskies.com's public RSS feeds, only gohuskies.com links), opening on GoHuskies.com. Downloaded in the background at most every 30 minutes, so the feed never waits on it, and the last stories stay if GoHuskies is down. Department-wide news shows in the full feed, not in sport channels. | Should | ✅ |
| FR-FEED-10 | A post can have one video instead of photos: MP4 or a phone's QuickTime video, up to 1 minute (checked in the browser and on the server from the file's own header) and 60 MB. GPS coordinates in the file are overwritten with zeros. Videos stream with seeking, only for people who can see the post, and their files are deleted with the post or the account. All videos together stay under a quota (VIDEO_QUOTA_MB, default 300 MB) so they can't fill the disk the database is on; when it's full, people are told to post photos. | Should | ✅ |
| FR-FEED-11 | Profiles show the person's latest posts (any sport), like an athlete profile, not to people they blocked or who blocked them. Feed photos swipe in place (they don't open the raw image). | Should | ✅ |
| FR-FEED-12 | The post box is one line (your picture, "Who's down?", **Post**) until it's tapped; then the sport, photos, video and **Make it a plan** open. Under the sport it says who sees the post ("#basketball: everyone who plays Basketball sees it, and it's in the Basketball channel"). The channel row starts with **All** (every sport you picked); each post goes to one sport's channel. The sport tag sits next to the time on each card. | Must | ✅ |
| FR-FEED-13 | A plan in a post is checked exactly like Create a game (events.read_event_form): only that sport's places are listed and accepted, opening hours, the sport's longest length, the clocks changing, skill level and who it's open to; the place's tips, hours, "check you can use the courts" and what's on there then show as on the game form. | Must | ✅ |
| FR-FEED-14 | The feed is only for posts (people's posts and plans, clubs' posts and updates, Husky news). Games people post on their own are on **Play**, not in the feed (a "New games" row there was out of place). | Must | ✅ |
| FR-FEED-15 | **Pull to refresh** on the feed and My clubs: pulling down from the top shows "↓ Pull to refresh" / "↻ Let go to refresh" and reloads; the phone's own pull-to-refresh is off there, and a post being typed is never thrown away. | Should | ✅ |
| FR-FEED-16 | Nothing on the feed, a post's page or My clubs scrolls sideways on a 320px phone: the one-line post box, a card's 🔥 / Reply / Report / Delete row (it wraps) and **Reply as** all fit. | Must | ✅ |
| FR-FEED-17 | 🔥, replies (and deleting one), Follow, I'm in and deleting a post happen **in place**: sent in the background, only that card (or the replies) changes, the page doesn't reload or jump, and messages show as a toast that fades. Without JavaScript they work as normal forms. | Must | ✅ |
| FR-FEED-18 | Calm cards: each card shows only 🔥 and Reply; Report and Delete are behind a **⋯** menu. A club's card has **Follow** in its top corner (when you don't follow it) and one line, "📅 Events & info →", to the club page. | Must | ✅ |
| FR-FEED-19 | The feed's top is tidy: one **sport picker** ("All my sports", your sports, other sports) instead of a sideways row of sport chips; the one-line post box says just "Who's down?"; the Help bubble isn't shown on the feed, a post, All clubs or My clubs (it covered posts; Help is in the top bar). | Must | ✅ |
| FR-FEED-20 | On phones the Feed / Play / My events tabs (and the club tabs) stay just under the header while scrolling, instead of sliding under it. Play's "Showing …" line names up to 3 sports, otherwise "Showing your 52 sports · Change sports". The Help bubble is only for visitors who aren't logged in (logged-in people have the ? in the top bar). | Must | ✅ |
| FR-FEED-21 | Posting never reloads the page: the post box (feed, My clubs, a club's page) sends in the background, the new post appears at the top of the list under it, and the box empties and closes (a refused post keeps what you wrote, with the reason as a toast). **💬** opens the replies inside the card on the feed (tap again to close), replying there updates the replies and the 💬 number in place. | Must | ✅ |
| FR-FEED-22 | Even spacing: the post box, Clubs for you and every post on the feed and My clubs are 12px apart; the post box never touches the first post, whatever kind of post that is. | Must | ✅ |
| FR-FEED-23 | The opened post box closes back to one line when you tap anywhere else or scroll it out of sight; what you wrote, picked photos and the plan stay in it. Posts are compact so more fit on a screen: smaller text and padding, photos at most 340px tall (300px each in a swipeable row on wide screens). | Must | ✅ |
| FR-NAV-1 | Like Instagram: **5 places**, the same on phones (bottom bar) and laptops (sidebar): Home (the feed), Clubs (where Instagram's search is), Search (where its + is), Play (where Reels is), Profile. The 🔔 bell (where Instagram's heart is) and Messages sit top right on phones (in the sidebar on laptops). A **＋** button at the bottom right of every page (not over chats or forms) opens the **New post** sheet; posting, ×, a tap outside or Esc closes it, with no reload. No second row of tabs anywhere. Friends, Settings, Help and Log out are on your Profile, and Admin is tucked into Settings (admins only); your clubs (My clubs, Find a club) and your games are in its tabs. Badges for friend requests, clubs and admin show on Profile. | Must | ✅ |
| FR-NAV-2 | Profiles are like a Twitter profile: photo, name, bio, a few sports ("+12 more"), then tabs with **Posts** first, then Clubs, Games, Badges. | Must | ✅ |
| FR-FEED-24 | The feed's top is two menus side by side: sport (All my sports, …) and from whom (**Everyone**, **All clubs**, **My clubs**); no big title or greeting. The post box says "What's happening?" with **📷 Photo** and **🏀 Plan a game** under it. The old All clubs page sends you to the feed's All clubs. | Must | ✅ |
| FR-FEED-25 | Every card follows one pattern (avatar, name, time, #sport, content, reactions); clubs only add the verified mark. A new club is one short line. A plan's game is named from the sport and place ("Basketball at the IMA") so it doesn't repeat the post. Plans and club events whose game was canceled leave the feed. Photos fill the card's width, rounded, at most 340px tall. | Must | ✅ |
| FR-NAV-3 | One way to make each thing: a post is the **＋** button; a game is **＋ New game** on Play (one form: pick a time, or **Right now / In 30 min / In 1 hour** for a pickup game; the old Need players page goes there); a club is **＋ Register a club** on Clubs; a club event is **+ Club event** on the club's page. The old Create page goes to Clubs. | Must | ✅ |
| FR-NAV-7 | The **Clubs** tab is the clubs section: search clubs, **＋ Register a club**, chips for **All · My clubs · My sports** (clubs for the sports on your profile) and any sport, the quick filters, and clubs as compact rows (logo, name, one line, badges). | Must | ✅ |
| FR-NAV-4 | **Search** (🔍 in the top bar, and in the sidebar) finds verified clubs (by name, description or sport) and people (by name or NetID) in one box; clubs are found like accounts you follow. | Must | ✅ |
| FR-NAV-5 | **Play** is a live map, like Snap Map, above the list of games: a quiet grey campus map with a sport bubble for each place where something's on **right now**: starting within an hour ("in 20 min"), going on ("Live", pulsing), or ended in the last 10 minutes ("Ended", faded). Tap a bubble for its games. Same visibility rules as the list. "Nothing on right now" when empty. No big title, no Clubs for you strip. | Must | ✅ |
| FR-FEED-26 | The feed's top is **one row of chips**, one choice at a time: **All** (everything, club posts included), **My clubs**, 2 of your sports, and **More ▾** for any other sport. They wrap rather than scroll sideways. | Must | ✅ |
| FR-FEED-27 | Media in posts is small: photos are 92px squares (104px on wide screens), up to 4 shown with "+N" on the last; tapping one opens it full screen (swipe / arrows / ← → through the post's photos; ×, Esc or a tap outside closes). A video is a small tile (200px wide) that plays in place with a small see-through ▶ / ❚❚ button at its bottom-left; tapping the video opens it full screen. Cards are tighter (32px picture). | Must | ✅ |
| FR-NAV-6 | Play has no greeting. Its live map centers on campus (or its bubbles) once the page has its final size, and re-centers if the width changes (it used to land ~2 km west); with nothing on, the map is smaller and says why. | Must | ✅ |
| FR-NAV-8 | Long lists can be searched: a small **Search** box sits above every long dropdown (sports, places) and above the sports chips (sign-up, Your sports). Typing "ten" leaves Table Tennis and Tennis; a single match is picked for you (except in filters that apply at once); your current pick and ticked sports always stay; the box hides when the list is short. | Should | ✅ |
| FR-NAV-9 | The ＋ button never hides the end of a page: the footer has room under it (phones and laptops), and short link rows (My clubs: Find a club · Manage my clubs) wrap instead of overlapping at 320px. | Should | ✅ |
| FR-NAV-10 | Play's map is like Snap Map: a big, colorful preview at the top of Play (a still picture, so scrolling never drags it) with "N places with games now" and **Tap to open the map**. Tapping opens it **full screen** (drag, zoom, tap a bubble) with **← Back**, a ◎ back-to-campus button, and the phone's back button / Esc closing it. | Must | ✅ |
| FR-FEED-28 | On phones, posts are flat rows like Twitter: no boxes, a thin line between posts, name · time · #sport on one line next to a small picture, the text under the name, 72 px photo squares and plain 🔥 / 💬. | Must | ✅ |
| FR-ADMIN-1 | **Admin → Clean up test data** lists posts, replies, clubs and club updates that look like keyboard mashing (5+ consonants in a row, or an 18+ letter word), ticked, or everything with **Show everything**; **Delete ticked** removes them (a club with its posts and games, videos' files too) after a confirm. | Must | ✅ |
| FR-PLACE-1 | **Off campus: 📍 Where exactly?** (game form, Need players, plans in posts; shown only when Off campus is picked): **Drop a pin** (tap a map, drag to adjust; the map only loads when tapped), **Use my location**, or type an address / paste a Google Maps or Apple Maps link (coordinates are read from the link; short share links are kept and opened as they are; other websites are refused). The game page shows the pin with **Google Maps** and **Apple Maps** directions (or opens the address or link in either app), and Play's live map shows the game at its own spot. Kept when editing. | Must | ✅ |
| FR-CLUB-32 | Clubs have their own feeds: **All clubs** (what every verified club posts, where the Clubs tab opens), **My clubs** (just the clubs you're in or follow) and **Find a club** (the list). Club posts still reach the main feed too. | Must | ✅ |
| FR-CLUB-33 | Asking to join is one clear form: **Request to join** turns into the form itself (the club's question, **Send** and **Cancel**); while it's open, Follow is hidden so following can't throw away a half-written request. Follow / Unfollow happen in place (no reload). The "Follow vs member" tip only shows before you've followed or asked to join. After asking, the page says you'll see the club's updates while you wait. | Must | ✅ |
| FR-CLUB-31 | **My clubs** shows what your clubs posted (their feed posts with photos, 🔥 and replies, and their updates and event posts), newest first; officers post there as the club (words and photos), which also reaches everyone's feed. | Must | ✅ |
| FR-FEED-7 | One job per page: **Feed** (what's happening; new games are short announcements there), **Play** ("Find a game": every game with filters), **My events** (your schedule); **Find a club** (finding) and **My clubs** (your clubs, with officers' waiting-to-join counts). Page titles say each page's job. | Must | ✅ |
| FR-FEED-1 | Home opens on the **Feed**: posts, club updates and club events, and newly posted games for the sports you picked, newest first (your own posts always show). **Games** and **My events** are the next tabs. | Must | ✅ |
| FR-FEED-2 | Every post has a sport tag. Tapping a tag (or a sport chip at the top) shows that sport only, like a channel; anyone can open any sport's channel. | Must | ✅ |
| FR-FEED-3 | A post has words (up to 1000 characters) and/or up to 10 photos, which are shrunk and stripped of hidden data (like GPS) and only shown to people logged in who can see the post. Up to 10 posts an hour. | Must | ✅ |
| FR-FEED-4 | "Make it a plan" (when, how long, where, how many people) turns a post into a real game behind the scenes, checked like any game (the place fits the sport, it's open then, it's in the future, within 60 days). The post shows the headcount and an **I'm in** button; the game gets the usual chat and reminders and isn't shown a second time in the feed. | Must | ✅ |
| FR-FEED-5 | Posts by people you blocked (or who blocked you) and by suspended people never show. Anyone can report a post (admins see it as "Feed post", with a link to it); the author or an admin can delete it, with its photos. Deleting a plan's post keeps its game. | Must | ✅ |
| FR-FEED-6 | Club posts in the feed show the club (logo, name, ✓) and a **+ Follow** button for clubs you don't follow yet, which keeps you on the feed. A Community rules page is linked from the composer: physique and progress photos are welcome; nudity and sexual content are not. | Must | ✅ |

### Clubs (CLUB)

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-CLUB-1 | Only officers can register a club. A social media account or a website is required, either one or both (how admins check it's real); and the HuskyLink / UW Recreation page isn't asked (people put their website there and got stuck). | Must | ✅ |
| FR-CLUB-2 | A club is only public after an admin approves it. Changing a live club's name or kind sends it back for a quick check (the edit form warns first); fixing capitals or spaces doesn't. Rejections include a note on what to fix. Denying a club as spam frees its name (it's kept as "Name (denied #id)"), so a squatter can't keep the real club from registering; restoring gives the name back if it's still free. | Must | ✅ |
| FR-CLUB-3 | Anyone (even logged out) can browse verified clubs and search or filter them (sport, beginner-friendly, free, no tryouts). "Free" finds the ways officers write it ("Free!", "$0", "None", "No dues"), not dues with a price in them. | Must | ✅ |
| FR-CLUB-4 | Students can follow a club, or request to join / apply / sign up for tryouts. They're a member only after an officer confirms them. | Must | ✅ |
| FR-CLUB-5 | Officers can post updates, create club events, confirm or decline people, remove members and add officers. | Must | ✅ |
| FR-CLUB-6 | Students can message a club's officers before joining. | Should | ✅ |
| FR-CLUB-7 | Officers upload the club's logo (square, 256 px); it shows on the club page, in the club list, on Home and in Club updates. | Should | ✅ |
| FR-CLUB-8 | Every verified club has a Share page with its link and a printable QR code ("Scan to join") for flyers and the involvement fair. | Should | ✅ |
| FR-CLUB-9 | Club events can repeat weekly (up to 12 weeks, for practices) and can be for members only (only members see them in their feed or can join; others see "Join the club"). | Must | ✅ |
| FR-CLUB-10 | A new club event is posted to the club's updates automatically, with a link, so followers and members hear about it. | Should | ✅ |
| FR-CLUB-11 | Officers see members' UW emails, can copy them all and download the roster as a spreadsheet (CSV). Members don't see each other's emails. | Should | ✅ |
| FR-CLUB-12 | The person who registered a club is its owner: only they add officers (searching anyone on the app by name or UW NetID, on Manage officers) or take officer rights away; they always stay an officer. Other officers edit the club, post, make club events and confirm members. The owner can hand the club to another officer (Make owner); they stay an officer. If the owner is no longer an officer, any officer can manage officers. | Must | ✅ |
| FR-CLUB-13 | Club events belong to the club: any current officer can edit or cancel them and take players off, and an officer who leaves or steps down can't anymore. Their upcoming club events go to another active officer (the owner first) when they step down, leave the club, are suspended or delete their account, instead of being canceled or deleted; they stay in as a player and can leave. With no other active officer, the old rules apply. Someone who leaves the club or is removed is taken out of its upcoming members-only events (they stop seeing the note, players and chat). | Must | ✅ |
| FR-CLUB-14 | Weekly practices: the last week must be within a year. Turning a club event members-only takes people who aren't members off it (they're told). When another officer edits or cancels a club event, players hear it from that officer and the host is told too. A club going back to review sends each person one on-hold notice, not one per week. | Must | ✅ |
| FR-CLUB-15 | A club always has an owner it can use: when the owner deletes their account the longest-serving active officer becomes owner, and an ownerless older club can still be handed to an officer. Suspended officers don't count as "another officer". Officer changes happen one at a time, so two officers removing each other can't leave none. "Make officer" respects blocks both ways. | ✅ |
| FR-CLUB-16 | Canceling a join request or tryout keeps you following (like a decline). A blocked person's join request doesn't email or text the officer involved. Suspended people's names leave old club posts ("An officer"), requests and counts. | ✅ |
| FR-CLUB-17 | Club event posts stay true: a canceled event's post says "Canceled:", a weekly series' post keeps describing the series after edits, and private events don't push open ones off the club page. | ✅ |
| FR-CLUB-18 | Deleting an account steps down from every club first, in one locked step, so two officers deleting at once can't leave a club with none; a club whose other officer is suspended is kept. A canceled club event's post says "Canceled:" however it was canceled (by an officer, a suspension, a denied club, a deleted account). Editing one week of a series doesn't rewrite the series' post unless who it's for changes; older series posts get their week count back. | ✅ |
| FR-CLUB-19 | The club directory counts only games the club page shows (not private or full ones), finds clubs by sport name ("skiing"), and sorts A–Z ignoring capitals and accents. People waiting on a join request still hear about the club's new games. | ✅ |
| FR-CLUB-20 | A club waiting for verification isn't a dead end: its page shows Manage officers (to the owner), says the link and QR code will be ready once it's verified, and the owner can withdraw the request while nobody else has joined. | Should | ✅ |
| FR-CLUB-21 | The Clubs tab's **My clubs** page shows a row of your clubs (with Officer / Member / Following), what's coming up in them (open events, members-only ones if you're a member) and their posts. With no clubs it suggests clubs for your sports. | Must | ✅ |
| FR-CLUB-22 | Profiles show the verified clubs someone is a member or officer of (officers marked), not to people they blocked or who blocked them; your own profile links to Find clubs. | Should | ✅ |
| FR-CLUB-23 | A club's first approval posts "🆕 <club> just joined Sportive Circle!" with its description, which everyone who plays its sport sees in the feed (once, even if it's approved again after a re-check). | Should | ✅ |
| FR-CLUB-24 | The feed shows **Clubs for you** (clubs for your sports, with **+ Follow**) until you follow or join any club. | Should | ✅ |
| FR-CLUB-25 | Officers can mark a club event as a **Try-it-out session** (open events only): its post says "👋 Try it out, new people welcome!", and the event shows "New people welcome" on Play and in the feed. | Should | ✅ |
| FR-CLUB-26 | A club's page and its posts in the feed say which of your friends follow or are in it ("Your friends Maya and 2 others are in this club"), when you aren't a member yet. | Should | ✅ |
| FR-CLUB-27 | Officers see **This week** on their club page: new followers or members, people waiting to join, people going to its events (last and next 7 days) and posts, with a nudge to post when there were none. | Should | ✅ |
| FR-CLUB-28 | Officers post **as the club** from the feed composer (**Post as**) or the club page: words, up to 10 photos or a video, 🔥, replies and plans like anyone's post. A club's plan is a club event (it's on the club page). Club posts reach **everyone's** feed (not only followers), and a sport's channel shows its clubs' posts; club updates and event posts from every verified club also reach the whole feed. A club's posts stay off the officer's own profile, hide while the club isn't verified, and any of its officers can delete them. | Must | ✅ |
| FR-CLUB-29 | Officers **reply as the club** (**Reply as**); the reply shows the club's logo, name and verified mark and links to the club, and the post's author is told "UW Run Club replied". Any of the club's officers can delete its replies. | Must | ✅ |
| FR-CLUB-30 | Verified clubs carry the **verified club mark** (a purple seal with a check) next to their name in the feed, replies and on their page, and their feed cards have a purple edge plus **📅 Events**, **ℹ️ Info & joining** and **+ Follow** buttons that open the club page's Events and About tabs. | Must | ✅ |
| FR-CLUB-31 | A club **pins** one of its posts to the top of its page for **24 hours** (⋯ → 📌 Pin for 24 hours; one pin at a time, ⋯ → Unpin), shown with "📌 Pinned". Only people who can post as the club pin; it happens in place. | Should | ✅ |
| FR-CLUB-32 | **Posting as the club is a permission the owner gives**: on Manage officers each officer has **Posts: On / Off** (they get a message when it's turned on). The owner always can post; officers made from now on start with it off, and officers from before keep posting. Officers without it see "The owner picks which officers post as the club" instead of the post box, and can't post or reply as the club. | Must | ✅ |
| FR-CLUB-33 | **Members follow the club**: the followers count includes members, officers and people waiting to join, and leaving the club keeps you following it ("You still follow it"); unfollowing is one more tap. | Must | ✅ |

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
| FR-SOC-11 | Hold one of your own messages (DM or game chat) and tap **Delete** to delete it for everyone: its words, photo, game card and reactions are gone and it shows "🚫 Message deleted" in its place, for the other person too on their next check (and in the inbox preview). A report made before keeps its saved copy. | Should | ✅ |

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
| NFR-SEC-9 | One person can't flood others: at most 60 games posted an hour (checked one post at a time, so two tabs can't both slip under it); at most 5 "posted a game" notices a day from one host to one person; spots reserved for the same friend in at most 5 games a day (renewing a spot in the same game doesn't count again); "Changed" emails and texts about one game at most 6 a day per player (the bell keeps the latest, and the host is told not everyone got another email). | Limits checked on the server. | ✅ |
| NFR-SEC-10 | Texts can't crowd each other out: at most 20 update texts a day, with game changes, cancels and reminders getting their own 20; at most 3 "You down?" texts a day from one friend; only texts that really went out count; a STOP reply is explained in Settings → Texts (text START back, then turn texts on). | Limits checked on the server. | ✅ |

### Privacy (NFR-PRIV)

| ID | Requirement | Status |
|---|---|---|
| NFR-PRIV-1 | Location from "Where am I?" never leaves the browser. | ✅ |
| NFR-PRIV-2 | Photo metadata is removed. | ✅ |
| NFR-PRIV-7 | Photos come out right from any phone: 16-bit grayscale and see-through PNGs too (on white). | ✅ |
| NFR-PRIV-8 | A club's public page and updates never show when or where a private or members-only club event is, including after an edit makes it so; a members-only game's page, map and "Send to friends" are for members, its host and players; game cards in chats stop showing the place once a game is private or members-only. | ✅ |
| NFR-PRIV-9 | Checking whether a number is already on the app costs a code try (5 a day), so nobody can look numbers up for free. | ✅ |
| NFR-PRIV-10 | A check on a number that's already taken costs the person checking, never that number's own owner (they can still get their codes). | ✅ |
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
| NFR-UX-10 | Nothing typed is lost on a bad connection: chat keeps words typed while a message sends, gives up on a stuck send after 20 seconds with a message, and doesn't reload over a draft when logged out elsewhere; Settings switches say "Couldn't save" offline and flip back. Chat waits for the Enter that finishes Japanese/Chinese/Korean typing; the photo viewer keeps keyboard focus and gives it back. | ✅ |
| NFR-UX-11 | Forms say what's missing early: the new-game wizard asks for a sport on step 1; Need players warns when there's nobody left to find; "Maybe later" after sign-up hides the home-screen card; an invite link for a game that's over says so; the "You replied STOP" note goes away with a new number. | ✅ |
| NFR-UX-12 | A chat message is never posted twice: a slow send (20 s, or 90 s with a photo) checks the chat before saying it didn't go; being logged out elsewhere keeps the typed message. | ✅ |
| NFR-UX-13 | Notices and messages stay true: friends' "posted a game" notice shows the new time after an edit and goes away if the game turns private; change texts say what changed; the Monday email and Need players count skip games the host took you off; the bell lists every game chat it counts; full posts can't push open ones out of the Need players strip; Messages search looks past the first 20 matches before keeping people you can message; an invite link says when the friend who sent it left the game. | ✅ |
| NFR-UX-14 | Emails carry a plain List-Unsubscribe link (Gmail/Yahoo one-click), a Date and a Message-ID. | ✅ |
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
