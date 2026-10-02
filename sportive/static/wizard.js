// Step-by-step forms: one section at a time with a progress bar, like signing up in a phone app.
// "Next" checks the current step first. Without JavaScript, the whole form simply shows.
(function () {
  const form = document.querySelector("form[data-wizard]");
  if (!form) return;
  const steps = [...form.querySelectorAll(".wizard-step")];
  const nav = form.querySelector(".wizard-nav");
  const back = form.querySelector("[data-wizard-back]");
  const next = form.querySelector("[data-wizard-next]");
  const submit = form.querySelector("[data-wizard-submit]");
  const progress = document.createElement("div");
  progress.className = "wizard-progress";
  progress.innerHTML = '<div class="wizard-bar"><span></span></div><p class="wizard-count" aria-live="polite"></p>';
  form.prepend(progress);
  nav.hidden = false;

  let current = 0;

  function show(index) {
    current = index;
    steps.forEach((step, i) => { step.hidden = i !== index; });
    back.hidden = index === 0;  // step 1: no Back, so Next is full width (not stuck on the right)
    next.hidden = index === steps.length - 1;
    submit.hidden = index !== steps.length - 1;
    progress.querySelector("span").style.width = `${((index + 1) / steps.length) * 100}%`;
    const title = steps[index].querySelector(".form-step");
    progress.querySelector(".wizard-count").textContent =
      `Step ${index + 1} of ${steps.length}: ${title ? title.textContent.replace(/^\s*\d+\s*/, "") : ""}`;
  }

  function stepIsValid() {
    // Show the browser's own "please fill this in" message for the first problem in this step.
    for (const field of steps[current].querySelectorAll("input, select, textarea")) {
      if (!field.checkValidity()) { field.reportValidity(); return false; }
    }
    // <fieldset data-need-one="message">: at least one of its boxes has to be filled in (e.g. a social account).
    for (const group of steps[current].querySelectorAll("[data-need-one]")) {
      const boxes = [...group.querySelectorAll("input")];
      if (!boxes.some((box) => box.value.trim())) {
        boxes[0].setCustomValidity(group.dataset.needOne);
        boxes[0].reportValidity();
        boxes.forEach((box) => box.addEventListener("input", () => boxes[0].setCustomValidity(""), { once: true }));
        return false;
      }
    }
    return true;
  }

  // After changing steps, move focus into the new step. Otherwise focus stays on a button that may have
  // just been hidden (Next on the last step), and keyboard / screen reader users are dropped at the top
  // of the page. (The step titles are hidden in wizard mode; the progress line announces the step name.)
  function focusStep() {
    const field = [...steps[current].querySelectorAll("input, select, textarea")]
      .find((el) => el.type !== "hidden" && !el.disabled && el.getClientRects().length);
    const target = field || progress.querySelector(".wizard-count");
    if (!field) target.tabIndex = -1;
    target.focus({ preventScroll: true });
  }

  let lastNext = 0;
  next.addEventListener("click", () => {
    if (Date.now() - lastNext < 400) return;  // a fast double tap moves one step, not two
    lastNext = Date.now();
    if (!stepIsValid()) return;
    show(current + 1);
    focusStep();
    form.scrollIntoView({ block: "start", behavior: "smooth" });
  });
  back.addEventListener("click", () => { show(current - 1); focusStep(); });
  // <form data-must-change>: a sent-back club can't be resent exactly as it was.
  if (form.hasAttribute("data-must-change")) {
    const snapshot = (f) => JSON.stringify([...new FormData(f)].filter(([key]) => key !== "csrf_token"));
    const original = snapshot(form);
    const note = form.querySelector("[data-unchanged-note]");
    form.addEventListener("submit", (event) => {
      if (snapshot(form) !== original) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (note) { note.hidden = false; note.scrollIntoView({ block: "center" }); }
    }, true);
    form.addEventListener("input", () => { if (note) note.hidden = true; });
  }
  form.addEventListener("keydown", (event) => {  // Enter moves to the next step instead of submitting early
    if (event.key === "Enter" && event.target.tagName === "INPUT" && current < steps.length - 1) {
      event.preventDefault();
      next.click();
    }
  });
  // If the server sent the form back with a problem, open the step that has it and put the cursor there.
  const errorField = form.dataset.errorField && form.querySelector(`[name="${form.dataset.errorField}"]`);
  const errorStep = errorField ? steps.findIndex((step) => step.contains(errorField)) : -1;
  show(Math.max(errorStep, 0));
  if (errorField) {
    errorField.setAttribute("aria-invalid", "true");
    const problem = document.querySelector(".flash-error");  // read out with the field, not just once at the top
    if (problem) {
      problem.id = problem.id || "form-problem";
      errorField.setAttribute("aria-describedby",
                              [errorField.getAttribute("aria-describedby"), problem.id].filter(Boolean).join(" "));
    }
    errorField.focus();
  }
})();
