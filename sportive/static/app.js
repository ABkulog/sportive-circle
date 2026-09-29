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

  // <a data-back>: "Back" goes to the page you were on before this one (Home, My events, the bell...).
  // Pages that belong to this one, like a game's chat or edit page, don't count: coming back from the
  // chat and tapping Back takes you out of the game, never into the chat again. The link's own href is
  // the fallback (e.g. the page was opened from a shared link).
  document.querySelectorAll("a[data-back]").forEach((link) => {
    const here = location.pathname.replace(/\/$/, "");
    const key = `sc-back:${here}`;
    let from = null;
    try {
      const referrer = new URL(document.referrer);
      if (referrer.origin === location.origin) from = referrer;
    } catch (e) { /* no referrer */ }
    const inside = from && (from.pathname === here || from.pathname.startsWith(`${here}/`));
    const outside = from && !inside ? from.pathname + from.search : null;
    try {
      if (outside) sessionStorage.setItem(key, outside);
      const saved = sessionStorage.getItem(key);
      if (saved) link.href = saved;
    } catch (e) {
      if (outside) link.href = outside;  // storage blocked: the page right before still works
    }
  });

  // <form data-dialog="id">: show that <dialog> first (e.g. "No problem!" after "Add later"); its
  // button sends the form. Without JavaScript the form just sends right away.
  document.querySelectorAll("form[data-dialog]").forEach((form) => {
    const dialog = document.getElementById(form.dataset.dialog);
    if (!dialog || typeof dialog.showModal !== "function") return;
    form.addEventListener("submit", (event) => {
      if (form.dataset.dialogShown) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      dialog.showModal();
    }, true);
    dialog.querySelectorAll("[data-dialog-continue]").forEach((button) => {
      button.addEventListener("click", () => { form.dataset.dialogShown = "1"; dialog.close(); form.requestSubmit(); });
    });
  });

  // <button data-countdown="42" data-countdown-text="Resend code in {s}s">: disabled and counting down,
  // then usable. (The server checks the same wait.)
  document.querySelectorAll("button[data-countdown]").forEach((button) => {
    let left = parseInt(button.dataset.countdown, 10) || 0;
    if (left <= 0) return;
    const label = button.textContent;
    const tick = () => {
      if (left <= 0) { button.disabled = false; button.textContent = label; return; }
      button.disabled = true;
      button.textContent = button.dataset.countdownText.replace("{s}", left);
      left -= 1;
      setTimeout(tick, 1000);
    };
    tick();
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
  // data-share-text (e.g. a private game's invite with its password) is sent along with the link.
  document.querySelectorAll("[data-share-url]").forEach((button) => {
    const label = button.querySelector("[data-share-label]");
    const original = label ? label.textContent : "";
    button.addEventListener("click", async () => {
      const url = button.dataset.shareUrl;
      const title = button.dataset.shareTitle || document.title;
      const text = button.dataset.shareText || `${title} on Sportive Circle`;
      if (navigator.share) {
        try { await navigator.share({ title, text, url }); } catch (e) { /* closed */ }
        return;
      }
      const copy = button.dataset.shareText ? `${text}\n${url}` : url;
      try {
        await navigator.clipboard.writeText(copy);
        if (label) {
          label.textContent = "Copied!";
          setTimeout(() => { label.textContent = original; }, 2000);
        }
      } catch (e) {
        window.prompt("Copy this:", copy);
      }
    });
  });

  // <button data-copy="text">: copy it (e.g. a club roster's emails), then say "Copied!".
  document.querySelectorAll("[data-copy]").forEach((button) => {
    const label = button.querySelector("[data-copy-label]") || button;
    const original = label.textContent;
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        label.textContent = "Copied!";
        setTimeout(() => { label.textContent = original; }, 2000);
      } catch (e) {
        window.prompt("Copy this:", button.dataset.copy);
      }
    });
  });

  // Look (light / dark / match my phone): try it right away, before saving.
  document.querySelectorAll("input[data-theme-choice]").forEach((radio) => {
    radio.addEventListener("change", () => { document.documentElement.dataset.theme = radio.value; });
  });

  // <button data-print>: print the page (e.g. a club's QR code for a flyer).
  document.querySelectorAll("[data-print]").forEach((button) => button.addEventListener("click", () => window.print()));

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
      image.style.setProperty("--size", "150px");
      photoPreview.replaceChildren(image);
    });
  }

  // The "Need help?" bubble: shown until someone taps its ×, then hidden on this device for good.
  const helpBubble = document.querySelector("[data-help-bubble]");
  if (helpBubble) {
    let closed = false;
    try { closed = localStorage.getItem("helpBubbleClosed") === "1"; } catch (error) { /* private mode */ }
    helpBubble.hidden = closed;
    helpBubble.querySelector("[data-help-close]").addEventListener("click", () => {
      helpBubble.hidden = true;
      try { localStorage.setItem("helpBubbleClosed", "1"); } catch (error) { /* private mode */ }
    });
  }

  // Every password box gets an eye button to peek at what you typed (tap again to hide it).
  const EYE = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor"' +
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7' +
    'S2 12 2 12z"/><circle cx="12" cy="12" r="3"/><path class="eye-slash" d="M4 4l16 16"/></svg>';
  document.querySelectorAll('input[type="password"]').forEach((input) => {
    const wrap = document.createElement("span");
    wrap.className = "password-wrap";
    input.replaceWith(wrap);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "peek";
    button.innerHTML = EYE;  // our own fixed icon, never text someone typed
    button.setAttribute("aria-label", "Show password");
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.setAttribute("aria-pressed", String(show));
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      input.focus();
    });
    wrap.append(input, button);
  });
  // Hide them again before sending, so the browser offers to save it as a password as usual.
  document.addEventListener("submit", (event) => {
    event.target.querySelectorAll(".password-wrap input").forEach((input) => { input.type = "password"; });
  }, true);
})();
