// Inline-save helper + sidebar navigation for the backend-install
// render view. Checkboxes commit on change; notes + captures commit on
// blur. Sidebar highlights the currently-visible step and mirrors
// each step's progress badge.

(function () {
  const CSRF = document.cookie
    .split("; ")
    .find((r) => r.startsWith("csrftoken="))
    ?.split("=")[1] || "";

  const BASE = window.BI_BASE_URL;
  const CUSTOMER = window.BI_CUSTOMER_LABEL || "this install";

  async function post(url, body, target) {
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: body === undefined ? "{}" : JSON.stringify(body),
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

  // ── Step + sidebar progress ──
  function refreshStepProgress(stepEl) {
    const boxes = stepEl.querySelectorAll('input[type="checkbox"][data-action="toggle-check"]');
    if (!boxes.length) return;
    const done = [...boxes].filter((b) => b.checked).length;
    const total = boxes.length;

    const stepBadge = stepEl.querySelector(".step-progress");
    if (stepBadge) {
      stepBadge.textContent = `${done} / ${total}`;
      stepBadge.classList.toggle("complete", done === total);
    }

    const id = stepEl.id;
    const sidebarLink = document.querySelector(`.sidebar-step[data-step-anchor="${id}"]`);
    if (sidebarLink) {
      const sidebarBadge = sidebarLink.querySelector(".sidebar-step-progress");
      if (sidebarBadge) {
        sidebarBadge.textContent = `${done}/${total}`;
        sidebarBadge.classList.toggle("complete", done === total);
      }
    }

    refreshOverallProgress();
  }

  function refreshOverallProgress() {
    const boxes = document.querySelectorAll('input[type="checkbox"][data-action="toggle-check"]');
    const done = [...boxes].filter((b) => b.checked).length;
    const total = boxes.length;
    const frac = document.querySelector(".sidebar-progress-fraction");
    if (frac) frac.textContent = `${done} / ${total}`;
    const fill = document.querySelector(".progress-bar-fill");
    if (fill) fill.style.width = total ? `${(done / total) * 100}%` : "0%";
  }

  // ── Inline saves ──
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

  // ── Reset ──
  const resetBtn = document.querySelector('[data-action="reset"]');
  if (resetBtn) {
    resetBtn.addEventListener("click", async () => {
      const ok = window.confirm(
        `Reset all progress for ${CUSTOMER}'s backend install?\n\n` +
        `This will uncheck every box, clear every note, and clear every ` +
        `captured value (including the auto-filled hostname and temp ` +
        `password). Cannot be undone.`
      );
      if (!ok) return;
      const r = await post(`${BASE}reset/`, {}, resetBtn);
      if (r && r.ok) window.location.reload();
    });
  }

  // ── Scroll spy: highlight the step closest to the top of the viewport ──
  const steps = document.querySelectorAll("section.step");
  const links = new Map();
  document.querySelectorAll(".sidebar-step").forEach((a) => {
    links.set(a.dataset.stepAnchor, a);
  });

  if (steps.length && "IntersectionObserver" in window) {
    const visible = new Set();
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) visible.add(e.target.id);
          else visible.delete(e.target.id);
        });
        if (!visible.size) return;
        // pick the topmost visible step
        const ordered = [...steps].map((s) => s.id).filter((id) => visible.has(id));
        const top = ordered[0];
        links.forEach((a, key) => a.classList.toggle("active", key === top));
      },
      { rootMargin: "-10% 0px -70% 0px", threshold: 0 }
    );
    steps.forEach((s) => obs.observe(s));
  }
})();
