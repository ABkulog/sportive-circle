// Tabs: show one section at a time. Without JavaScript every section just shows, one after another.
// Links like #how-to-join or #requests open the tab that contains them.
(function () {
  document.querySelectorAll("[data-tabs]").forEach((tabs) => {
    const buttons = [...tabs.querySelectorAll("[data-tab-button]")];
    const panels = [...tabs.querySelectorAll("[data-tab-panel]")];

    function show(name, focusPanel) {
      buttons.forEach((button) => {
        const on = button.dataset.tabButton === name;
        button.classList.toggle("is-on", on);
        button.setAttribute("aria-selected", on ? "true" : "false");
        button.tabIndex = on ? 0 : -1;
      });
      panels.forEach((panel) => { panel.hidden = panel.dataset.tabPanel !== name; });
      if (focusPanel) tabs.querySelector(`[data-tab-panel="${name}"]`).focus({ preventScroll: true });
    }

    buttons.forEach((button, index) => {
      const panel = tabs.querySelector(`[data-tab-panel="${button.dataset.tabButton}"]`);
      button.id = `tab-${button.dataset.tabButton}`;
      button.setAttribute("aria-controls", panel.id);
      panel.setAttribute("aria-labelledby", button.id);
      panel.tabIndex = -1;
      button.addEventListener("click", () => show(button.dataset.tabButton));
      button.addEventListener("keydown", (event) => {  // arrow keys move between tabs
        const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
        if (!step) return;
        const next = buttons[(index + step + buttons.length) % buttons.length];
        next.focus();
        show(next.dataset.tabButton);
      });
    });

    // Open the tab that contains the #target in the URL (e.g. after joining, #how-to-join).
    const target = location.hash && document.getElementById(location.hash.slice(1));
    const home = target && target.closest("[data-tab-panel]");
    show(home ? home.dataset.tabPanel : buttons[0].dataset.tabButton);
    if (target) target.scrollIntoView({ block: "center" });
  });
})();
