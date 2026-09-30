// Chat: checks for new messages every few seconds and adds them without reloading.
// Messages are added with textContent (never innerHTML), so nobody can inject code.
(function () {
  const box = document.querySelector(".chat[data-poll-url]");
  if (!box) return;
  const list = document.getElementById("chat-messages");
  const empty = document.getElementById("chat-empty");
  let lastId = parseInt(box.dataset.lastId, 10) || 0;

  const scrollDown = () => { list.scrollTop = list.scrollHeight; };
  scrollDown();

  function render(message) {
    const item = document.createElement("li");
    item.className = "chat-msg" + (message.mine ? " is-mine" : "");
    if (!message.mine) {
      const avatar = document.createElement("a");
      avatar.className = "chat-avatar";
      avatar.href = message.profile;
      avatar.tabIndex = -1;
      avatar.setAttribute("aria-label", message.name ? `${message.name}'s profile` : "Profile");
      if (message.avatar) {
        const image = document.createElement("img");
        image.src = message.avatar;
        image.alt = "";
        avatar.appendChild(image);
      } else {
        const initial = document.createElement("span");
        initial.textContent = message.initial;
        avatar.appendChild(initial);
      }
      item.appendChild(avatar);
    }
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    if (!message.mine) {
      const name = document.createElement("span");
      name.className = "chat-name";
      name.textContent = message.name;
      bubble.appendChild(name);
    }
    const text = document.createElement("p");
    text.textContent = message.body;
    const time = document.createElement("time");
    time.textContent = message.time;
    bubble.appendChild(text);
    if (message.game) {
      const game = document.createElement("a");
      game.className = "chat-game" + (message.game.cancelled ? " is-cancelled" : "");
      game.href = message.game.url;
      const emoji = document.createElement("span");
      emoji.className = "chat-game-emoji";
      emoji.setAttribute("aria-hidden", "true");
      emoji.textContent = message.game.emoji;
      const info = document.createElement("span");
      const title = document.createElement("strong");
      title.textContent = message.game.title;
      const meta = document.createElement("small");
      meta.textContent = `${message.game.cancelled ? "Canceled" : message.game.when} · ${message.game.where}`;
      info.append(title, " ", meta);
      game.append(emoji, info);
      bubble.appendChild(game);
    }
    bubble.appendChild(time);
    if (message.report) {
      const report = document.createElement("a");
      report.className = "chat-report";
      report.href = message.report;
      report.textContent = "🚩 Report";
      bubble.appendChild(report);
    }
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
      const nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
      messages.forEach(render);
      lastId = messages[messages.length - 1].id;
      if (empty) empty.hidden = true;
      box.classList.remove("is-empty");
      if (nearBottom) scrollDown();
    } catch (error) { /* offline for a moment; try again next time */ }
  }
  setInterval(poll, 5000);

  // Enter sends, Shift+Enter makes a new line; the box grows as you type.
  const textarea = box.querySelector("textarea");
  if (textarea) {
    textarea.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && textarea.value.trim()) {
        event.preventDefault();
        if (textarea.form.requestSubmit) textarea.form.requestSubmit();  // Safari 16+
        else if (textarea.form.dispatchEvent(new Event("submit", { cancelable: true }))) textarea.form.submit();
      }
    });
    textarea.addEventListener("input", () => {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
    });
  }
})();
