// Inline-save helper for the backend-install render view.
// Checkbox toggles save on change; notes + captures save on blur.

(function () {
  const CSRF = document.cookie
    .split("; ")
    .find((r) => r.startsWith("csrftoken="))
    ?.split("=")[1] || "";

  const BASE = window.BI_BASE_URL;

  async function post(url, body, target) {
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify(body),
        credentials: "same-origin",
      });
      flash(target, r.ok);
      return r;
    } catch {
      flash(target, false);
    }
  }

  function flash(el, ok) {
    if (!el) return;
    const cls = ok ? "save-ok" : "save-err";
    el.classList.remove("save-ok", "save-err");
    el.classList.add(cls);
    setTimeout(() => el.classList.remove(cls), 1200);
  }

  function refreshStepProgress(stepEl) {
    const boxes = stepEl.querySelectorAll('input[type="checkbox"][data-action="toggle-check"]');
    if (!boxes.length) return;
    const done = [...boxes].filter((b) => b.checked).length;
    const badge = stepEl.querySelector(".step-progress");
    if (badge) {
      badge.textContent = `${done} / ${boxes.length}`;
      badge.classList.toggle("complete", done === boxes.length);
    }
  }

  document.querySelectorAll('input[type="checkbox"][data-action="toggle-check"]').forEach((el) => {
    el.addEventListener("change", async () => {
      const itemId = el.dataset.itemId;
      const wrap = el.closest(".check-item");
      await post(`${BASE}item/${itemId}/check/`, { checked: el.checked }, wrap);
      refreshStepProgress(el.closest(".step"));
    });
  });

  document.querySelectorAll('textarea[data-action="save-notes"]').forEach((el) => {
    let original = el.value;
    el.addEventListener("blur", async () => {
      if (el.value === original) return;
      const itemId = el.dataset.itemId;
      const r = await post(`${BASE}item/${itemId}/notes/`, { notes: el.value }, el);
      if (r && r.ok) original = el.value;
    });
  });

  document.querySelectorAll('input[data-action="save-capture"]').forEach((el) => {
    let original = el.value;
    el.addEventListener("blur", async () => {
      if (el.value === original) return;
      const key = el.dataset.captureKey;
      const r = await post(`${BASE}capture/${key}/`, { value: el.value }, el);
      if (r && r.ok) original = el.value;
    });
  });
})();
