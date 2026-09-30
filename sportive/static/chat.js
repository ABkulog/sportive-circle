// Chat: checks for new messages every few seconds and adds them without reloading.
// Messages are added with textContent (never innerHTML), so nobody can inject code.
(function () {
  const box = document.querySelector(".chat[data-poll-url]");
  if (!box) return;
  const list = document.getElementById("chat-messages");
  const empty = document.getElementById("chat-empty");
  let lastId = parseInt(box.dataset.lastId, 10) || 0;

  // Phones: the page is pinned to the part of the screen you can actually see, so it never scrolls. When the
  // keyboard opens, iPhones slide the page up; the chat follows the visible part instead, so the back link,
  // the messages and the box all stay on screen (only the chat gets shorter).
  const topbar = document.querySelector(".topbar");
  const fit = () => {
    const root = document.documentElement;
    if (window.innerWidth > 700) { root.classList.remove("chat-pinned"); return; }
    root.classList.add("chat-pinned");
    const view = window.visualViewport;
    const viewTop = view ? view.offsetTop : 0;
    const viewBottom = viewTop + (view ? view.height : window.innerHeight);
    const barBottom = topbar && topbar.offsetParent ? topbar.getBoundingClientRect().bottom : 0;
    const top = Math.max(barBottom, viewTop);
    root.style.setProperty("--chat-top", top + "px");
    root.style.setProperty("--chat-height", Math.max(200, viewBottom - top) + "px");
    root.classList.toggle("keyboard-open", !!view && view.height < window.innerHeight - 120);
  };
  fit();
  window.addEventListener("resize", fit);
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", () => { fit(); scrollDown(); });
    window.visualViewport.addEventListener("scroll", fit);
  }
  const scrollDown = () => { list.scrollTop = list.scrollHeight; };
  const nearBottom = () => list.scrollHeight - list.scrollTop - list.clientHeight < 200;
  scrollDown();
  // Fonts and the layout settle after this runs, which moves things a little: jump to the newest again then.
  window.addEventListener("load", () => { fit(); scrollDown(); });
  if (document.fonts) document.fonts.ready.then(scrollDown);
  // Photos load after the page: keep the newest message in view as they appear.
  list.querySelectorAll("img").forEach((image) => {
    if (!image.complete) image.addEventListener("load", () => { if (nearBottom()) scrollDown(); });
  });

  const isGame = box.dataset.kind !== "dm";
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  function render(message) {
    const previous = list.querySelector(".chat-msg:last-of-type");
    const lastDay = [...list.querySelectorAll(".chat-day")].pop();
    if (!lastDay || lastDay.textContent !== message.day) {
      const day = el("li", "chat-day");
      day.appendChild(el("span", "", message.day));
      list.appendChild(day);
    }
    const sameGroup = previous && previous.dataset.sender === String(message.sender)
      && previous.dataset.day === message.day && list.lastElementChild === previous;
    if (sameGroup) previous.classList.add("is-grouped");  // its photo and time move to this new last one
    const item = el("li", "chat-msg" + (message.mine ? " is-mine" : "") + (sameGroup ? "" : " starts-group"));
    item.dataset.id = message.id;
    item.dataset.sender = message.sender;
    item.dataset.time = message.time;
    item.dataset.day = message.day;
    if (!message.mine) {
      const avatar = el("a", "chat-avatar");
      avatar.href = message.profile;
      avatar.tabIndex = -1;
      avatar.setAttribute("aria-label", message.name ? `${message.name}'s profile` : "Profile");
      if (message.avatar) {
        const image = el("img");
        image.src = message.avatar;
        image.alt = "";
        avatar.appendChild(image);
      } else {
        avatar.appendChild(el("span", "", message.initial));
      }
      item.appendChild(avatar);
    }
    const bubble = el("div", "chat-bubble" + (message.photo && !message.body ? " is-photo" : ""));
    if (!message.mine && isGame) bubble.appendChild(el("span", "chat-name", message.name));
    if (message.photo) {
      const link = el("a", "chat-photo");
      link.href = message.photo;
      link.target = "_blank";
      link.rel = "noopener";
      const image = el("img");
      image.src = message.photo;
      image.alt = `Photo from ${message.name}`;
      image.addEventListener("load", () => { if (nearBottom()) scrollDown(); });
      link.appendChild(image);
      bubble.appendChild(link);
    }
    if (message.body) bubble.appendChild(el("p", "", message.body));
    if (message.game) {
      const game = el("a", "chat-game" + (message.game.cancelled ? " is-cancelled" : ""));
      game.href = message.game.url;
      const emoji = el("span", "chat-game-emoji", message.game.emoji);
      emoji.setAttribute("aria-hidden", "true");
      const info = el("span");
      info.append(el("strong", "", message.game.title), " ",
                  el("small", "", `${message.game.cancelled ? "Canceled" : message.game.when} · ${message.game.where}`));
      game.append(emoji, info);
      bubble.appendChild(game);
    }
    const meta = el("span", "chat-meta");
    meta.appendChild(el("time", "", message.time));
    if (message.report) {
      const more = el("details", "chat-more");
      const summary = el("summary", "", "⋯");
      summary.setAttribute("aria-label", "More options for this message");
      const report = el("a", "", "Report");
      report.href = message.report;
      more.append(summary, report);
      meta.appendChild(more);
    }
    bubble.appendChild(meta);
    item.appendChild(bubble);
    list.appendChild(item);
  }

  // Albums, like WhatsApp: 4+ photos in a row from one person show as one 2x2 grid, "+N" on the 4th opens the
  // rest. The grid sits in the last message of the run (with its words, time and Seen); the others are hidden.
  // Rebuilt from scratch whenever messages arrive, so a run that grows just becomes a bigger album.
  const ALBUM_FROM = 4;
  const opened = new Set();  // albums someone tapped "+N" on (by their first message's id)
  function makeAlbums() {
    list.querySelectorAll(".chat-album").forEach((album) => album.remove());
    list.querySelectorAll(".in-album").forEach((item) => item.classList.remove("in-album"));
    list.querySelectorAll(".has-album").forEach((item) => {
      item.classList.remove("has-album");
      if (item.dataset.albumStart) { item.classList.remove("starts-group"); delete item.dataset.albumStart; }
    });
    let run = [];
    const finish = () => {
      if (run.length >= ALBUM_FROM) buildAlbum(run);
      run = [];
    };
    list.querySelectorAll(":scope > li").forEach((item) => {
      const photo = item.classList.contains("chat-msg") && item.querySelector(":scope .chat-bubble > .chat-photo");
      const last = run[run.length - 1];
      if (!photo || (last && (last.dataset.sender !== item.dataset.sender || last.dataset.day !== item.dataset.day))) finish();
      if (!photo) return;
      run.push(item);
      if (item.querySelector(".chat-bubble > p")) finish();  // words end an album (they're its caption)
    });
    finish();
  }
  function buildAlbum(run) {
    const host = run[run.length - 1], key = run[0].dataset.id;
    const showAll = opened.has(key);
    const album = el("div", "chat-album");
    run.forEach((item, i) => {
      if (!showAll && i >= ALBUM_FROM) return;
      const source = item.querySelector(".chat-bubble > .chat-photo");
      const tile = el("a");
      tile.href = source.href;
      tile.target = "_blank";
      tile.rel = "noopener";
      const image = el("img");
      image.src = source.querySelector("img").src;
      image.alt = source.querySelector("img").alt;
      tile.appendChild(image);
      if (!showAll && i === ALBUM_FROM - 1 && run.length > ALBUM_FROM) {
        tile.appendChild(el("span", "chat-album-more", `+${run.length - ALBUM_FROM}`));
        tile.setAttribute("aria-label", `Show all ${run.length} photos`);
        tile.addEventListener("click", (event) => { event.preventDefault(); opened.add(key); makeAlbums(); });
      }
      album.appendChild(tile);
    });
    run.slice(0, -1).forEach((item) => item.classList.add("in-album"));
    host.classList.add("has-album");
    if (run[0].classList.contains("starts-group") && !host.classList.contains("starts-group")) {
      host.classList.add("starts-group");
      host.dataset.albumStart = "1";
    }
    const bubble = host.querySelector(".chat-bubble");
    bubble.insertBefore(album, bubble.querySelector(".chat-photo"));
  }
  makeAlbums();

  // Photo viewer: tapping a photo opens it full screen (not a new tab). Swipe or use the arrows to go through
  // every photo in the chat; ×, Esc, a tap on the dark part or a swipe down closes it.
  const viewer = el("div", "lightbox");
  viewer.hidden = true;
  viewer.setAttribute("role", "dialog");
  viewer.setAttribute("aria-modal", "true");
  viewer.setAttribute("aria-label", "Photo");
  const viewerImage = el("img");
  const viewerCount = el("span", "lightbox-count");
  const viewerButton = (className, label, text) => {
    const button = el("button", className, text);
    button.type = "button";
    button.setAttribute("aria-label", label);
    return button;
  };
  const closeButton = viewerButton("lightbox-close", "Close", "×");
  const prevButton = viewerButton("lightbox-prev", "Previous photo", "‹");
  const nextButton = viewerButton("lightbox-next", "Next photo", "›");
  viewer.append(viewerImage, viewerCount, closeButton, prevButton, nextButton);
  document.body.appendChild(viewer);
  let shown = [], at = 0, openedFrom = null;
  const showPhoto = (i) => {
    at = (i + shown.length) % shown.length;
    viewerImage.src = shown[at].src;
    viewerImage.alt = shown[at].alt;
    const many = shown.length > 1;
    viewerCount.textContent = many ? `${at + 1} / ${shown.length}` : "";
    prevButton.hidden = nextButton.hidden = !many;
  };
  function openViewer(photos, i, isAvatar = false) {
    viewer.classList.toggle("is-avatar", isAvatar);  // profile pictures can't be long-pressed to save
    openedFrom = document.activeElement;
    if (openedFrom && openedFrom.blur) openedFrom.blur();  // puts the keyboard away
    shown = photos;
    showPhoto(i);
    viewer.hidden = false;
    closeButton.focus();
  }
  const closeViewer = () => {
    viewer.hidden = true;
    viewerImage.removeAttribute("src");
  };
  closeButton.addEventListener("click", closeViewer);
  prevButton.addEventListener("click", () => showPhoto(at - 1));
  nextButton.addEventListener("click", () => showPhoto(at + 1));
  viewer.addEventListener("click", (event) => { if (event.target === viewer) closeViewer(); });
  document.addEventListener("keydown", (event) => {
    if (viewer.hidden) return;
    if (event.key === "Escape") closeViewer();
    else if (event.key === "ArrowLeft") showPhoto(at - 1);
    else if (event.key === "ArrowRight") showPhoto(at + 1);
  });
  let viewerTouch = null;
  viewer.addEventListener("touchstart", (event) => {
    viewerTouch = { x: event.touches[0].clientX, y: event.touches[0].clientY };
  }, { passive: true });
  viewer.addEventListener("touchend", (event) => {
    if (!viewerTouch) return;
    const dx = event.changedTouches[0].clientX - viewerTouch.x, dy = event.changedTouches[0].clientY - viewerTouch.y;
    viewerTouch = null;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) showPhoto(at + (dx < 0 ? 1 : -1));
    else if (dy > 80 && dy > Math.abs(dx)) closeViewer();
  });
  // Every photo in the chat, oldest first (album tiles open the same photos).
  const chatPhotos = () => [...list.querySelectorAll(".chat-bubble > .chat-photo")].map((link) => {
    const image = link.querySelector("img");
    return { src: link.href, alt: image ? image.alt : "Photo" };
  });
  list.addEventListener("click", (event) => {
    const link = event.target.closest(".chat-photo, .chat-album a");
    if (!link || event.defaultPrevented) return;  // "+N" opens the album instead
    event.preventDefault();
    const photos = chatPhotos();
    openViewer(photos, Math.max(0, photos.findIndex((photo) => photo.src === link.href)));
  });

  // Profile pictures: one tap opens their profile, a double tap shows the picture big.
  let avatarTap = null;
  list.addEventListener("click", (event) => {
    const avatar = event.target.closest(".chat-avatar");
    if (!avatar) return;
    const image = avatar.querySelector("img");
    if (!image) return;  // no picture (initials): straight to the profile
    event.preventDefault();
    if (avatarTap && avatarTap.avatar === avatar) {
      clearTimeout(avatarTap.timer);
      avatarTap = null;
      const big = new URL(image.src, location.href);
      big.searchParams.delete("s");
      openViewer([{ src: big.href, alt: avatar.getAttribute("aria-label") || "Profile picture" }], 0, true);
      return;
    }
    if (avatarTap) clearTimeout(avatarTap.timer);
    avatarTap = { avatar, timer: setTimeout(() => { avatarTap = null; location.href = avatar.href; }, 280) };
  });

  // "Seen" / "Delivered" under my newest message (only when the newest message is mine).
  function showStatus(status) {
    list.querySelectorAll(".chat-seen").forEach((node) => node.remove());
    const newest = [...list.querySelectorAll(".chat-msg")].pop();
    if (!status || !newest || newest.dataset.id !== String(status.id)) return;
    newest.querySelector(".chat-meta").appendChild(el("span", "chat-seen", status.text));
  }

  // Swipe left on the messages to see when each one was sent (the times sit just off the right edge).
  let swipe = null;
  list.addEventListener("touchstart", (event) => {
    swipe = { x: event.touches[0].clientX, y: event.touches[0].clientY, sideways: null };
  }, { passive: true });
  list.addEventListener("touchmove", (event) => {
    if (!swipe) return;
    const dx = event.touches[0].clientX - swipe.x, dy = event.touches[0].clientY - swipe.y;
    if (swipe.sideways === null && Math.abs(dx) + Math.abs(dy) > 10) swipe.sideways = Math.abs(dx) > Math.abs(dy);
    if (!swipe.sideways) return;
    list.classList.add("show-times");
    list.style.setProperty("--swipe", Math.max(-88, Math.min(0, dx)) + "px");
  }, { passive: true });
  const endSwipe = () => {
    swipe = null;
    list.classList.remove("show-times");
    list.style.removeProperty("--swipe");
  };
  list.addEventListener("touchend", endSwipe);
  list.addEventListener("touchcancel", endSwipe);

  async function poll(now) {
    if (document.hidden && !now) return;
    try {
      const response = await fetch(`${box.dataset.pollUrl}?after=${lastId}`, { headers: { Accept: "application/json" } });
      if (new URL(response.url).pathname.startsWith("/login")) { location.reload(); return; }  // logged out
      if (!response.ok) return;
      const { messages, status } = await response.json();
      if (!messages.length) { showStatus(status); return; }
      const wasNearBottom = nearBottom();
      messages.forEach(render);
      makeAlbums();
      lastId = messages[messages.length - 1].id;
      showStatus(status);
      if (empty) empty.hidden = true;
      box.classList.remove("is-empty");
      if (wasNearBottom) scrollDown();
    } catch (error) { /* offline for a moment; try again next time */ }
  }
  setInterval(poll, 5000);

  // Enter sends, Shift+Enter makes a new line; the box grows as you type.
  const textarea = box.querySelector("textarea");
  const photoInput = box.querySelector("[data-chat-photo]");
  const attached = box.querySelector("[data-chat-attached]");
  const MAX_PHOTOS = 10;  // each goes as its own message, one after another (the rate limit is 20 a minute)
  let picked = [];        // the photos picked, shown above the box until they're sent or removed
  const hasPhoto = () => picked.length > 0;
  if (textarea) {
    const grow = () => {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
    };
    textarea.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && (textarea.value.trim() || hasPhoto())) {
        event.preventDefault();
        if (textarea.form.requestSubmit) textarea.form.requestSubmit();  // Safari 16+
        else if (textarea.form.dispatchEvent(new Event("submit", { cancelable: true }))) textarea.form.submit();
      }
    });
    textarea.addEventListener("input", grow);
    // Tapping the messages (not a photo, link or ⋯ menu) puts the keyboard away; tapping the box brings it back.
    // (A touch, not a click: iPhones don't send clicks for taps on plain text.)
    const putKeyboardAway = (event) => {
      if (document.activeElement === textarea && !event.target.closest("a, button, summary, details")) textarea.blur();
    };
    list.addEventListener("pointerdown", putKeyboardAway);
    if (empty) empty.addEventListener("pointerdown", putKeyboardAway);
    // Sending happens in the background: the page doesn't reload, the box empties and keeps the keyboard up,
    // and the message shows right away. (Without JavaScript the form still posts the normal way.)
    const form = textarea.form;
    const sendButton = form.querySelector(".chat-send");
    const errorLine = box.querySelector("[data-chat-error]");
    const showError = (text) => { if (errorLine) { errorLine.textContent = text || ""; errorLine.hidden = !text; } };
    let sending = false;
    // Tapping Send shouldn't take the focus from the box (on phones that would close the keyboard).
    sendButton.addEventListener("pointerdown", (event) => event.preventDefault());
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!textarea.value.trim() && !hasPhoto()) { textarea.focus(); return; }  // nothing to send
      if (sending) return;
      sending = true;
      sendButton.disabled = true;
      try {
        // One request per photo (the words go with the last one), or one for words only.
        const photos = picked.length ? [...picked] : [null];
        for (let i = 0; i < photos.length; i++) {
          const data = new FormData(form);
          data.delete("photo");
          if (photos[i]) data.append("photo", photos[i]);
          if (i < photos.length - 1) data.set("body", "");
          const response = await fetch(form.action, { method: "POST", body: data,
                                                      headers: { "X-Chat-Send": "1", Accept: "application/json" } });
          if (new URL(response.url).pathname.startsWith("/login")) { location.reload(); return; }  // logged out
          if (response.status === 413) { showError("That photo is too big. Pick one under 8 MB."); break; }
          const answer = await response.json();
          if (!answer.ok) { showError(answer.error); break; }
          if (photos[i]) photoInput.dispatchEvent(new CustomEvent("chat:sent", { detail: photos[i] }));
          if (i === photos.length - 1) {
            textarea.value = "";
            grow();
            showError(null);
          }
        }
        await poll(true);
        scrollDown();
      } catch (error) {
        showError("Couldn't send. Check your connection and try again.");
      } finally {
        sending = false;
        sendButton.disabled = false;
        textarea.focus();
      }
    });
    // Quick replies fill the box (you can still change them before sending).
    box.querySelectorAll("[data-quick]").forEach((chip) => {
      chip.addEventListener("click", () => {
        textarea.value = textarea.value.trim() ? `${textarea.value.trim()} ${chip.dataset.quick}` : chip.dataset.quick;
        grow();
        textarea.focus();
      });
    });
  }
  // Picked photos (up to 10, picked in one go or a few at a time) show above the box until sent or removed.
  if (photoInput && attached) {
    const thumbs = attached.querySelector("[data-chat-thumbs]");
    const show = () => {
      thumbs.querySelectorAll("img").forEach((image) => URL.revokeObjectURL(image.src));
      thumbs.replaceChildren(...picked.map((file) => {
        const image = el("img");
        image.alt = "";
        image.src = URL.createObjectURL(file);
        return image;
      }));
      attached.hidden = !picked.length;
    };
    photoInput.addEventListener("change", () => {
      const chosen = [...photoInput.files].filter((file) => file.type.startsWith("image/"));
      photoInput.value = "";  // the list lives in `picked`, so the same photo can be picked again later
      picked = picked.concat(chosen).slice(0, MAX_PHOTOS);
      const errorLine = box.querySelector("[data-chat-error]");
      if (errorLine && picked.length === MAX_PHOTOS && chosen.length) {
        errorLine.textContent = `Up to ${MAX_PHOTOS} photos at a time.`;
        errorLine.hidden = false;
      }
      show();
      if (textarea) textarea.focus();
    });
    attached.querySelector("[data-chat-unattach]").addEventListener("click", () => { picked = []; show(); });
    photoInput.addEventListener("chat:sent", (event) => {  // one photo went: take it off the list
      picked = picked.filter((file) => file !== event.detail);
      show();
    });
  }
})();
