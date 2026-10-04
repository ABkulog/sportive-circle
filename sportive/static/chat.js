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
    const item = el("li", "chat-msg" + (message.mine ? " is-mine" : "") + (message.deleted ? " is-deleted" : "")
                    + (sameGroup ? "" : " starts-group"));
    item.dataset.id = message.id;
    item.dataset.sender = message.sender;
    item.dataset.time = message.time;
    item.dataset.day = message.day;
    if (!message.mine) {
      const avatar = el("a", "chat-avatar");
      avatar.href = message.profile;
      avatar.tabIndex = -1;
      avatar.setAttribute("aria-label", message.name ? `${message.name}'s profile` : "Profile");
      if (message.avatar) {  // a background, not an <img>, so it can't be long-pressed and saved
        const photo = el("span", "chat-avatar-photo");
        photo.dataset.src = message.avatar;
        photo.style.backgroundImage = `url("${encodeURI(message.avatar)}")`;
        avatar.appendChild(photo);
      } else {
        avatar.appendChild(el("span", "", message.initial));
      }
      item.appendChild(avatar);
    }
    const bubble = el("div", "chat-bubble" + (message.photo && !message.body ? " is-photo" : ""));
    bubble.tabIndex = 0;  // Enter opens the react / copy menu (see keydown below)
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
    showReactions(item, message.reactions || []);
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
  viewerImage.alt = "";  // (described by the dialog's label; the photo is set when it opens)
  const viewerAvatar = el("div", "lightbox-avatar");  // profile pictures: a background, so no "Save image"
  viewerAvatar.setAttribute("role", "img");
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
  viewer.append(viewerImage, viewerAvatar, viewerCount, closeButton, prevButton, nextButton);
  document.body.appendChild(viewer);
  let shown = [], at = 0, openedFrom = null;
  const showPhoto = (i) => {
    at = (i + shown.length) % shown.length;
    if (!viewer.classList.contains("is-avatar")) viewerImage.src = shown[at].src;
    viewerImage.alt = shown[at].alt;
    const many = shown.length > 1;
    viewerCount.textContent = many ? `${at + 1} / ${shown.length}` : "";
    prevButton.hidden = nextButton.hidden = !many;
  };
  function openViewer(photos, i, isAvatar = false) {
    viewer.classList.toggle("is-avatar", isAvatar);  // profile pictures can't be long-pressed to save
    viewerImage.hidden = isAvatar;
    viewerAvatar.hidden = !isAvatar;
    if (isAvatar) {
      viewerAvatar.style.backgroundImage = `url("${encodeURI(photos[0].src)}")`;
      viewerAvatar.setAttribute("aria-label", photos[0].alt);
    }
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
    // Back to the photo it was opened from (not the message box: that would pop the phone's keyboard up).
    if (openedFrom && openedFrom.isConnected && openedFrom.focus && openedFrom.tagName !== "TEXTAREA") {
      openedFrom.focus({ preventScroll: true });
    }
  };
  closeButton.addEventListener("click", closeViewer);
  prevButton.addEventListener("click", () => showPhoto(at - 1));
  nextButton.addEventListener("click", () => showPhoto(at + 1));
  viewer.addEventListener("click", (event) => { if (event.target === viewer) closeViewer(); });
  document.addEventListener("keydown", (event) => {
    if (viewer.hidden) return;
    if (event.key === "Escape") closeViewer();
    else if (event.key === "Tab") {  // it's a full-screen viewer: Tab stays on its buttons
      const buttons = [...viewer.querySelectorAll("button")].filter((button) => !button.hidden);
      const here = buttons.indexOf(document.activeElement);
      event.preventDefault();
      buttons[(here + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length].focus();
    } else if (event.key === "ArrowLeft") showPhoto(at - 1);
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
  const openPhoto = (link) => {
    const photos = chatPhotos();
    openViewer(photos, Math.max(0, photos.findIndex((photo) => photo.src === link.href)));
  };

  // Reactions, like WhatsApp: hold a message (right-click on a laptop) for the reaction bar, Copy and Report;
  // a double tap (double click) is ❤️; tapping a reaction under a message adds or takes off yours.
  const REACTIONS = ["❤️", "😂", "👍", "🔥", "😮", "😢"];  // the same list as social.REACTIONS
  const csrf = () => (document.querySelector('input[name="csrf_token"]') || {}).value || "";
  function showReactions(item, reactions) {
    const json = JSON.stringify(reactions || []);
    if (item.dataset.reactions === json && (reactions || []).length === item.querySelectorAll(".chat-reaction").length) return;
    item.dataset.reactions = json;
    const bubble = item.querySelector(".chat-bubble");
    const old = bubble.querySelector(".chat-reactions");
    if (old) old.remove();
    if (!reactions || !reactions.length) return;
    const row = el("div", "chat-reactions");
    reactions.forEach((reaction) => {
      const chip = el("button", "chat-reaction" + (reaction.mine ? " is-mine" : ""),
                      reaction.count > 1 ? `${reaction.emoji} ${reaction.count}` : reaction.emoji);
      chip.type = "button";
      chip.dataset.emoji = reaction.emoji;
      chip.setAttribute("aria-label", `${reaction.emoji} ${reaction.count}${reaction.mine ? ", yours" : ""}`);
      row.appendChild(chip);
    });
    bubble.appendChild(row);
  }
  list.querySelectorAll(".chat-msg").forEach((item) => {
    let reactions = [];
    try { reactions = JSON.parse(item.dataset.reactions || "[]"); } catch (error) { /* leave it empty */ }
    item.dataset.reactions = "";
    showReactions(item, reactions);
  });
  // Delete for everyone: the bubble keeps its place and says it was deleted (the other side sees it on its next check).
  function markDeleted(item, text) {
    if (!item || item.classList.contains("is-deleted")) return;
    item.classList.add("is-deleted");
    const bubble = item.querySelector(".chat-bubble");
    bubble.classList.remove("is-photo");
    bubble.querySelectorAll(".chat-photo, .chat-game, :scope > p, .chat-more").forEach((part) => part.remove());
    bubble.insertBefore(el("p", "", text || "🚫 Message deleted"), bubble.querySelector(".chat-meta"));
    item.dataset.reactions = "[]";
    showReactions(item, []);
  }
  async function deleteMessage(item) {
    if (!item || !item.dataset.id || !confirm("Delete this message for everyone?")) return;
    const data = new FormData();
    data.append("csrf_token", csrf());
    data.append("kind", box.dataset.kind === "dm" ? "dm" : "game");
    data.append("id", item.dataset.id);
    try {
      const response = await fetch(box.dataset.deleteUrl, { method: "POST", body: data,
                                                            headers: { Accept: "application/json" } });
      if (response.ok) markDeleted(item, (await response.json()).body);
    } catch (error) { /* offline: nothing changes */ }
  }
  async function react(item, emoji) {
    if (!item || !item.dataset.id) return;
    const data = new FormData();
    data.append("csrf_token", csrf());
    data.append("kind", box.dataset.kind === "dm" ? "dm" : "game");
    data.append("id", item.dataset.id);
    data.append("emoji", emoji);
    try {
      const response = await fetch(box.dataset.reactUrl, { method: "POST", body: data,
                                                           headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const answer = await response.json();
      showReactions(item, answer.reactions);
    } catch (error) { /* offline: nothing changes */ }
  }
  function heart(item) {
    const pop = el("span", "chat-heart-pop", "❤️");
    pop.setAttribute("aria-hidden", "true");
    item.querySelector(".chat-bubble").appendChild(pop);
    setTimeout(() => pop.remove(), 700);
    const mine = JSON.parse(item.dataset.reactions || "[]").find((reaction) => reaction.mine);
    // A double tap only adds a heart (like Instagram). While the first one is on its way, another double tap
    // waits for it: otherwise on a slow connection the second would take the heart back off.
    if (item.dataset.hearting || (mine && mine.emoji === "❤️")) return;
    item.dataset.hearting = "1";
    Promise.resolve(react(item, "❤️")).finally(() => { delete item.dataset.hearting; });
  }

  // The menu that opens when you hold a message.
  const menu = el("div", "chat-menu");
  menu.hidden = true;
  menu.setAttribute("role", "dialog");  // a small panel of buttons (not an arrow-key menu)
  menu.setAttribute("aria-label", "Message options");
  document.body.appendChild(menu);
  let menuFor = null;
  // refocus: put the keyboard (or screen reader) back on the message, so nobody loses their place in the chat.
  const closeMenu = (refocus) => {
    const item = menuFor;
    const wasInside = menu.contains(document.activeElement);
    menu.hidden = true;
    if (item) item.classList.remove("is-held");
    menuFor = null;
    if (item && refocus === true && wasInside) item.querySelector(".chat-bubble").focus({ preventScroll: true });
  };
  // Tab stays inside the open panel (it sits at the end of the page) until it's closed.
  menu.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const stops = [...menu.querySelectorAll("button, a[href]")];
    if (!stops.length) return;
    const at = stops.indexOf(document.activeElement);
    const next = event.shiftKey ? (at <= 0 ? stops.length - 1 : at - 1) : (at + 1) % stops.length;
    event.preventDefault();
    stops[next].focus();
  });
  function openMenu(item) {
    closeMenu();
    menuFor = item;
    item.classList.add("is-held");
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();  // keyboard away
    const mine = (JSON.parse(item.dataset.reactions || "[]").find((reaction) => reaction.mine) || {}).emoji;
    const emojis = el("div", "chat-menu-emojis");
    REACTIONS.forEach((emoji) => {
      const button = el("button", emoji === mine ? "is-mine" : "", emoji);
      button.type = "button";
      button.setAttribute("aria-label", `React ${emoji}`);
      button.addEventListener("click", () => { react(item, emoji); closeMenu(true); });
      emojis.appendChild(button);
    });
    const actions = el("div", "chat-menu-actions");
    const text = item.querySelector(".chat-bubble > p");
    if (text && navigator.clipboard && !item.classList.contains("is-deleted")) {
      const copy = el("button", "", "Copy");
      copy.type = "button";
      copy.addEventListener("click", () => { navigator.clipboard.writeText(text.textContent).catch(() => {}); closeMenu(true); });
      actions.appendChild(copy);
    }
    const report = item.querySelector(".chat-more a");
    if (report) {
      const link = el("a", "is-danger", "Report");
      link.href = report.href;
      actions.appendChild(link);
    }
    if (item.classList.contains("is-mine") && !item.classList.contains("is-deleted") && box.dataset.deleteUrl) {
      const remove = el("button", "is-danger", "Delete");
      remove.type = "button";
      remove.addEventListener("click", () => { closeMenu(true); deleteMessage(item); });
      actions.appendChild(remove);
    }
    menu.replaceChildren(emojis);
    if (actions.children.length) menu.appendChild(actions);
    menu.hidden = false;
    const spot = item.querySelector(".chat-bubble").getBoundingClientRect();
    const width = menu.offsetWidth, height = menu.offsetHeight;
    let top = spot.top - height - 8;
    if (top < 70) top = Math.min(spot.bottom + 8, window.innerHeight - height - 8);
    const left = item.classList.contains("is-mine") ? spot.right - width : spot.left;
    menu.style.top = Math.max(8, top) + "px";
    menu.style.left = Math.min(Math.max(8, left), window.innerWidth - width - 8) + "px";
    const first = menu.querySelector("button");
    if (first) first.focus({ preventScroll: true });
  }
  document.addEventListener("pointerdown", (event) => {
    if (!menu.hidden && !menu.contains(event.target)) closeMenu();
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !menu.hidden) closeMenu(true); });
  list.addEventListener("scroll", closeMenu, { passive: true });

  // Hold (about half a second, without moving) opens the menu.
  let hold = null, held = false;
  list.addEventListener("pointerdown", (event) => {
    const item = event.target.closest(".chat-msg");
    if (!item || !event.target.closest(".chat-bubble") || event.target.closest(".chat-reaction")) return;
    held = false;
    hold = { x: event.clientX, y: event.clientY, timer: setTimeout(() => { held = true; hold = null; openMenu(item); }, 450) };
  });
  const cancelHold = () => { if (hold) { clearTimeout(hold.timer); hold = null; } };
  list.addEventListener("pointermove", (event) => {
    if (hold && Math.hypot(event.clientX - hold.x, event.clientY - hold.y) > 8) cancelHold();
  });
  list.addEventListener("pointerup", cancelHold);
  list.addEventListener("pointercancel", cancelHold);
  // Keyboard: Enter or Space on a focused message opens the menu (react, copy, report).
  list.addEventListener("keydown", (event) => {
    if ((event.key === "Enter" || event.key === " ") && event.target.classList.contains("chat-bubble")) {
      event.preventDefault();
      openMenu(event.target.closest(".chat-msg"));
    }
  });
  list.addEventListener("contextmenu", (event) => {  // right-click on a laptop (and long-press on Android)
    const item = event.target.closest(".chat-msg");
    if (!item || !event.target.closest(".chat-bubble")) return;
    event.preventDefault();
    cancelHold();
    if (menuFor !== item) openMenu(item);
  });

  // Taps: a reaction under a message toggles yours; two quick taps on a message is ❤️; one tap on a photo
  // opens it (a moment later, in case a second tap is coming).
  let lastTap = null;
  list.addEventListener("click", (event) => {
    if (held) { held = false; event.preventDefault(); return; }  // the end of a hold, not a tap
    if (event.defaultPrevented) return;                         // "+N" opens the album instead
    const item = event.target.closest(".chat-msg");
    const chip = event.target.closest(".chat-reaction");
    if (chip) { react(item, chip.dataset.emoji); return; }
    if (!item || event.target.closest(".chat-avatar, .chat-more, .chat-game")) return;
    const bubble = event.target.closest(".chat-bubble");
    if (!bubble) return;
    const photo = event.target.closest(".chat-photo, .chat-album a");
    if (photo) event.preventDefault();
    const now = Date.now();
    if (lastTap && lastTap.item === item && now - lastTap.at < 320) {
      clearTimeout(lastTap.timer);
      lastTap = null;
      heart(item);
      return;
    }
    if (lastTap) clearTimeout(lastTap.timer);
    lastTap = { item, at: now, timer: photo ? setTimeout(() => { lastTap = null; openPhoto(photo); }, 300) : null };
  });

  // Profile pictures: one tap opens their profile, a double tap shows the picture big.
  let avatarTap = null;
  list.addEventListener("click", (event) => {
    const avatar = event.target.closest(".chat-avatar");
    if (!avatar) return;
    const image = avatar.querySelector(".chat-avatar-photo");
    if (!image) return;  // no picture (initials): straight to the profile
    event.preventDefault();
    if (avatarTap && avatarTap.avatar === avatar) {
      clearTimeout(avatarTap.timer);
      avatarTap = null;
      const big = new URL(image.dataset.src, location.href);
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

  // One check at a time: on a slow connection the 5-second timer would otherwise start new checks before the
  // last one answered, and each answer would add the same new messages again.
  let polling = null;
  let whenMineArrives = null;  // set while a send that took too long might still arrive
  async function poll(now) {
    if (document.hidden && !now) return;
    if (polling) {
      if (!now) return;          // the timer can skip a turn
      await polling.catch(() => {});  // after sending: wait for the one in flight, then ask again
    }
    polling = check();
    try { await polling; } finally { polling = null; }
  }
  async function check() {
    try {
      const first = list.querySelector(".chat-msg");
      const response = await fetch(`${box.dataset.pollUrl}?after=${lastId}&from=${first ? first.dataset.id : 0}`,
                                   { headers: { Accept: "application/json" } });
      if (new URL(response.url).pathname.startsWith("/login")) {  // logged out (maybe in another tab)
        const draft = box.querySelector("textarea");
        if (!draft || !draft.value.trim()) location.reload();  // never throw away something being typed
        return;
      }
      if (!response.ok) return;
      const answer = await response.json();
      const { status, reactions } = answer;
      (answer.deleted || []).forEach((id) => markDeleted(list.querySelector(`.chat-msg[data-id="${id}"]`)));
      const messages = answer.messages.filter((m) => m.id > lastId && !list.querySelector(`.chat-msg[data-id="${m.id}"]`));
      if (reactions) {  // reactions change on old messages too: bring every message up to date
        list.querySelectorAll(".chat-msg").forEach((item) => showReactions(item, reactions[item.dataset.id] || []));
      }
      if (!messages.length) { showStatus(status); return; }
      const wasNearBottom = nearBottom();
      messages.forEach(render);
      if (whenMineArrives) whenMineArrives(messages);  // a slow send that showed up after all
      makeAlbums();
      lastId = messages[messages.length - 1].id;
      showStatus(status);
      if (empty) empty.hidden = true;
      box.classList.remove("is-empty");
      if (wasNearBottom) scrollDown();
    } catch (error) { /* offline for a moment; try again next time */ }
  }
  setInterval(poll, 5000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });  // back to the tab: catch up now

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
      // Not the Enter that finishes Japanese, Chinese or Korean typing (isComposing / 229): that one picks the word.
      if (event.isComposing || event.keyCode === 229) return;
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
      const sentText = textarea.value;  // what's going out: anything typed while it sends stays in the box
      const sentAfter = lastId;         // newer messages of mine than this one are what this send made
      const takeSentText = () => {      // take away only what was sent: words typed while it was on its way stay
        textarea.value = textarea.value.startsWith(sentText) ? textarea.value.slice(sentText.length).trimStart() : textarea.value;
        grow();
      };
      try {
        // One request per photo (the words go with the last one), or one for words only.
        const photos = picked.length ? [...picked] : [null];
        for (let i = 0; i < photos.length; i++) {
          const data = new FormData(form);
          data.delete("photo");
          if (photos[i]) data.append("photo", photos[i]);
          if (i < photos.length - 1) data.set("body", "");
          // A send that hangs (a bad connection) gives up after 20 seconds, so the box doesn't stay stuck.
          const timeout = new AbortController();
          const timer = setTimeout(() => timeout.abort(), photos[i] ? 90000 : 20000);  // a photo upload takes longer
          let response;
          try {
            response = await fetch(form.action, { method: "POST", body: data, signal: timeout.signal,
                                                  headers: { "X-Chat-Send": "1", Accept: "application/json" } });
          } finally { clearTimeout(timer); }
          if (new URL(response.url).pathname.startsWith("/login")) {  // logged out (on another device, say)
            showError("You were logged out. Copy your message, then reload the page and log in.");
            break;
          }
          if (response.status === 413) { showError("That photo is too big. Pick one under 8 MB."); break; }
          if (!(response.headers.get("Content-Type") || "").includes("json")) {  // e.g. logged out in another tab
            showError("You were logged out. Copy your message, then reload the page and log in.");
            break;
          }
          const answer = await response.json();
          if (!answer.ok) { showError(answer.error); break; }
          if (photos[i]) photoInput.dispatchEvent(new CustomEvent("chat:sent", { detail: photos[i] }));
          if (i === photos.length - 1) {
            takeSentText();
            showError(null);
          }
        }
        await poll(true);
        scrollDown();
      } catch (error) {
        // A slow answer isn't always a lost message: look in the chat first, so sending again can't post it twice.
        let arrived = false;
        try {
          await poll(true);
          const words = sentText.trim();
          arrived = Boolean(words) && [...list.querySelectorAll(".chat-msg.is-mine")].some((item) =>
            Number(item.dataset.id) > sentAfter && (item.querySelector(".chat-bubble > p") || {}).textContent === words);
        } catch (checkError) { /* still offline */ }
        if (arrived) {
          takeSentText();
          showError(null);
          scrollDown();
        } else if (error.name === "AbortError") {
          showError("This is taking a while. If it doesn't show up in the chat soon, try again.");
          const words = sentText.trim();
          whenMineArrives = (messages) => {  // it may still get there: then the note and the sent words go
            if (!messages.some((m) => m.mine && m.id > sentAfter && m.body === words)) return;
            whenMineArrives = null;
            takeSentText();
            showError(null);
          };
        } else {
          showError("Couldn't send. Check your connection and try again.");
        }
      } finally {
        sending = false;
        sendButton.disabled = false;
        textarea.focus();
      }
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
