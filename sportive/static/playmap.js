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
  const map = L.map(box, { scrollWheelZoom: false, zoomControl: false, attributionControl: true })
    .setView([47.6553, -122.3035], 15);  // UW
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
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
  if (bounds.length === 1) map.setView(bounds[0], 16);
  else if (bounds.length > 1) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
})();
