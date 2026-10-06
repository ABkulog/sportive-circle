// Keeps the "Location" list and the "Participants" number in sync with the chosen sport.
// The server checks the same rules (constants.py), so this is only for convenience.
(function () {
  const rulesElement = document.getElementById("sport-rules");
  const form = document.querySelector("form[data-sport-form]");
  if (!rulesElement || !form) return;

  const rules = JSON.parse(rulesElement.textContent);
  const sport = form.querySelector('select[name="sport"]');
  const location = form.querySelector('select[name="location"]');
  const placeholder = location.options[0];
  const everyPlace = Array.from(location.options).slice(1).map((option) => option.value);
  const players = form.querySelector("[data-players]");
  const placeTip = form.querySelector("[data-place-tip]");
  let lastSport = sport.value;

  function updatePlaces() {
    const rule = rules[sport.value];
    const allowed = rule ? rule.locations : everyPlace;
    const current = location.value;
    location.replaceChildren(placeholder, ...allowed.map((place) => new Option(place, place, false, place === current)));
    if (allowed.length === 1) location.value = allowed[0];
    else if (!allowed.includes(current)) location.value = "";
  }

  // "Participants": any number the host needs. Picking another sport suggests its usual size (5v5 basketball = 10),
  // unless the host already typed their own number.
  let typedPlayers = false;
  if (players) players.addEventListener("input", () => { typedPlayers = true; });
  function updatePlayers() {
    const rule = rules[sport.value];
    if (!players || !rule) return;
    if (sport.value !== lastSport && !typedPlayers) players.value = String(rule.default);
    lastSport = sport.value;
  }

  // Good-to-know details for this sport at this place (e.g. "Indoor pickleball is in Gym B, Thursdays 2-5 PM").
  function updateTip() {
    if (!placeTip) return;
    const rule = rules[sport.value];
    placeTip.textContent = (rule && rule.tips[location.value])
      || (location.value.startsWith("Off campus") ? "Add where in the note, so people can find you." : "");
  }

  // "Heads up: check you can use the courts/field/trail then": the word follows the sport.
  const space = form.querySelector("[data-place-space]");
  function updateSpace() {
    const rule = rules[sport.value];
    if (space) space.textContent = rule ? rule.space : "place";
  }

  sport.addEventListener("change", () => { updatePlaces(); updatePlayers(); updateTip(); updateSpace(); });
  location.addEventListener("change", updateTip);
  updatePlaces();
  updatePlayers();
  updateTip();
  updateSpace();
})();

// "No limit": the number box switches off (and isn't sent) while it's ticked.
(function () {
  const box = document.querySelector("[data-no-limit]");
  const players = document.querySelector("[data-players]");
  if (!box || !players) return;
  const update = () => { players.disabled = box.checked; };
  box.addEventListener("change", update);
  update();
})();

// "You + 2 friends = 3 of 10 · need 7 more": the math for the "Who's coming?" part, as you tick friends.
(function () {
  const form = document.querySelector("form[data-sport-form]");
  const math = form && form.querySelector("[data-player-math]");
  if (!math) return;
  const players = form.querySelector("[data-players]");
  const teamSize = form.querySelector("[data-team-size]");
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  function update() {
    const friends = form.querySelectorAll('input[name="reserve"]:checked').length;
    const team = teamSize && !teamSize.disabled ? parseInt(teamSize.value, 10) : 0;
    if (team) {
      const mine = 1 + friends;
      math.textContent = `Your team: you${friends ? ` + ${plural(friends, "friend")}` : ""} = ${mine} of ${team}`
        + (mine > team ? ` · that's ${mine - team} too many` : "");
      return;
    }
    const coming = 1 + friends;
    let text = "You";
    if (friends) text += ` + ${plural(friends, "friend")}`;
    if (players && players.disabled) {  // "No limit"
      math.textContent = `${text} = ${coming} going · no limit`;
      math.classList.remove("is-over");
      return;
    }
    const total = parseInt(players && players.value, 10) || 0;
    text += ` = ${coming} of ${total}`;
    const need = total - coming;
    // On Need players, "full" means there's nobody left to find, which can't be posted: warn like "too many".
    const findingNobody = need === 0 && form.hasAttribute("data-need-players");
    text += need > 0 ? ` · need ${need} more` : findingNobody ? " · nobody left to find, so add more players"
      : need === 0 ? " · full" : ` · that's ${-need} too many`;
    math.textContent = text;
    math.classList.toggle("is-over", need < 0 || findingNobody);
  }
  form.addEventListener("change", update);
  form.addEventListener("input", update);
  update();
})();

// Who can join / Format: show only what makes sense (see the data-show notes in _macros.html).
// Hidden parts are switched off too, so their values are never sent and can't block the form.
(function () {
  const form = document.querySelector("form[data-sport-form]");
  if (!form) return;
  const card = form.closest(".card") || document;
  const privateRadio = form.querySelector('input[name="is_private"][value="1"]');
  const teamSize = form.querySelector("[data-team-size]");
  const teamField = form.querySelector("[data-team-field]");
  const sport = form.querySelector('select[name="sport"]');
  const rulesElement = document.getElementById("sport-rules");
  const rules = rulesElement ? JSON.parse(rulesElement.textContent) : {};
  const regularOption = teamSize ? teamSize.options[0] : null;

  function updateSizes() {
    if (!teamSize) return;
    const sizes = (rules[sport.value] && rules[sport.value].teams) || [];
    const current = teamSize.value;
    teamSize.replaceChildren(regularOption,
      ...sizes.map((n) => new Option(`${n}v${n} team vs team`, n, false, String(n) === current)));
    if (!sizes.map(String).includes(current)) teamSize.value = "";
  }

  function apply() {
    const isPrivate = Boolean(privateRadio && privateRadio.checked);
    if (isPrivate && teamSize) teamSize.value = "";  // team vs team is for open games
    const isTeam = teamSize ? Boolean(teamSize.value) : form.hasAttribute("data-team-game");
    const on = { public: !isPrivate, private: isPrivate, crowd: !isPrivate && !isTeam, regular: !isTeam };
    card.querySelectorAll("[data-show]").forEach((element) => {
      const show = element.dataset.show.split(" ").every((rule) => on[rule]);
      element.hidden = !show;
      const noLimit = form.querySelector("[data-no-limit]");
      element.querySelectorAll("input, select, textarea").forEach((input) => {
        // The number box stays off while "No limit" is ticked.
        input.disabled = !show || (input.matches("[data-players]") && Boolean(noLimit && noLimit.checked));
      });
    });
    if (teamField) {
      const sizes = (rules[sport.value] && rules[sport.value].teams) || [];
      if (!sizes.length) { teamField.hidden = true; teamSize.disabled = true; }
    }
    const password = form.querySelector('input[name="password"]');
    if (password) password.required = isPrivate;
  }

  form.querySelectorAll('input[name="is_private"]').forEach((radio) => radio.addEventListener("change", apply));
  if (teamSize) teamSize.addEventListener("change", apply);
  if (sport) sport.addEventListener("change", () => { updateSizes(); apply(); });
  updateSizes();
  apply();
})();

// "Ends" follows "Starts": pick a new start time and the end moves with it, keeping the game's length
// (1 hour for a new game, or whatever length the host set). The server still checks the times.
(function () {
  const form = document.querySelector("form[data-sport-form]");
  const starts = form && form.querySelector('input[name="starts_at"]');
  const ends = form && form.querySelector('input[name="ends_at"]');
  if (!starts || !ends) return;
  const HOUR = 60 * 60 * 1000;
  // datetime-local values are wall-clock times ("2026-09-30T18:00"): read and write them as local time.
  // Done in UTC so the night the clocks change can't stretch or shrink a game: 1:30 + 1 hour is always 2:30.
  const read = (input) => { const t = Date.parse(input.value + "Z"); return Number.isNaN(t) ? null : t; };
  const write = (input, time) => { input.value = new Date(time).toISOString().slice(0, 16); };
  const gap = () => {
    const s = read(starts), e = read(ends);
    return s !== null && e !== null && e > s ? e - s : HOUR;
  };
  let length = gap();
  starts.addEventListener("input", () => {
    const s = read(starts);
    if (s === null) return;
    write(ends, s + length);
    ends.min = starts.value;
  });
  // A host who sets their own end time keeps that length for the next start change.
  ends.addEventListener("change", () => { length = gap(); });
  if (starts.value) ends.min = starts.value;
})();

// "What's on there then": as the host picks a place and time, show UW Rec reservations (the place is taken)
// and other Sportive Circle games (the place is busy, not taken: they can still post). Built with textContent.
(function () {
  const form = document.querySelector("form[data-sport-form]");
  const box = form && form.querySelector("[data-whats-on]");
  if (!box) return;
  const location = form.querySelector('select[name="location"]');
  const startsAt = form.querySelector('input[name="starts_at"]');
  const endsAt = form.querySelector('input[name="ends_at"]');
  const startsIn = form.querySelector('select[name="starts_in"]');   // Need players: "in 30 min"...
  const duration = form.querySelector('select[name="duration"]');    // ...for "1 hour"
  // "In 30 min" as a Seattle clock time (the game's time), even on a phone set to New York or Seoul.
  const seattleClock = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles", year: "numeric",
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const local = (d) => {
    const part = Object.fromEntries(seattleClock.formatToParts(d).map((p) => [p.type, p.value]));
    return `${part.year}-${part.month}-${part.day}T${part.hour}:${part.minute}`;
  };

  function times() {
    if (startsAt && endsAt) return [startsAt.value, endsAt.value];
    if (startsAt && duration) {  // a plan in a feed post: a start and "How long"
      const start = Date.parse(startsAt.value + "Z");
      if (Number.isNaN(start)) return [null, null];
      return [startsAt.value, new Date(start + Number(duration.value) * 60000).toISOString().slice(0, 16)];
    }
    if (!startsIn || !duration) return [null, null];
    const start = new Date(Date.now() + Number(startsIn.value) * 60000);
    return [local(start), local(new Date(start.getTime() + Number(duration.value) * 60000))];
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function show(info) {
    box.replaceChildren();
    if (!info) { box.hidden = true; return; }
    info.reserved.forEach((r) => {
      const line = el("p", "whats-on-rec");
      line.append(el("strong", "", "UW Rec: reserved "), `${r.when}`, ` · ${r.label}. You probably can't play there then.`);
      box.appendChild(line);
    });
    if (info.uw_rec) {
      const line = el("p", "muted");
      if (info.beyond_copy) line.append("We only copy UW Rec's schedule 4 weeks ahead, so we can't tell yet. ");
      else if (!info.reserved.length) line.append("No UW Rec reservations we know of then. ");
      const link = el("a", "", "Check UW Rec's schedule");
      link.href = info.schedule; link.target = "_blank"; link.rel = "noopener";
      line.append(link);
      box.appendChild(line);
    }
    if (info.games.length) {
      box.appendChild(el("p", "whats-on-title", "Also on Sportive Circle there then:"));
      const list = el("ul", "whats-on-games");
      info.games.forEach((game) => {
        const item = el("li");
        const name = game.url ? el("a", "", game.title) : el("span", "", game.title);
        if (game.url) { name.href = game.url; name.target = "_blank"; }
        item.append(name, ` · ${game.when}` + (game.going == null ? "" : ` · ${game.going}${game.max ? "/" + game.max : ""} going`));
        list.appendChild(item);
      });
      box.appendChild(list);
      box.appendChild(el("p", "muted", "You can still post: games can share a place, and there may be room to join theirs instead."));
    }
    box.hidden = !box.childNodes.length;
  }

  let timer = null;
  let asked = 0;
  function check() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const [starts, ends] = times();
      if (!location.value || !starts || !ends) { ++asked; show(null); return; }  // and ignore older answers
      const params = new URLSearchParams({ location: location.value, starts_at: starts, ends_at: ends });
      if (form.dataset.eventId) params.set("event", form.dataset.eventId);
      const ticket = ++asked;
      try {
        const response = await fetch(`${box.dataset.url}?${params}`, { headers: { Accept: "application/json" } });
        if (ticket === asked && response.ok) show(await response.json());
      } catch (error) { /* offline: no heads-up, the form still works */ }
    }, 300);
  }
  [location, startsAt, endsAt, startsIn, duration].forEach((input) => {
    if (input) { input.addEventListener("change", check); input.addEventListener("input", check); }
  });
  form.querySelector('select[name="sport"]')?.addEventListener("change", check);  // the place list changes with it
  check();
})();

// "Open 9:00 AM – 8:30 PM on Saturdays" under the place, for the date picked (Need players: today), so the host
// picks a time while the place is open. The server checks the same hours (placehours.py).
(function () {
  const hoursElement = document.getElementById("place-hours");
  const form = document.querySelector("form[data-sport-form]");
  const line = form && form.querySelector("[data-place-hours]");
  if (!hoursElement || !line) return;
  const hours = JSON.parse(hoursElement.textContent);
  const location = form.querySelector('select[name="location"]');
  const starts = form.querySelector('[name="starts_at"]');
  const days = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"];
  const clock = (text) => {
    const [hour, minute] = text.split(":").map(Number);
    return `${(hour % 12) || 12}:${String(minute).padStart(2, "0")} ${hour < 12 ? "AM" : "PM"}`;
  };
  function update() {
    const seasons = hours[location.value];
    const picked = starts && /^\d{4}-\d{2}-\d{2}/.test(starts.value) ? starts.value.slice(0, 10) : null;
    const day = picked ? new Date(`${picked}T12:00:00`) : new Date();
    const stamp = `${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
    const season = seasons && seasons.find(([first, last]) => first <= stamp && stamp <= last);
    if (!season) { line.textContent = ""; return; }
    const weekday = (day.getDay() + 6) % 7;  // Monday first, like the server
    const today = season[2][String(weekday)];
    const allClosed = Object.values(season[2]).every((value) => value === null);
    if (today === undefined) line.textContent = "";
    else if (today === null) line.textContent = allClosed ? "Closed for the season then." : `Closed on ${days[weekday]}.`;
    else if (today[0] === "00:00") line.textContent = `Lights off at ${clock(today[1])} on ${days[weekday]}.`;
    else line.textContent = `Open ${clock(today[0])} – ${clock(today[1])} on ${days[weekday]}.`;
  }
  location.addEventListener("change", update);
  form.addEventListener("change", update);
  if (starts) starts.addEventListener("input", update);
  update();
})();

// One game form: "Right now / In 30 min / In 1 hour" fill in Starts (Seattle time, rounded up to 5 minutes),
// and Ends follows with the game's length, so a pickup game "starting soon" is two taps.
(function () {
  const form = document.querySelector("form[data-sport-form]");
  const box = form && form.querySelector("[data-start-quick]");
  const starts = form && form.querySelector('input[name="starts_at"]');
  if (!box || !starts) return;
  const seattleClock = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles", year: "numeric",
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const FIVE_MIN = 5 * 60 * 1000;
  box.addEventListener("click", (event) => {
    const button = event.target.closest("[data-start-in]");
    if (!button) return;
    const when = new Date(Math.ceil((Date.now() + Number(button.dataset.startIn) * 60000 + 60000) / FIVE_MIN) * FIVE_MIN);
    const part = Object.fromEntries(seattleClock.formatToParts(when).map((p) => [p.type, p.value]));
    starts.value = `${part.year}-${part.month}-${part.day}T${part.hour}:${part.minute}`;
    starts.dispatchEvent(new Event("input", { bubbles: true }));
    starts.dispatchEvent(new Event("change", { bubbles: true }));
    box.querySelectorAll("[data-start-in]").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
  });
})();

// A plan in the post box: "No limit: anyone can come" switches off "People you need" (and it isn't sent).
(function () {
  const box = document.querySelector("[data-plan-no-limit]");
  const spots = document.querySelector("[data-plan-spots]");
  if (!box || !spots) return;
  const update = () => { spots.disabled = box.checked; };
  box.addEventListener("change", update);
  update();
})();
