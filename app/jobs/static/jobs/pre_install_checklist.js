// DFHA pre-install checklist — checklist inline saves + room walkthrough AJAX.

(function () {
  const CSRF = document.cookie
    .split("; ")
    .find((r) => r.startsWith("csrftoken="))
    ?.split("=")[1] || "";

  const BASE = window.PI_BASE_URL;
  const CUSTOMER = window.PI_CUSTOMER_LABEL || "this install";
  const ROOM_TYPES = window.ROOM_TYPES || [];
  const CATALOG = window.CATALOG_DEVICES || [];

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

  // ── Checklist: step + sidebar progress ──
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

  const resetBtn = document.querySelector('[data-action="reset"]');
  if (resetBtn) {
    resetBtn.addEventListener("click", async () => {
      const ok = window.confirm(
        `Reset all checklist progress for ${CUSTOMER}?\n\n` +
        `This will uncheck every box, clear every note, and clear every captured value. Cannot be undone.`
      );
      if (!ok) return;
      const r = await post(`${BASE}reset/`, {}, resetBtn);
      if (r && r.ok) window.location.reload();
    });
  }

  // ── Scroll spy ──
  const steps = document.querySelectorAll("section.step");
  const links = new Map();
  document.querySelectorAll(".sidebar-step").forEach((a) => {
    links.set(a.dataset.stepAnchor, a);
  });
  if (steps.length && "IntersectionObserver" in window) {
    const visible = new Set();
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => { e.isIntersecting ? visible.add(e.target.id) : visible.delete(e.target.id); });
        if (!visible.size) return;
        const ordered = [...steps].map((s) => s.id).filter((id) => visible.has(id));
        const top = ordered[0];
        links.forEach((a, key) => a.classList.toggle("active", key === top));
      },
      { rootMargin: "-10% 0px -70% 0px", threshold: 0 }
    );
    steps.forEach((s) => obs.observe(s));
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ── Room walkthrough ──
  // ─────────────────────────────────────────────────────────────────────────

  // Populate room type <select>
  const roomTypeSelect = document.getElementById("room-type-select");
  if (roomTypeSelect) {
    ROOM_TYPES.forEach(({ value, label }) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      roomTypeSelect.appendChild(opt);
    });
  }

  // Populate catalog device <select> in modal
  const rdDeviceSelect = document.getElementById("rd-device-select");
  if (rdDeviceSelect) {
    CATALOG.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d.device_id;
      opt.textContent = d.label;
      rdDeviceSelect.appendChild(opt);
    });
  }

  // Room count badge in sidebar
  function refreshRoomBadge() {
    const badge = document.getElementById("room-count-badge");
    if (!badge) return;
    const count = document.querySelectorAll(".room-card").length;
    badge.textContent = `${count} room${count !== 1 ? "s" : ""}`;
  }

  // Room device summary in step header
  function refreshRoomDeviceSummary() {
    const el = document.getElementById("room-device-summary");
    if (!el) return;
    const total = document.querySelectorAll(".room-device-row").length;
    const confirmed = document.querySelectorAll(".room-device-row.confirmed").length;
    el.textContent = total > 0 ? `${confirmed} / ${total} confirmed` : "";
    el.classList.toggle("complete", total > 0 && confirmed === total);
  }

  // Build a room card DOM node from server data
  function buildRoomCard(roomId, displayLabel) {
    const card = document.createElement("div");
    card.className = "room-card";
    card.dataset.roomId = roomId;
    card.innerHTML = `
      <div class="room-card-header">
        <span class="room-label">${escHtml(displayLabel)}</span>
        <button type="button" class="room-delete-btn" data-room-id="${roomId}" title="Remove room">×</button>
      </div>
      <div class="room-devices" id="room-devices-${roomId}">
        <p class="room-empty-msg">No devices added yet.</p>
      </div>
      <button type="button" class="add-rd-btn" data-room-id="${roomId}">+ Add device</button>
    `;
    return card;
  }

  // Add room button
  const addRoomBtn = document.getElementById("add-room-btn");
  if (addRoomBtn) {
    addRoomBtn.addEventListener("click", async () => {
      const roomType = roomTypeSelect.value;
      if (!roomType) { roomTypeSelect.focus(); return; }
      const customName = (document.getElementById("room-custom-name")?.value || "").trim();

      addRoomBtn.disabled = true;
      addRoomBtn.textContent = "Adding…";

      const r = await fetch(`${BASE}rooms/add/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify({ room_type: roomType, custom_name: customName }),
        credentials: "same-origin",
      });

      addRoomBtn.disabled = false;
      addRoomBtn.textContent = "+ Add room";

      if (!r.ok) return;
      const data = await r.json();

      // Remove "no rooms" message if present
      const noRoomsMsg = document.getElementById("no-rooms-msg");
      if (noRoomsMsg) noRoomsMsg.remove();

      const roomList = document.getElementById("room-list");
      const card = buildRoomCard(data.id, data.display_label);
      roomList.appendChild(card);

      // Reset inputs
      roomTypeSelect.value = "";
      if (document.getElementById("room-custom-name")) {
        document.getElementById("room-custom-name").value = "";
      }

      refreshRoomBadge();
    });
  }

  // Delete room (delegated on room-list)
  const roomList = document.getElementById("room-list");
  if (roomList) {
    roomList.addEventListener("click", async (e) => {
      const delBtn = e.target.closest(".room-delete-btn");
      if (!delBtn) return;
      const roomId = delBtn.dataset.roomId;
      if (!window.confirm("Remove this room and all its devices?")) return;
      const r = await fetch(`${BASE}rooms/${roomId}/delete/`, {
        method: "POST",
        headers: { "X-CSRFToken": CSRF },
        credentials: "same-origin",
      });
      if (r && r.ok) {
        delBtn.closest(".room-card")?.remove();
        refreshRoomBadge();
        refreshRoomDeviceSummary();
      }
    });
  }

  // ── Room device modal ──
  const rdModal = document.getElementById("rd-modal");
  let activeRoomId = null;

  function openRdModal(roomId) {
    activeRoomId = roomId;
    rdDeviceSelect.value = "";
    document.getElementById("rd-qty").value = 1;
    rdModal.hidden = false;
    rdDeviceSelect.focus();
  }

  function closeRdModal() {
    rdModal.hidden = true;
    activeRoomId = null;
  }

  document.getElementById("rd-cancel-btn")?.addEventListener("click", closeRdModal);
  rdModal?.addEventListener("click", (e) => { if (e.target === rdModal) closeRdModal(); });

  // "Add device" button on each room card (delegated)
  if (roomList) {
    roomList.addEventListener("click", (e) => {
      const btn = e.target.closest(".add-rd-btn");
      if (btn) openRdModal(btn.dataset.roomId);
    });
  }

  // Confirm adding device to room
  document.getElementById("rd-confirm-btn")?.addEventListener("click", async () => {
    const deviceId = parseInt(rdDeviceSelect.value, 10);
    if (!deviceId) { rdDeviceSelect.focus(); return; }
    const qty = Math.max(1, parseInt(document.getElementById("rd-qty").value, 10) || 1);
    const roomId = activeRoomId;

    const r = await fetch(`${BASE}rooms/${roomId}/devices/add/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
      body: JSON.stringify({ device_id: deviceId, quantity: qty }),
      credentials: "same-origin",
    });

    if (!r.ok) { closeRdModal(); return; }
    const data = await r.json();
    closeRdModal();

    const devicesContainer = document.getElementById(`room-devices-${roomId}`);
    if (devicesContainer) {
      // Remove "no devices" placeholder
      devicesContainer.querySelectorAll(".room-empty-msg").forEach((el) => el.remove());

      const row = document.createElement("div");
      row.className = "room-device-row";
      row.dataset.rdId = data.id;
      row.innerHTML = `
        <label class="rd-confirm-label">
          <input type="checkbox" class="rd-confirm" data-room-id="${roomId}" data-rd-id="${data.id}">
          <span class="rd-label">${data.quantity}× ${escHtml(data.device_label)}</span>
        </label>
        <button type="button" class="rd-delete-btn" data-room-id="${roomId}" data-rd-id="${data.id}" title="Remove">×</button>
      `;
      devicesContainer.appendChild(row);
    }
    refreshRoomDeviceSummary();
  });

  // Confirm/unconfirm a room device (delegated)
  if (roomList) {
    roomList.addEventListener("change", async (e) => {
      const cb = e.target.closest(".rd-confirm");
      if (!cb) return;
      const roomId = cb.dataset.roomId;
      const rdId = cb.dataset.rdId;
      const r = await fetch(`${BASE}rooms/${roomId}/devices/${rdId}/confirm/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify({ confirmed: cb.checked }),
        credentials: "same-origin",
      });
      if (r && r.ok) {
        cb.closest(".room-device-row")?.classList.toggle("confirmed", cb.checked);
        refreshRoomDeviceSummary();
      }
    });

    // Delete a room device (delegated)
    roomList.addEventListener("click", async (e) => {
      const btn = e.target.closest(".rd-delete-btn");
      if (!btn) return;
      const roomId = btn.dataset.roomId;
      const rdId = btn.dataset.rdId;
      const r = await fetch(`${BASE}rooms/${roomId}/devices/${rdId}/delete/`, {
        method: "POST",
        headers: { "X-CSRFToken": CSRF },
        credentials: "same-origin",
      });
      if (r && r.ok) {
        btn.closest(".room-device-row")?.remove();
        // If no devices left, show empty message
        const devicesContainer = document.getElementById(`room-devices-${roomId}`);
        if (devicesContainer && !devicesContainer.querySelector(".room-device-row")) {
          const p = document.createElement("p");
          p.className = "room-empty-msg";
          p.textContent = "No devices added yet.";
          devicesContainer.appendChild(p);
        }
        refreshRoomDeviceSummary();
      }
    });
  }

  function escHtml(s) {
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  refreshRoomBadge();
  refreshRoomDeviceSummary();
})();
