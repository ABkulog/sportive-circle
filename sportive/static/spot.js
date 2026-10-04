// Off campus: "📍 Where exactly?" Shown only when the place is "Off campus". Drop a pin on a map (tap it, drag to
// adjust), use your location, or type an address / paste a Google or Apple Maps link. The map library only
// loads when someone taps "Drop a pin", so the form stays light. The server checks everything again.
(function () {
  const OFF_CAMPUS = "Off campus (see note)";
  const UW = [47.6553, -122.3035];
  const LEAFLET = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/";
  let loading = null;

  function loadLeaflet() {
    if (typeof L !== "undefined") return Promise.resolve();
    if (loading) return loading;
    loading = new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = LEAFLET + "leaflet.css";
      css.integrity = "sha512-Zcn6bjR/8RZbLEpLIeOwNtzREBAJnUKESxces60Mpoj+2okopSAcSUIUOseddDm0cxnGQzxIR7vJgsLZbdLE3w==";
      css.crossOrigin = "anonymous";
      document.head.appendChild(css);
      const script = document.createElement("script");
      script.src = LEAFLET + "leaflet.js";
      script.integrity = "sha512-BwHfrr4c9kmRkLw6iXFdzcdWV/PGkVgiIyIWLLlTSXzWQzxuSg4DiQUCpauz/EWjgk5TYQqX/kvn9pG1NpYfqg==";
      script.crossOrigin = "anonymous";
      script.onload = () => resolve();
      script.onerror = () => { loading = null; reject(new Error("map")); };
      document.head.appendChild(script);
    });
    return loading;
  }

  document.querySelectorAll("[data-spot]").forEach((box) => {
    const form = box.closest("form");
    const place = form && form.querySelector('select[name="location"]');
    const pin = box.querySelector("[data-pin]");
    const status = box.querySelector("[data-pin-status]");
    const mapBox = box.querySelector("[data-spot-map]");
    const clear = box.querySelector("[data-clear-pin]");
    let map = null;
    let marker = null;

    const current = () => {
      const parts = (pin.value || "").split(",").map(Number);
      return parts.length === 2 && parts.every((n) => !Number.isNaN(n)) ? parts : null;
    };
    function setPin(lat, lng, note) {
      pin.value = `${lat.toFixed(6)},${lng.toFixed(6)}`;
      status.textContent = note || "📍 Pin dropped. Drag it to adjust.";
      clear.hidden = false;
      if (map) {
        if (marker) marker.setLatLng([lat, lng]);
        else {
          marker = L.marker([lat, lng], { draggable: true }).addTo(map);
          marker.on("dragend", () => { const p = marker.getLatLng(); setPin(p.lat, p.lng); });
        }
      }
    }
    async function openMap(center) {
      try {
        await loadLeaflet();
      } catch (error) {
        status.textContent = "The map couldn't load here. Type the address or paste a maps link instead.";
        return false;
      }
      mapBox.hidden = false;
      if (!map) {
        map = L.map(mapBox, { scrollWheelZoom: false }).setView(center || current() || UW, center || current() ? 16 : 13);
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(map);
        map.on("click", (event) => setPin(event.latlng.lat, event.latlng.lng));
        const there = current();
        if (there) setPin(there[0], there[1], status.textContent);
      } else if (center) {
        map.setView(center, 16);
      }
      setTimeout(() => map.invalidateSize(), 50);
      if (!current()) status.textContent = "Tap the map where you're meeting.";
      return true;
    }

    box.querySelector("[data-drop-pin]").addEventListener("click", () => openMap());
    const mine = box.querySelector("[data-my-spot]");
    if (!("geolocation" in navigator)) mine.hidden = true;
    mine.addEventListener("click", () => {
      status.textContent = "Finding you…";
      navigator.geolocation.getCurrentPosition(async (position) => {
        const { latitude, longitude } = position.coords;
        await openMap([latitude, longitude]);
        setPin(latitude, longitude, "📍 Pin dropped where you are. Drag it to adjust.");
      }, () => { status.textContent = "Couldn't get your location. Drop the pin on the map instead."; },
      { enableHighAccuracy: true, timeout: 10000 });
    });
    clear.hidden = !current();
    clear.addEventListener("click", () => {
      pin.value = "";
      status.textContent = "";
      clear.hidden = true;
      if (marker) { marker.remove(); marker = null; }
    });

    // Only for Off campus (campus places already have their own pin)
    function update() {
      const off = !place || place.value === OFF_CAMPUS;
      box.hidden = !off;
      if (map && off) setTimeout(() => map.invalidateSize(), 50);
    }
    if (place) place.addEventListener("change", update);
    update();
  });
})();
