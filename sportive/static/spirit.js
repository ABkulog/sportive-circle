// Purple & gold confetti when something good happens (joining a game, posting one, signing up).
// Skipped for people who turned on "reduce motion" on their device.
(function () {
  if (!document.querySelector(".flash-celebrate")) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const colors = ["#4b2e83", "#ffc700", "#b7a57a", "#ffffff", "#32006e"];
  const layer = document.createElement("div");
  layer.className = "confetti";
  layer.setAttribute("aria-hidden", "true");

  for (let i = 0; i < 90; i++) {
    const piece = document.createElement("span");
    const size = 6 + Math.random() * 7;
    piece.style.left = `${Math.random() * 100}%`;
    piece.style.width = `${size}px`;
    piece.style.height = `${size * (Math.random() < 0.5 ? 1 : 0.45)}px`;
    piece.style.background = colors[i % colors.length];
    piece.style.animationDelay = `${Math.random() * 0.35}s`;
    piece.style.animationDuration = `${1.6 + Math.random() * 1.2}s`;
    piece.style.setProperty("--drift", `${(Math.random() - 0.5) * 160}px`);
    piece.style.setProperty("--spin", `${(Math.random() - 0.5) * 1080}deg`);
    if (Math.random() < 0.3) piece.style.borderRadius = "50%";
    layer.appendChild(piece);
  }
  document.body.appendChild(layer);
  setTimeout(() => layer.remove(), 3200);
})();
