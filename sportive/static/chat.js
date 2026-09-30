// Chat: checks for new messages every few seconds and adds them without reloading.
// Messages are added with textContent (never innerHTML), so nobody can inject code.
(function () {
  const box = document.querySelector(".chat[data-poll-url]");
  if (!box) return;
  const list = document.getElementById("chat-messages");
  const empty = document.getElementById("chat-empty");
  let lastId = parseInt(box.dataset.lastId, 10) || 0;

  // Phones: the chat fills the screen below the header, and shrinks when the keyboard opens.
  const fit = () => {
    if (window.innerWidth > 700) { box.style.height = ""; return; }
    const visible = window.visualViewport ? window.visualViewport.height : window.innerHeight;
    const top = box.getBoundingClientRect().top + window.scrollY;
    box.style.height = Math.max(320, visible - top + window.scrollY - 8) + "px";
  };
  fit();
  window.addEventListener("resize", fit);
  if (window.visualViewport) window.visualViewport.addEventListener("resize", () => { fit(); scrollDown(); });
  const scrollDown = () => { list.scrollTop = list.scrollHeight; };
  const nearBottom = () => list.scrollHeight - list.scrollTop - list.clientHeight < 200;
  scrollDown();
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
    item.dataset.sender = message.sender;
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

  async function poll() {
    if (document.hidden) return;
    try {
      const response = await fetch(`${box.dataset.pollUrl}?after=${lastId}`, { headers: { Accept: "application/json" } });
      if (new URL(response.url).pathname.startsWith("/login")) { location.reload(); return; }  // logged out
      if (!response.ok) return;
      const { messages } = await response.json();
      if (!messages.length) return;
      const wasNearBottom = nearBottom();
      messages.forEach(render);
      lastId = messages[messages.length - 1].id;
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
  const hasPhoto = () => photoInput && photoInput.files && photoInput.files.length > 0;
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
    // Nothing to send (no words, no photo): don't send an empty message.
    textarea.form.addEventListener("submit", (event) => {
      if (!textarea.value.trim() && !hasPhoto()) { event.preventDefault(); textarea.focus(); }
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
  // A picked photo shows above the box until it's sent or removed.
  if (photoInput && attached) {
    let previewUrl = null;
    const clear = () => {
      photoInput.value = "";
      attached.hidden = true;
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    };
    photoInput.addEventListener("change", () => {
      if (!hasPhoto()) { clear(); return; }
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(photoInput.files[0]);
      attached.querySelector("[data-chat-preview]").src = previewUrl;
      attached.hidden = false;
      if (textarea) textarea.focus();
    });
    attached.querySelector("[data-chat-unattach]").addEventListener("click", clear);
  }
})();
