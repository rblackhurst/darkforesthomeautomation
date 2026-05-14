// DFHA internal prep page — inline saves for all interactive elements.

(function () {
  const CSRF = document.cookie
    .split("; ")
    .find((r) => r.startsWith("csrftoken="))
    ?.split("=")[1] || "";

  const BASE = window.IP_BASE_URL;

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
    showToast(ok);
  }

  function showToast(ok) {
    const toast = document.getElementById("save-toast");
    if (!toast) return;
    toast.textContent = ok ? "Saved" : "Error saving";
    toast.classList.add("visible");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toast.classList.remove("visible"), 1500);
  }

  // ── Stock confirmation checkboxes ──
  document.querySelectorAll(".stock-check").forEach((el) => {
    el.addEventListener("change", async () => {
      const slId = el.dataset.slId;
      const row = el.closest(".device-row");
      const r = await post(`${BASE}devices/${slId}/confirm/`, { confirmed: el.checked }, row);
      if (r && r.ok) row.classList.toggle("confirmed", el.checked);
    });
  });

  // ── Toggle fields (github_created, picklist_picked) ──
  document.querySelectorAll(".toggle-check").forEach((el) => {
    el.addEventListener("change", async () => {
      const field = el.id === "github-created" ? "github_created" : "picklist_picked";
      await post(`${BASE}save/`, { field, value: el.checked }, el.closest("section"));
    });
  });

  // ── GitHub username ──
  const ghInput = document.getElementById("github-username");
  if (ghInput) {
    let orig = ghInput.value;
    ghInput.addEventListener("blur", async () => {
      if (ghInput.value === orig) return;
      const r = await post(`${BASE}save/`, { field: "github_username", value: ghInput.value }, ghInput);
      if (r && r.ok) orig = ghInput.value;
    });
  }

  // ── Internal notes ──
  const notesEl = document.getElementById("internal-notes");
  if (notesEl) {
    let orig = notesEl.value;
    notesEl.addEventListener("blur", async () => {
      if (notesEl.value === orig) return;
      const r = await post(`${BASE}save/`, { field: "notes", value: notesEl.value }, notesEl);
      if (r && r.ok) orig = notesEl.value;
    });
  }
})();
