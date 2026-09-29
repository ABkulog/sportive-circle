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
    back.style.visibility = index === 0 ? "hidden" : "visible";
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

  next.addEventListener("click", () => {
    if (!stepIsValid()) return;
    show(current + 1);
    form.scrollIntoView({ block: "start", behavior: "smooth" });
  });
  back.addEventListener("click", () => show(current - 1));
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
    errorField.focus();
  }
})();
