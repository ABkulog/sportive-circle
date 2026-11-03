// Play's live map, like Snap Map: a calm campus map with a bubble for each place where something's on right now:
// starting within an hour, going on, or ended in the last 10. The bubble shows the sport and "Live",
// "in 20 min" or "Ended"; every other place has a labeled pin. Tap one for its panel (games, hours, create). Built with DOM methods (titles are text, never HTML).
// If the map library can't load, the map hides and the list under it still works.
(function () {
  const box = document.getElementById("play-map");
  const data = document.getElementById("play-pins");
  if (!box || !data) return;
  if (typeof L === "undefined") { box.closest(".live-map-wrap").hidden = true; return; }
  const pins = JSON.parse(data.textContent);
  const wrap = box.closest("[data-live-map]");
  // On the page it's a still preview (tap opens it full screen), so it never fights the page's scrolling.
  const map = L.map(box, { scrollWheelZoom: false, zoomControl: false, attributionControl: true, dragging: false,
                           touchZoom: false, doubleClickZoom: false, boxZoom: false, keyboard: false })
    .setView([47.6553, -122.3035], 15);  // UW
  // OpenStreetMap's own colorful tiles, like Snap Map (no grey filter). Not CARTO: its tiles need a paid key now
  // and showed "API KEY REQUIRED" across the map.
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  // Every place games are played (the IMA, courts, fields, the track): a labeled pin with its sport. Tap one and a
  // small panel slides up: hours today (closed said plainly), the games there this week, what UW Rec has booked
  // today (club practices, IM games), and at the end "Create an event here" with the place and sport filled in.
  const spotsData = document.getElementById("play-spots");
  const spots = spotsData ? JSON.parse(spotsData.textContent) : [];
  const spotAt = {};
  spots.forEach((spot) => { spotAt[`${spot.lat},${spot.lng}`] = spot; });
  const sheet = wrap && wrap.querySelector("[data-spot-sheet]");
  const sheetBody = sheet && sheet.querySelector("[data-spot-body]");
  function add(parent, tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    parent.appendChild(node);
    return node;
  }
  // The page only knows how many games each place has; tapping it loads the place's panel (its games this week).
  const panelUrl = sheet && sheet.dataset.panelUrl;
  function openSheet(spot) {
    if (!sheet) return;
    sheetBody.replaceChildren();
    add(sheetBody, "p", "muted", `${spot.emoji} ${spot.name}…`);
    sheet.hidden = false;
    fetch(`${panelUrl}?place=${encodeURIComponent(spot.name)}`, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then(fillSheet)
      .catch(() => fillSheet({ ...spot, games: [] }));
  }
  function fillSheet(spot) {
    sheetBody.replaceChildren();
    add(sheetBody, "h3", "spot-sheet-title", `${spot.emoji} ${spot.name}`);
    if (spot.hours) add(sheetBody, "p", spot.closed ? "spot-hours is-closed" : "spot-hours",
                        spot.closed ? "⚠️ Closed today" : spot.hours);
    add(sheetBody, "p", "spot-sheet-sub", spot.games.length ? "Games this week" : "No games here this week yet");
    spot.games.forEach((game) => {
      const link = add(sheetBody, "a", "spot-game");
      link.href = game.url;
      add(link, "strong", "", game.title);
      add(link, "small", "muted", ` · ${game.when}${game.max ? ` · ${game.going}/${game.max} going` : ""}`);
    });
    if (spot.bookings.length) {
      add(sheetBody, "p", "spot-sheet-sub", "Booked by UW Rec today");
      spot.bookings.forEach((booking) => add(sheetBody, "p", "spot-booking", `${booking.label} · ${booking.when}`));
    }
    const create = add(sheetBody, "a", "btn btn-block spot-create", "＋ Create an event here");
    create.href = spot.new_url;
    if (spot.closed) add(sheetBody, "p", "muted small", "It's closed today: you can still post one for another day (or anyway).");
    sheetBody.scrollTop = 0;
  }
  if (sheet) sheet.querySelector("[data-spot-close]").addEventListener("click", () => { sheet.hidden = true; });

  const bounds = [];
  const withGames = new Set(pins.map((pin) => `${pin.lat},${pin.lng}`));
  spots.forEach((spot) => {
    if (withGames.has(`${spot.lat},${spot.lng}`)) return;  // the game bubble there opens the same panel
    const pinBox = document.createElement("div");
    pinBox.className = `spot-pin${spot.game_count ? " has-games" : ""}${spot.closed ? " is-closed" : ""}`;
    add(pinBox, "span", "spot-emoji", spot.emoji);
    add(pinBox, "span", "spot-name", spot.game_count ? `${spot.short} · ${spot.game_count}` : spot.short);
    const icon = L.divIcon({ html: pinBox, className: "live-icon", iconSize: [96, 58], iconAnchor: [48, 20] });
    L.marker([spot.lat, spot.lng], { icon, title: `${spot.name}: tap for games and to create an event` })
      .addTo(map).on("click", () => openSheet(spot));
  });
  pins.forEach((pin) => {
    const bubble = document.createElement("div");
    bubble.className = `live-bubble is-${pin.state}`;
    const emoji = document.createElement("span");
    emoji.className = "live-emoji";
    emoji.textContent = pin.emoji;
    const label = document.createElement("span");
    label.className = "live-label";
    label.textContent = pin.games.length > 1 ? `${pin.label} · ${pin.games.length}` : pin.label;
    bubble.append(emoji, label);
    const icon = L.divIcon({ html: bubble, className: "live-icon", iconSize: [64, 64], iconAnchor: [32, 26] });

    const list = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = pin.name;
    list.appendChild(name);
    pin.games.forEach((game) => {
      const link = document.createElement("a");
      link.href = game.url;
      link.className = "map-game";
      link.textContent = `${game.title} · ${game.when}`;
      list.appendChild(link);
    });
    const spot = spotAt[`${pin.lat},${pin.lng}`];
    const marker = L.marker([pin.lat, pin.lng], { icon, title: `${pin.name}: ${pin.label}`, zIndexOffset: 1000 }).addTo(map);
    if (spot) marker.on("click", () => openSheet(spot));  // a campus place: its panel (games, hours, create)
    else marker.bindPopup(list);                         // an off-campus game's own pin
    bounds.push([pin.lat, pin.lng]);
  });
  // Center it once the page has its final size: set up while the page was still laying out, it landed ~2 km
  // west of campus (in Wallingford) because the map thought it was wider than it is.
  function frame() {
    map.invalidateSize();
    if (bounds.length === 1) map.setView(bounds[0], 16);
    else if (bounds.length > 1) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
    else map.setView([47.6553, -122.3035], 15);
  }
  frame();
  requestAnimationFrame(frame);

  // Full screen, like Snap Map: tap the map; ← Back, Esc or the phone's back button closes it.
  const openButton = wrap && wrap.querySelector("[data-map-open]");
  const backButton = wrap && wrap.querySelector("[data-map-close]");
  const recenter = wrap && wrap.querySelector("[data-map-recenter]");
  const handlers = ["dragging", "touchZoom", "doubleClickZoom", "scrollWheelZoom", "boxZoom", "keyboard"];
  let pushed = false;
  function setFull(on) {
    if (!wrap || wrap.classList.contains("is-full") === on) return;
    wrap.classList.toggle("is-full", on);
    if (!on && sheet) sheet.hidden = true;
    document.body.classList.toggle("map-full", on);
    handlers.forEach((name) => map[name][on ? "enable" : "disable"]());
    if (on) map.addControl(zoom); else map.removeControl(zoom);
    openButton.hidden = on;
    backButton.hidden = !on;
    recenter.hidden = !on;
    setTimeout(frame, 30);
    if (on) backButton.focus(); else openButton.focus({ preventScroll: true });
  }
  const zoom = L.control.zoom({ position: "bottomright" });
  if (openButton) {
    openButton.addEventListener("click", () => {
      history.pushState({ playMap: true }, "", "#map");
      pushed = true;
      setFull(true);
    });
    backButton.addEventListener("click", () => { if (pushed) history.back(); else setFull(false); });
    recenter.addEventListener("click", () => map.setView([47.6553, -122.3035], 15));
    window.addEventListener("popstate", () => { pushed = false; setFull(location.hash === "#map"); });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && wrap.classList.contains("is-full")) backButton.click();
    });
    if (location.hash === "#map") setFull(true);  // a shared link, or coming back to it
  }
  window.addEventListener("load", frame, { once: true });
  if (window.ResizeObserver) {
    let width = box.clientWidth;
    new ResizeObserver(() => { if (box.clientWidth !== width) { width = box.clientWidth; frame(); } }).observe(box);
  }
})();
