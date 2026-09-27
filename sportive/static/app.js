// Small helpers used on many pages. Pages describe what they want with data-* attributes
// (no inline JavaScript), so names and messages that people type can never run as code.
(function () {
  // <form data-confirm="Leave the club?">: ask first. The text is plain data, so an apostrophe
  // in a name ("O'Brien") can't break it.
  document.addEventListener("submit", (event) => {
    const form = event.target;
    const message = form.dataset && form.dataset.confirm;
    if (message && !window.confirm(message)) { event.preventDefault(); return; }
    // A double tap shouldn't post twice: lock the buttons of a form that's already sending
    // (GET forms like search and filters are harmless, so they stay free).
    if (form.method === "post") {
      if (form.dataset.sending) { event.preventDefault(); return; }
      form.dataset.sending = "1";
      setTimeout(() => form.querySelectorAll("button").forEach((button) => { button.disabled = true; }));
    }
  });
  // Coming back with the Back button shows the page from memory: unlock its forms again.
  window.addEventListener("pageshow", () => {
    document.querySelectorAll("form[data-sending]").forEach((form) => {
      delete form.dataset.sending;
      form.querySelectorAll("button").forEach((button) => { button.disabled = false; });
    });
  });

  // <select data-autosubmit>: filters apply as soon as you pick something.
  document.addEventListener("change", (event) => {
    const field = event.target;
    if (field.matches && field.matches("[data-autosubmit]") && field.form) field.form.requestSubmit();
  });

  // <p data-expand>: long text is clamped to a few lines; tap to read it all.
  document.querySelectorAll("[data-expand]").forEach((box) => {
    box.tabIndex = 0;
    box.setAttribute("role", "button");
    box.setAttribute("aria-expanded", "false");
    const toggle = () => box.setAttribute("aria-expanded", box.classList.toggle("is-open") ? "true" : "false");
    box.addEventListener("click", toggle);
    box.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); }
    });
  });

  // One-time tips (like "New here?"): hidden for good once dismissed on this device.
  document.querySelectorAll("[data-tip]").forEach((tip) => {
    const key = `sc-tip-${tip.dataset.tip}`;
    let seen = false;
    try { seen = localStorage.getItem(key) === "1"; } catch (e) { /* private mode: just show it */ }
    if (!seen) tip.hidden = false;
    const close = tip.querySelector("[data-tip-close]");
    if (close) close.addEventListener("click", () => {
      tip.hidden = true;
      try { localStorage.setItem(key, "1"); } catch (e) { /* not saved; fine */ }
    });
  });

  // Share: the phone's share sheet (GroupMe, iMessage, Instagram...), or copy the link on a laptop.
  document.querySelectorAll("[data-share-url]").forEach((button) => {
    const label = button.querySelector("[data-share-label]");
    button.addEventListener("click", async () => {
      const url = button.dataset.shareUrl;
      const title = button.dataset.shareTitle || document.title;
      if (navigator.share) {
        try { await navigator.share({ title, text: `${title} on Sportive Circle`, url }); } catch (e) { /* closed */ }
        return;
      }
      try {
        await navigator.clipboard.writeText(url);
        if (label) {
          label.textContent = "Copied!";
          setTimeout(() => { label.textContent = "Share"; }, 2000);
        }
      } catch (e) {
        window.prompt("Copy this link:", url);
      }
    });
  });

  // Badge locker: once the showcase is full, the other checkboxes wait until you uncheck one.
  const picks = [...document.querySelectorAll(".showcase-pick")];
  const count = document.getElementById("picked-count");
  if (picks.length && count) {
    const slots = parseInt(count.dataset.slots, 10) || 3;
    const update = () => {
      const checked = picks.filter((box) => box.checked).length;
      count.textContent = checked;
      picks.forEach((box) => { box.disabled = !box.checked && checked >= slots; });
    };
    picks.forEach((box) => box.addEventListener("change", update));
    update();
  }

  // Profile picture: show the chosen photo right away (the server crops it to a square when you save).
  const photoInput = document.getElementById("photo-input");
  const photoPreview = document.getElementById("photo-preview");
  if (photoInput && photoPreview) {
    photoInput.addEventListener("change", () => {
      const file = photoInput.files[0];
      if (!file) return;
      const image = new Image();
      image.src = URL.createObjectURL(file);
      image.alt = "";
      image.className = "avatar-img";
      image.style.setProperty("--size", "160px");
      photoPreview.replaceChildren(image);
    });
  }
})();
