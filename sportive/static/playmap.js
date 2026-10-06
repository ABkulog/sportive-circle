// Play's live map, like Snap Map: a calm campus map with a bubble for each place where something's on right now:
// starting within an hour, going on, or ended in the last 10. The bubble shows the sport and "Live",
// "in 20 min" or "Ended"; tap it for the games there. Built with DOM methods (titles are text, never HTML).
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
  // Bright, clean colors (CARTO Voyager, from OpenStreetMap), like Snap Map, instead of plain grey tiles.
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    maxZoom: 19, subdomains: "abcd",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  }).addTo(map);

  const bounds = [];
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
    L.marker([pin.lat, pin.lng], { icon, title: `${pin.name}: ${pin.label}` }).addTo(map).bindPopup(list);
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
