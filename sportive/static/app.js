// Small helpers used on many pages. Pages describe what they want with data-* attributes
// (no inline JavaScript), so names and messages that people type can never run as code.
(function () {
  // form.requestSubmit() needs Safari 16+. Older iPhones get the same result by hand: run the
  // page's submit handlers (like the confirm below), and send only if none of them said no.
  function submitForm(form) {
    if (form.requestSubmit) return form.requestSubmit();
    if (form.dispatchEvent(new Event("submit", { cancelable: true }))) form.submit();
  }

  // <form data-confirm="Leave the club?">: ask first. The text is plain data, so an apostrophe
  // in a name ("O'Brien") can't break it.
  document.addEventListener("submit", (event) => {
    const form = event.target;
    const message = form.dataset && form.dataset.confirm;
    if (message && !window.confirm(message)) { event.preventDefault(); return; }
    if (event.defaultPrevented) return;  // sent another way (e.g. a chat sends in the background)
    // A double tap shouldn't post twice: lock the buttons of a form that's already sending
    // (GET forms like search and filters are harmless, so they stay free).
    if (form.method === "post") {
      if (form.dataset.sending) { event.preventDefault(); return; }
      form.dataset.sending = "1";
      setTimeout(() => form.querySelectorAll("button").forEach((button) => { button.disabled = true; }));
    }
  });
  // <p data-reload-in="600">: reload when a held spot frees up (a few seconds late, so it's really free),
  // so a full-for-now game turns joinable without anyone having to keep tapping.
  document.querySelectorAll("[data-reload-in]").forEach((element) => {
    const seconds = Number(element.dataset.reloadIn);
    if (!(seconds >= 0 && seconds < 3600)) return;
    element.setAttribute("role", "status");
    setTimeout(() => {
      // Someone moving through the page with a keyboard or screen reader would be thrown back to the top by a
      // reload: tell them instead, with a link to check.
      const busy = document.activeElement && document.activeElement !== document.body;
      if (!busy) { location.reload(); return; }
      const again = document.createElement("a");
      again.href = location.href;
      again.textContent = "A spot may be open now. Check again";
      element.replaceChildren(again);
    }, (seconds + 3) * 1000);
  });
  // <input data-filter-list="#id">: as you type, hide the [data-filter-name] items in #id whose name doesn't
  // match (any word of the name starting with what's typed), plus sections left empty.
  document.querySelectorAll("input[data-filter-list]").forEach((input) => {
    const list = document.querySelector(input.dataset.filterList);
    if (!list) return;
    const items = Array.from(list.querySelectorAll("[data-filter-name]"));
    const empty = list.querySelector("[data-filter-empty]");
    // Accents and capitals don't matter ("jose" finds "José"), the same as the searches on the server.
    const words = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim()
      .split(/\s+/).filter(Boolean);
    const filter = () => {
      const typed = words(input.value);
      let shown = 0;
      items.forEach((item) => {
        const name = words(item.dataset.filterName);
        const match = typed.every((t) => name.some((n) => n.startsWith(t)));
        item.hidden = !match;
        if (match) shown += 1;
      });
      list.querySelectorAll("[data-filter-group]").forEach((group) => {
        group.hidden = !group.querySelector("[data-filter-name]:not([hidden])");
      });
      if (empty) empty.hidden = shown > 0 || !typed.length;
    };
    input.addEventListener("input", filter);
    filter();
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
      // Coming back from one of this page's own pages (its chat, its edit page): go where we came from before.
      // Opened from nowhere (a typed or shared link): the link's own place, never an old leftover.
      const saved = outside || (inside ? sessionStorage.getItem(key) : null);
      if (!from) sessionStorage.removeItem(key);
      if (saved) goBackTo(link, saved);
    } catch (e) {
      if (outside) goBackTo(link, outside);  // storage blocked: the page right before still works
    }
  });
  // "← Profile" must never lead somewhere else: if Back goes to another page, it just says "Back".
  function goBackTo(link, path) {
    const labelled = new URL(link.href, location.href);
    const target = new URL(path, location.href);
    if (target.pathname !== labelled.pathname) link.textContent = "← Back";
    link.href = path;
  }

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
      button.addEventListener("click", () => { form.dataset.dialogShown = "1"; dialog.close(); submitForm(form); });
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
    if (field.matches && field.matches("[data-autosubmit]") && field.form) submitForm(field.form);
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
    let previewUrl = null;
    photoInput.addEventListener("change", () => {
      const file = photoInput.files[0];
      if (!file) return;
      if (previewUrl) URL.revokeObjectURL(previewUrl);  // the last pick's copy isn't needed anymore
      previewUrl = URL.createObjectURL(file);
      const image = new Image();
      image.src = previewUrl;
      image.alt = "";
      image.className = "avatar-img";
      image.style.setProperty("--size", "150px");
      photoPreview.replaceChildren(image);
    });
  }

  // The "Help?" bubble: shown until someone taps its ×, then hidden on this device for good.
  const helpBubble = document.querySelector("[data-help-bubble]");
  if (helpBubble) {
    let closed = false;
    try { closed = localStorage.getItem("helpBubbleClosed") === "1"; } catch (error) { /* private mode */ }
    // Forms (edit profile, create a game...) keep their Save/Next button uncovered.
    if (document.querySelector("main .form-card, main form.form")) closed = true;
    helpBubble.hidden = closed;
    document.body.classList.toggle("has-help", !closed);  // room at the bottom so it never covers the last item
    helpBubble.querySelector("[data-help-close]").addEventListener("click", () => {
      helpBubble.hidden = true;
      document.body.classList.remove("has-help");
      try { localStorage.setItem("helpBubbleClosed", "1"); } catch (error) { /* private mode */ }
    });
  }

  // Putting the app on the home screen. Android/Chrome gets a one-tap Add (the browser's install prompt);
  // iPhone Safari gets the two steps (Apple only lets the person do it). Never once it runs from the home screen,
  // nor in browsers that can't (laptops, Instagram/Snapchat's). × hides the card; it comes back once after a week.
  const ua = navigator.userAgent;
  const iPadOS = /Macintosh/.test(ua) && navigator.maxTouchPoints > 1;  // iPads say "Mac" in Safari
  const iosSafari = (/iPhone|iPad|iPod/.test(ua) || iPadOS) && /Safari/.test(ua)
    && !/CriOS|FxiOS|EdgiOS|Instagram|FBAN|FBAV|Snapchat/.test(ua);
  const androidChrome = /Android/.test(ua) && /Chrome\//.test(ua) && !/; wv\)|Instagram|FBAN|FBAV|Snapchat/.test(ua);
  const installed = navigator.standalone || window.matchMedia("(display-mode: standalone)").matches;
  let installPrompt = null;
  const installListeners = [];
  window.addEventListener("beforeinstallprompt", (event) => {  // Chrome says it can be installed
    event.preventDefault();
    installPrompt = event;
    installListeners.forEach((listener) => listener());
  });
  const install = async () => {
    if (!installPrompt) return false;
    installPrompt.prompt();
    const choice = await installPrompt.userChoice;
    installPrompt = null;
    return choice.outcome === "accepted";
  };
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch (error) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (error) { /* private mode */ } },
  };
  const WEEK = 7 * 24 * 60 * 60 * 1000;

  const installTip = document.querySelector("[data-install-tip]");
  if (installTip && !installed) {
    const closes = Number(store.get("installTipCloses") || (store.get("installTipClosed") === "1" ? 1 : 0));
    const closedAt = Number(store.get("installTipClosedAt") || 0);
    const allowed = closes === 0 || (closes === 1 && Date.now() - closedAt > WEEK);
    const show = (part) => {
      if (!allowed) return;
      installTip.querySelector(`[data-install-${part}]`).hidden = false;
      installTip.hidden = false;
    };
    if (iosSafari) show("ios");
    const offerAndroid = () => { installTip.querySelector("[data-install-button]").hidden = false; show("android"); };
    if (installPrompt) offerAndroid(); else installListeners.push(offerAndroid);
    installTip.querySelector("[data-install-button]").addEventListener("click", async () => {
      if (await install()) installTip.hidden = true;
    });
    installTip.querySelector("[data-install-close]").addEventListener("click", () => {
      installTip.hidden = true;
      store.set("installTipCloses", String(closes + 1));
      store.set("installTipClosedAt", String(Date.now()));
    });
    // Back to this page from the history: the browser's install offer isn't carried over, so hide the button.
    window.addEventListener("pageshow", (event) => {
      if (event.persisted && !installPrompt) installTip.querySelector("[data-install-button]").hidden = true;
    });
  }
  window.addEventListener("appinstalled", () => {
    if (installTip) installTip.hidden = true;
    store.set("installTipCloses", "2");
  });

  // "You're in!" (right after sign-up): the steps for this phone, or straight on where it can't be done.
  const welcome = document.querySelector("[data-welcome]");
  if (welcome) {
    const next = welcome.dataset.next || "/";
    const addButton = welcome.querySelector("[data-welcome-add]");
    const offerAndroid = () => { addButton.hidden = false; };
    if (installed) {
      location.replace(next);
    } else if (iosSafari) {
      welcome.querySelector("[data-welcome-ios]").hidden = false;
    } else if (installPrompt) {
      offerAndroid();
    } else if (androidChrome) {
      // Chrome may take a while to offer its one-tap install: show its menu steps now, the button when it comes.
      welcome.querySelector("[data-welcome-android]").hidden = false;
      installListeners.push(() => { welcome.querySelector("[data-welcome-android]").hidden = true; offerAndroid(); });
    } else {
      installListeners.push(offerAndroid);
      setTimeout(() => { if (addButton.hidden) location.replace(next); }, 1500);  // nothing to offer here
    }
    addButton.addEventListener("click", async () => {
      if (await install()) location.replace(next);
    });
    // "Maybe later" counts as closing the home-screen card: it doesn't pop up again on the very next page.
    const later = welcome.querySelector("[data-welcome-later]");
    if (later) later.addEventListener("click", () => {
      const closes = Number(store.get("installTipCloses") || 0);
      store.set("installTipCloses", String(Math.max(closes, 1)));
      store.set("installTipClosedAt", String(Date.now()));
    });
  }

  // "⋯" menus (<details class="more-menu">, and a chat message's ⋯): Esc closes the open one and puts focus
  // back on its button.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const open = document.querySelector("details.more-menu[open], details.chat-more[open]");
    if (!open) return;
    open.open = false;
    open.querySelector("summary").focus();
  });

  // <form data-autosave>: each switch saves the moment it's flipped, in the background (no reload, no jump
  // back to the top). If that fails, the form is sent the normal way.
  // No connection: it says so and puts the switch back, instead of swapping the page for the browser's
  // "No internet" page. Saves go one at a time, in order, so two quick flips can't land the wrong way round.
  document.querySelectorAll("form[data-autosave]").forEach((form) => {
    const status = (form.closest(".card") || form).querySelector("[data-autosave-status]");
    let queue = Promise.resolve();
    form.addEventListener("change", (event) => {
      const changed = event.target;
      const before = changed.type === "checkbox" ? !changed.checked : null;
      const body = new FormData(form);
      if (status) status.textContent = "Saving…";
      queue = queue.then(async () => {
        let response;
        try {
          response = await fetch(form.action || location.href, { method: "POST", body, credentials: "same-origin" });
        } catch (error) {  // offline or the connection dropped
          if (before !== null) changed.checked = before;
          if (status) status.textContent = "Couldn't save. Check your connection and try again.";
          return;
        }
        // Logged out meanwhile (the log-in page answers) or the server said no: send it the normal way, which
        // shows the real reason (log in, or "your form expired").
        if (!response.ok || new URL(response.url).pathname.startsWith("/login")) { form.submit(); return; }
        if (status) status.textContent = "Saved";
      });
    });
  });

  // Profile pictures: no right-click / long-press menu (so no "Save image"); see style.css for iPhones.
  document.addEventListener("contextmenu", (event) => {
    if (event.target.closest(".avatar-img, .chat-avatar, .photo-lightbox, .lightbox.is-avatar")) event.preventDefault();
  });

  // data-zoom="dialog-id": a profile photo opens big; a tap anywhere (or Esc) closes it again. (The second tap
  // of a double tap doesn't count, so a double tap opens it too.) On your own profile (data-zoom-double) a
  // single tap still goes to "change photo" and a double tap shows it big.
  document.querySelectorAll("[data-zoom]").forEach((trigger) => {
    const dialog = document.getElementById(trigger.dataset.zoom);
    if (!dialog || typeof dialog.showModal !== "function") return;
    let openedAt = 0, pending = null;
    const open = () => { openedAt = Date.now(); dialog.showModal(); };
    trigger.addEventListener("click", (event) => {
      if (!("zoomDouble" in trigger.dataset)) { open(); return; }
      event.preventDefault();
      if (pending) { clearTimeout(pending); pending = null; open(); return; }
      pending = setTimeout(() => { pending = null; location.href = trigger.href; }, 280);
    });
    dialog.addEventListener("click", () => { if (Date.now() - openedAt > 400) dialog.close(); });
  });

  // Pull down at the top of a page to refresh it (phones). Not while typing, not with unsaved changes in a
  // form, not inside something that scrolls by itself (a chat), and not while a pop-up is open.
  if (window.matchMedia("(pointer: coarse)").matches) {
    const PULL = 70;  // how far to pull (px) before letting go refreshes
    let startY = null, pulled = 0, dirty = false;
    const hint = document.createElement("div");
    hint.className = "pull-refresh";
    hint.setAttribute("aria-hidden", "true");
    hint.innerHTML = '<span class="pull-arrow">↓</span><span class="pull-text">Pull to refresh</span>';
    document.body.append(hint);
    document.addEventListener("input", (event) => { if (event.target.closest("form")) dirty = true; });
    document.addEventListener("submit", () => { dirty = false; });
    const scrollsItself = (element) => {
      for (let el = element; el && el !== document.body; el = el.parentElement) {
        if (el.scrollTop > 0) return true;
        const overflow = getComputedStyle(el).overflowY;
        if ((overflow === "auto" || overflow === "scroll") && el.scrollHeight > el.clientHeight) return true;
      }
      return false;
    };
    document.addEventListener("touchstart", (event) => {
      const target = event.target;
      startY = null;
      if (window.scrollY > 0 || dirty || document.querySelector("dialog[open]") || event.touches.length > 1) return;
      if (target.closest("input, textarea, select, [contenteditable]") || scrollsItself(target)) return;
      startY = event.touches[0].clientY;
      pulled = 0;
    }, { passive: true });
    document.addEventListener("touchmove", (event) => {
      if (startY === null) return;
      pulled = Math.max(0, event.touches[0].clientY - startY);
      if (pulled > 0 && window.scrollY <= 0) {
        const shown = Math.min(pulled * 0.5, PULL);
        hint.style.transform = `translate(-50%, ${shown}px)`;
        hint.classList.add("is-pulling");
        hint.classList.toggle("is-ready", pulled > PULL * 1.4);
        hint.querySelector(".pull-text").textContent = pulled > PULL * 1.4 ? "Release to refresh" : "Pull to refresh";
      }
    }, { passive: true });
    document.addEventListener("touchend", () => {
      if (startY === null) return;
      startY = null;
      if (pulled > PULL * 1.4) {
        hint.classList.add("is-refreshing");
        hint.querySelector(".pull-text").textContent = "Refreshing…";
        location.reload();
      } else {
        hint.classList.remove("is-pulling", "is-ready");
        hint.style.transform = "";
      }
    });
  }

  // The bell rings when there's something new: when you open the app, refresh, or a new notification came in
  // since the last page (not on every page you tap through). The number pops in after the ring.
  const bells = [...document.querySelectorAll(".bell-link")];
  if (bells.length) {
    const badge = bells.map((bell) => bell.querySelector(".count-dot")).find(Boolean);
    const count = badge ? parseInt(badge.textContent, 10) || 0 : 0;
    const nav = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
    let last = null;
    try { last = sessionStorage.getItem("sc-bell"); sessionStorage.setItem("sc-bell", String(count)); } catch (e) { /* blocked */ }
    const fresh = last === null || (nav && nav.type === "reload") || count > parseInt(last, 10);
    if (count > 0 && fresh && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      bells.forEach((bell) => {
        bell.classList.add("is-ringing");
        setTimeout(() => bell.classList.remove("is-ringing"), 1500);
      });
    }
  }

  // Phone boxes: dashes appear as you type (206-555-0142 for +1 numbers; other countries in groups).
  document.querySelectorAll("input[data-phone]").forEach((input) => {
    const picker = input.closest(".phone-row") && input.closest(".phone-row").querySelector("[data-phone-country]");
    const format = () => {
      if (input.value.trim().startsWith("+")) return;  // a full international number: leave it as typed
      const us = !picker || picker.selectedOptions[0].dataset.dial === "1";
      let digits = input.value.replace(/\D/g, "");
      if (us && digits.length === 11 && digits.startsWith("1")) digits = digits.slice(1);
      if (us) digits = digits.slice(0, 10);
      const parts = us ? [digits.slice(0, 3), digits.slice(3, 6), digits.slice(6)]
        : (() => { const head = digits.slice(0, -4), groups = [];
                   for (let i = 0; i < head.length; i += 3) groups.push(head.slice(i, i + 3));
                   if (groups.length > 1 && groups[groups.length - 1].length === 1) groups.splice(-2, 2, groups.slice(-2).join(""));
                   return digits.length > 4 ? [...groups, digits.slice(-4)] : [digits]; })();
      input.value = parts.filter(Boolean).join("-");
    };
    input.addEventListener("input", format);
    if (picker) picker.addEventListener("change", format);
  });

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

  // <input type="file" data-max-files="10">: say how many photos are picked, and stop at the limit
  // (the server checks too). The count shows in the form's [data-picked] line.
  document.addEventListener("change", (event) => {
    const input = event.target;
    if (!input.matches || !input.matches("input[type=file][data-max-files]")) return;
    const max = Number(input.dataset.maxFiles);
    const line = input.form && input.form.querySelector("[data-picked]");
    if (input.files.length > max) {
      alert(`You can add up to ${max} photos to a post.`);
      input.value = "";
    }
    if (line) {
      const count = input.files.length;
      line.hidden = count === 0;
      line.textContent = count === 1 ? "1 photo added" : `${count} photos added`;
    }
  });

  // <input type="file" data-max-seconds="60">: a video longer than that is refused before it's uploaded
  // (the server checks too), and the form's [data-picked] line says how long it is.
  document.addEventListener("change", (event) => {
    const input = event.target;
    if (!input.matches || !input.matches("input[type=file][data-max-seconds]") || !input.files.length) return;
    const max = Number(input.dataset.maxSeconds);
    const line = input.form && input.form.querySelector("[data-picked]");
    const probe = document.createElement("video");
    probe.preload = "metadata";
    const url = URL.createObjectURL(input.files[0]);
    probe.addEventListener("loadedmetadata", () => {
      URL.revokeObjectURL(url);
      const seconds = Math.round(probe.duration);
      if (probe.duration > max + 0.5) {
        alert(`Videos can be up to 1 minute. This one is ${seconds} seconds: trim it first.`);
        input.value = "";
        if (line) line.hidden = true;
        return;
      }
      if (line) {
        line.hidden = false;
        line.textContent = `Video added (${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")})`;
      }
    });
    probe.addEventListener("error", () => URL.revokeObjectURL(url));  // the server will say what's wrong
    probe.src = url;
  });

  // The feed's post box is one line until you tap into it; then the sport, photos, video and plan open up.
  // (Without JavaScript it's simply all open.) The line under the sport says who will see the post.
  document.querySelectorAll("[data-composer]").forEach((form) => {
    form.classList.add("is-collapsible");
    const open = () => form.classList.add("is-open");
    form.addEventListener("focusin", open);
    form.addEventListener("click", open);
    const pick = form.querySelector("[data-sport-pick]");
    const hint = form.querySelector("[data-sport-hint]");
    const say = () => {
      const option = pick.options[pick.selectedIndex];
      if (!pick.value) { hint.textContent = "Pick a sport: everyone who plays it sees your post."; return; }
      const name = option.textContent.split(" / ")[0];
      hint.textContent = `#${name.toLowerCase().replace(/\s+/g, "")}: everyone who plays ${name} sees it, and it's in the ${name} channel.`;
    };
    if (pick && hint) { pick.addEventListener("change", say); say(); }
  });

  // Pull to refresh on the feed (and My clubs): pull down from the very top and let go to load what's new.
  // Phones' own pull-to-refresh is off on these pages (style.css), so there's one, and it works in the
  // home-screen app too. A post you're still typing is never thrown away.
  const pullPage = document.querySelector("[data-pull-refresh]");
  if (pullPage) {
    const NEED = 70;
    const bar = document.createElement("div");
    bar.className = "pull-refresh";
    bar.setAttribute("aria-hidden", "true");
    document.body.appendChild(bar);
    let startY = null;
    let pulled = 0;
    const typing = () => [...document.querySelectorAll("[data-composer] textarea")].some((box) => box.value.trim());
    const reset = () => { bar.style.setProperty("--pull", "0px"); bar.classList.remove("is-on", "is-ready"); };
    window.addEventListener("touchstart", (event) => {
      startY = window.scrollY <= 0 && event.touches.length === 1 && !typing() ? event.touches[0].clientY : null;
      pulled = 0;
    }, { passive: true });
    window.addEventListener("touchmove", (event) => {
      if (startY === null) return;
      if (window.scrollY > 0) { startY = null; reset(); return; }
      pulled = Math.max(0, event.touches[0].clientY - startY);
      bar.style.setProperty("--pull", `${Math.min(pulled, 120) * 0.6}px`);
      bar.classList.toggle("is-on", pulled > 8);
      bar.classList.toggle("is-ready", pulled > NEED);
      bar.textContent = pulled > NEED ? "↻ Let go to refresh" : "↓ Pull to refresh";
    }, { passive: true });
    window.addEventListener("touchend", () => {
      if (startY === null) return;
      startY = null;
      if (pulled > NEED) {
        bar.textContent = "Refreshing…";
        bar.classList.add("is-loading");
        window.location.reload();
      } else {
        reset();
      }
    });
  }
})();
