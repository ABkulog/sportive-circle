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

  // "Heads up: check the courts/field/trail is free": the word follows the sport.
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
    text += need > 0 ? ` · need ${need} more` : need === 0 ? " · full" : ` · that's ${-need} too many`;
    math.textContent = text;
    math.classList.toggle("is-over", need < 0);
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
  const read = (input) => { const t = new Date(input.value).getTime(); return Number.isNaN(t) ? null : t; };
  const pad = (n) => String(n).padStart(2, "0");
  const write = (input, time) => {
    const d = new Date(time);
    input.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };
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
  const pad = (n) => String(n).padStart(2, "0");
  const local = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;

  function times() {
    if (startsAt && endsAt) return [startsAt.value, endsAt.value];
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
      if (!info.reserved.length) line.append("No UW Rec reservations we know of then. ");
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
        item.append(name, ` · ${game.when} · ${game.going}${game.max ? "/" + game.max : ""} going`);
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
      if (!location.value || !starts || !ends) { show(null); return; }
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
