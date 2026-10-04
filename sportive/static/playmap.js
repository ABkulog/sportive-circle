// Play's map: a pin for each place with games coming up; tapping one lists them (links to each game).
// Built with DOM methods (game titles are text, never HTML). If the map library can't load, the map hides.
(function () {
  const box = document.getElementById("play-map");
  const data = document.getElementById("play-pins");
  if (!box || !data) return;
  if (typeof L === "undefined") { box.hidden = true; return; }
  const pins = JSON.parse(data.textContent);
  const map = L.map(box, { scrollWheelZoom: false, zoomControl: false });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  const bounds = [];
  pins.forEach((pin) => {
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
    const marker = L.marker([pin.lat, pin.lng], { title: pin.name }).addTo(map).bindPopup(list);
    marker.bindTooltip(String(pin.games.length), { permanent: true, direction: "top", className: "map-count", offset: [-15, -12] });
    bounds.push([pin.lat, pin.lng]);
  });
  if (bounds.length === 1) map.setView(bounds[0], 16);
  else map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
})();
