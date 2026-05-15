// DFHA on-site install page — inline saves + complete / reopen.

(function () {
  const CSRF = document.cookie
    .split("; ")
    .find((r) => r.startsWith("csrftoken="))
    ?.split("=")[1] || "";

  const URLS = window.OI_URLS;
  const FLAG_TOTAL = window.OI_FLAG_TOTAL;

  async function post(url, body, target) {
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify(body || {}),
        credentials: "same-origin",
      });
      flash(target, r.ok);
      if (!r.ok) return null;
      try { return await r.json(); } catch { return {}; }
    } catch {
      flash(target, false);
      return null;
    }
  }

  function flash(el, ok) {
    if (el) {
      const cls = ok ? "save-ok" : "save-err";
      el.classList.remove("save-ok", "save-err");
      el.classList.add(cls);
      setTimeout(() => el.classList.remove(cls), 1200);
    }
    const toast = document.getElementById("save-toast");
    if (!toast) return;
    toast.textContent = ok ? "Saved" : "Error saving";
    toast.classList.toggle("error", !ok);
    toast.classList.add("visible");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toast.classList.remove("visible"), 1500);
  }

  function paintConfirmedState() {
    document.querySelectorAll(".confirm-check").forEach((cb) => {
      const card = cb.closest(".card");
      if (card) card.classList.toggle("confirmed", cb.checked);
    });
  }

  function updateFlagCount() {
    const done = document.querySelectorAll(".confirm-check:checked").length;
    const el = document.getElementById("flag-done");
    if (el) el.textContent = done;
    const btn = document.getElementById("complete-btn");
    if (btn) btn.disabled = done < FLAG_TOTAL;
    const pending = document.querySelector(".complete-pending");
    if (pending) {
      const remaining = FLAG_TOTAL - done;
      if (remaining > 0) {
        pending.textContent = `${remaining} more confirmation${remaining === 1 ? "" : "s"} needed before this can be marked complete.`;
        pending.style.display = "";
      } else {
        pending.style.display = "none";
      }
    }
  }

  paintConfirmedState();

  // ── Confirmation checkboxes ──
  document.querySelectorAll(".confirm-check").forEach((cb) => {
    cb.addEventListener("change", async () => {
      const r = await post(URLS.save, { field: cb.dataset.field, value: cb.checked }, cb.closest(".card"));
      if (!r) { cb.checked = !cb.checked; return; }
      paintConfirmedState();
      updateFlagCount();
    });
  });

  // ── Text / textarea autosave on blur ──
  document.querySelectorAll("[data-field]:not(.confirm-check):not(.card)").forEach((el) => {
    if (!(el.tagName === "INPUT" || el.tagName === "TEXTAREA")) return;
    let orig = el.value;
    el.addEventListener("blur", async () => {
      if (el.value === orig) return;
      const r = await post(URLS.save, { field: el.dataset.field, value: el.value }, el);
      if (r) orig = el.value;
    });
  });

  // ── Mark complete ──
  const completeBtn = document.getElementById("complete-btn");
  if (completeBtn) {
    completeBtn.addEventListener("click", async () => {
      if (!confirm("Mark on-site install complete and advance the job to the walkthrough stage?")) return;
      const r = await post(URLS.complete, {}, completeBtn);
      if (r) location.reload();
    });
  }

  // ── Reopen ──
  const reopenBtn = document.getElementById("reopen-btn");
  if (reopenBtn) {
    reopenBtn.addEventListener("click", async () => {
      if (!confirm("Reopen the on-site install to record more work?")) return;
      const r = await post(URLS.reopen, {}, reopenBtn);
      if (r) location.reload();
    });
  }
})();
