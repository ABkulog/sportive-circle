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

// Skill levels you haven't ranked up to yet are locked (the server checks this too).
(function () {
  const tiersElement = document.getElementById("my-tiers");
  const form = document.querySelector("form[data-sport-form]");
  if (!tiersElement || !form) return;
  const { mine, needs } = JSON.parse(tiersElement.textContent);
  const sport = form.querySelector('select[name="sport"]');
  const level = form.querySelector('select[name="skill_level"]');
  if (!level) return;  // club events have no skill level
  const hint = form.querySelector("[data-level-hint]");
  const keep = level.dataset.keep || "";  // editing: the event's current level stays allowed

  function update() {
    const myTier = mine[sport.value] || 0;
    let locked = [];
    for (const option of level.options) {
      const name = option.value;
      const allowed = !(name in needs) || myTier >= needs[name] || keep === `${sport.value}|${name}`;
      option.disabled = !allowed;
      option.textContent = allowed ? name : `${name} 🔒`;
      if (!allowed) locked.push(name);
    }
    if (level.selectedOptions[0] && level.selectedOptions[0].disabled) level.value = "All levels";
    if (hint) hint.textContent = locked.length && sport.value
      ? `🔒 ${locked.join(" & ")} unlocks as you rank up in this sport.` : "";
  }
  sport.addEventListener("change", update);
  update();
})();

// Tryout spots only make sense for Intermediate / Competitive games.
(function () {
  const fields = document.querySelectorAll("[data-tryout-field]");
  const level = document.querySelector('form[data-sport-form] select[name="skill_level"]');
  if (!fields.length || !level) return;
  const hint = document.querySelector("[data-ranked-hint]");
  const update = () => {
    const ranked = ["Intermediate", "Competitive"].includes(level.value);
    fields.forEach((field) => { field.hidden = !ranked; });
    if (hint) hint.textContent = ranked ? "" : "Tryout spots and +1s are for Intermediate and Competitive games.";
  };
  level.addEventListener("change", update);
  document.querySelector('form[data-sport-form] select[name="sport"]').addEventListener("change", update);
  update();
})();
