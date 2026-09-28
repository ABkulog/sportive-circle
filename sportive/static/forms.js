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

// Private game: the password box shows only when "Private game" is on.
// Format: only the team sizes that make sense for the chosen sport (none for running, hiking...). A team
// game's size sets the number of players, so "Max players" hides.
(function () {
  const form = document.querySelector("form[data-sport-form]");
  if (!form) return;
  const privateToggle = form.querySelector("[data-private-toggle]");
  const passwordField = form.querySelector("[data-private-field]");
  if (privateToggle && passwordField) {
    const update = () => {
      passwordField.hidden = !privateToggle.checked;
      passwordField.querySelector("input").required = privateToggle.checked;
    };
    privateToggle.addEventListener("change", update);
    update();
  }
  const teamSize = form.querySelector("[data-team-size]");
  const regularOnly = form.querySelectorAll("[data-regular-only]");  // max players / "we have, we need"
  const rulesElement = document.getElementById("sport-rules");
  if (teamSize && rulesElement) {
    const rules = JSON.parse(rulesElement.textContent);
    const sport = form.querySelector('select[name="sport"]');
    const field = form.querySelector("[data-team-field]");
    const regular = teamSize.options[0];
    const updateSizes = () => {
      const sizes = (rules[sport.value] && rules[sport.value].teams) || [];
      const current = teamSize.value;
      teamSize.replaceChildren(regular, ...sizes.map((n) => new Option(`${n}v${n} team vs team`, n, false, String(n) === current)));
      if (!sizes.map(String).includes(current)) teamSize.value = "";
      if (field) field.hidden = sizes.length === 0;
      updateMax();
    };
    const updateMax = () => regularOnly.forEach((element) => { element.hidden = Boolean(teamSize.value); });
    sport.addEventListener("change", updateSizes);
    teamSize.addEventListener("change", updateMax);
    updateSizes();
  }
})();
