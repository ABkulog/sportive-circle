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
    const total = parseInt(players && players.value, 10) || 0;
    const coming = 1 + friends;
    let text = "You";
    if (friends) text += ` + ${plural(friends, "friend")}`;
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
      element.querySelectorAll("input, select, textarea").forEach((input) => { input.disabled = !show; });
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
