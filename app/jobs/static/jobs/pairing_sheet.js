// DFHA pairing sheet — inline saves + clipboard copy + lock/unlock.

(function () {
  const CSRF = document.cookie
    .split("; ")
    .find((r) => r.startsWith("csrftoken="))
    ?.split("=")[1] || "";

  const URLS = window.PS_URLS;

  async function post(url, body, target) {
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: body ? JSON.stringify(body) : "{}",
        credentials: "same-origin",
      });
      const ok = r.ok;
      flash(target, ok);
      if (!ok) return null;
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
    showToast(ok);
  }

  function showToast(ok) {
    const toast = document.getElementById("save-toast");
    if (!toast) return;
    toast.textContent = ok ? "Saved" : "Error saving";
    toast.classList.toggle("error", !ok);
    toast.classList.add("visible");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toast.classList.remove("visible"), 1500);
  }

  function updatePairedCount() {
    const total = window.PS_TOTAL;
    const done = document.querySelectorAll(".pair-row.paired").length;
    const el = document.getElementById("paired-count");
    if (el) el.textContent = done;
    const lockBtn = document.getElementById("lock-btn");
    if (lockBtn) lockBtn.disabled = done < total;
  }

  // ── Paired checkbox ──
  document.querySelectorAll(".paired-check").forEach((el) => {
    el.addEventListener("change", async () => {
      const row = el.closest(".pair-row");
      const psdId = row.dataset.psdId;
      const r = await post(URLS.paired(psdId), { paired: el.checked }, row);
      if (r) {
        row.classList.toggle("paired", el.checked);
        // Surface or update timestamp.
        let stamp = row.querySelector(".paired-when");
        if (el.checked && r.paired_at) {
          if (!stamp) {
            stamp = document.createElement("div");
            stamp.className = "paired-when";
            row.querySelector(".col-check").appendChild(stamp);
          }
          stamp.textContent = new Date(r.paired_at).toLocaleString();
        } else if (!el.checked && stamp) {
          stamp.remove();
        }
        updatePairedCount();
      } else {
        el.checked = !el.checked;
      }
    });
  });

  // ── HA name input ──
  document.querySelectorAll(".ha-name-input").forEach((el) => {
    let orig = el.value;
    el.addEventListener("blur", async () => {
      if (el.value === orig) return;
      const row = el.closest(".pair-row");
      const r = await post(URLS.name(row.dataset.psdId), { ha_name: el.value }, el);
      if (r) {
        el.value = r.ha_name;
        orig = el.value;
      }
    });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); el.blur(); }
    });
  });

  // ── Notes input ──
  document.querySelectorAll(".notes-input").forEach((el) => {
    let orig = el.value;
    el.addEventListener("blur", async () => {
      if (el.value === orig) return;
      const row = el.closest(".pair-row");
      const r = await post(URLS.notes(row.dataset.psdId), { notes: el.value }, el);
      if (r) orig = el.value;
    });
  });

  // ── Regenerate name ──
  document.querySelectorAll(".regen-btn").forEach((el) => {
    el.addEventListener("click", async () => {
      const row = el.closest(".pair-row");
      const r = await post(URLS.regenerate(row.dataset.psdId), {}, row);
      if (r) {
        const input = row.querySelector(".ha-name-input");
        input.value = r.ha_name;
      }
    });
  });

  // ── Copy to clipboard ──
  document.querySelectorAll(".copy-btn").forEach((el) => {
    el.addEventListener("click", async () => {
      const row = el.closest(".pair-row");
      const name = row.querySelector(".ha-name-input").value;
      if (!name) return;
      try {
        await navigator.clipboard.writeText(name);
        el.classList.add("copied");
        setTimeout(() => el.classList.remove("copied"), 900);
      } catch {
        // Fallback: select+execCommand is deprecated; just flash error.
        flash(row, false);
      }
    });
  });

  // ── Lock / unlock ──
  const lockBtn = document.getElementById("lock-btn");
  if (lockBtn) {
    lockBtn.addEventListener("click", async () => {
      if (!confirm("Lock the pairing sheet? Unlocking after the walkthrough is audit-logged.")) return;
      const r = await post(URLS.lock, {}, lockBtn);
      if (r) location.reload();
    });
  }
  const unlockBtn = document.getElementById("unlock-btn");
  if (unlockBtn) {
    unlockBtn.addEventListener("click", async () => {
      if (!confirm("Unlock the pairing sheet?")) return;
      const r = await post(URLS.unlock, {}, unlockBtn);
      if (r) location.reload();
    });
  }
})();
