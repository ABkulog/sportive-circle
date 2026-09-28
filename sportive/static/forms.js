// Keeps the "Location" list and player limits in sync with the chosen sport.
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

  const totalInput = form.querySelector('input[name="max_players"]');  // New event form
  const haveInput = form.querySelector('input[name="have"]');          // Need players form
  const neededInput = form.querySelector('input[name="needed"]');
  const hint = form.querySelector("[data-max-hint]");
  const placeTip = form.querySelector("[data-place-tip]");

  function updatePlaces() {
    const rule = rules[sport.value];
    const allowed = rule ? rule.locations : everyPlace;
    const current = location.value;
    location.replaceChildren(placeholder, ...allowed.map((place) => new Option(place, place, false, place === current)));
    if (allowed.length === 1) location.value = allowed[0];
    else if (!allowed.includes(current)) location.value = "";
  }

  function updateLimits() {
    const rule = rules[sport.value];
    if (hint) hint.textContent = rule ? `${rule.label}: up to ${rule.max} players` : "";
    if (totalInput) {
      totalInput.max = rule ? rule.max : "";
      totalInput.placeholder = rule ? `${rule.max} (the most for ${rule.label.toLowerCase()})` : "Pick a sport first";
    }
    if (neededInput && haveInput) {
      const have = parseInt(haveInput.value, 10) || 1;
      if (rule) {
        haveInput.max = rule.max - 1;
        neededInput.max = Math.max(rule.max - have, 1);
      }
    }
  }

  // Good-to-know details for this sport at this place (e.g. "Indoor pickleball is in Gym B, Thursdays 2-5 PM").
  function updateTip() {
    if (!placeTip) return;
    const rule = rules[sport.value];
    placeTip.textContent = (rule && rule.tips[location.value]) || "";
  }

  sport.addEventListener("change", () => { updatePlaces(); updateLimits(); updateTip(); });
  location.addEventListener("change", updateTip);
  if (haveInput) haveInput.addEventListener("input", updateLimits);
  updatePlaces();
  updateLimits();
  updateTip();
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
