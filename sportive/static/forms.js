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

  sport.addEventListener("change", () => { updatePlaces(); updateLimits(); });
  if (haveInput) haveInput.addEventListener("input", updateLimits);
  updatePlaces();
  updateLimits();
})();
