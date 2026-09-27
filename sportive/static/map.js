// Event map: a pin for the event, and (if you tap "Where am I?") a blue dot for you,
// plus how far it is. Your location stays in your browser; it's never sent to our server.
(function () {
  const box = document.getElementById("event-map");
  if (!box || typeof L === "undefined") return;

  const folded = box.closest("details");
  if (folded && !folded.open) {
    folded.addEventListener("toggle", () => { if (folded.open && !box.dataset.ready) start(); });
  } else {
    start();
  }

  function start() {
    box.dataset.ready = "1";
    const place = [parseFloat(box.dataset.lat), parseFloat(box.dataset.lng)];
    const map = L.map(box, { scrollWheelZoom: false }).setView(place, 17);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    L.marker(place, { title: box.dataset.name }).addTo(map).bindPopup(box.dataset.name).openPopup();

    const button = document.getElementById("locate-me");
    const status = document.getElementById("map-status");
    let me = null;

    function metersBetween([lat1, lng1], [lat2, lng2]) {
      const toRad = (deg) => (deg * Math.PI) / 180;
      const a = Math.sin(toRad(lat2 - lat1) / 2) ** 2 +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(toRad(lng2 - lng1) / 2) ** 2;
      return 6371000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function describe(meters) {
      const miles = meters / 1609.34;
      const walkMinutes = Math.max(1, Math.round(meters / 80)); // ~80 m per minute walking
      if (meters < 60) return "You're here! 🎉";
      const distance = miles < 0.1 ? `${Math.round(meters)} m` : `${miles.toFixed(1)} mi`;
      if (miles > 3) return `You're about ${distance} away. That's a long walk, maybe take the bus or bike.`;
      return `You're about ${distance} away, around a ${walkMinutes} min walk.`;
    }

    if (!button) return;
    if (!("geolocation" in navigator)) {
      button.hidden = true;
      return;
    }
    // Where to turn location on, in words that match the user's device.
    function howToAllow() {
      const ua = navigator.userAgent;
      const iOS = /iPhone|iPad|iPod/.test(ua) || (ua.includes("Macintosh") && navigator.maxTouchPoints > 1);
      if (iOS) return "To turn it on: Settings → Privacy & Security → Location Services → Safari Websites → While Using the App. Then reload this page.";
      if (/Android/.test(ua)) return "To turn it on: tap the icon left of the web address → Permissions → Location → Allow. Then reload this page.";
      if (/Macintosh/.test(ua)) {
        const safari = /Safari/.test(ua) && !/Chrome|Chromium|Edg|Firefox/.test(ua);
        return safari
          ? "To turn it on: System Settings → Privacy & Security → Location Services → turn on Safari, then Safari → Settings → Websites → Location → Allow. Then reload this page."
          : "To turn it on: System Settings → Privacy & Security → Location Services → turn on your browser, then click the icon left of the web address and allow Location. Then reload this page.";
      }
      return "To turn it on: click the icon left of the web address and allow Location. Then reload this page.";
    }

    function showMe(position) {
      const here = [position.coords.latitude, position.coords.longitude];
      if (me) me.setLatLng(here);
      else me = L.circleMarker(here, {
        radius: 8, color: "#fff", weight: 3, fillColor: "#1a73e8", fillOpacity: 1,
      }).addTo(map).bindTooltip("You");
      map.fitBounds(L.latLngBounds([here, place]), { padding: [40, 40], maxZoom: 17 });
      status.textContent = describe(metersBetween(here, place));
    }

    function done() {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }

    function locate(precise) {
      navigator.geolocation.getCurrentPosition(
        (position) => { done(); showMe(position); },
        (error) => {
          if (error.code === error.PERMISSION_DENIED) {
            done();
            status.textContent = `Your browser is blocking location for this site. ${howToAllow()} Or just tap Directions.`;
          } else if (precise) {
            // GPS can time out indoors or on laptops; Wi-Fi location is rougher but usually answers.
            status.textContent = "Still looking…";
            locate(false);
          } else {
            done();
            status.textContent = "Couldn't find your location right now. Try again outside, or tap Directions.";
          }
        },
        precise
          ? { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
          : { enableHighAccuracy: false, timeout: 15000, maximumAge: 300000 },
      );
    }

    button.addEventListener("click", () => {
      if (!window.isSecureContext) {
        status.textContent = "Location only works on a secure (https) page. Tap Directions instead.";
        return;
      }
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      status.textContent = "Finding you…";
      locate(true);
    });
  }
})();
