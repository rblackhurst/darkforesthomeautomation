// DFHA sales form — package selection, à-la-carte device table, form serialization.

(function () {
  const packages = window.PACKAGES_DATA || [];
  const catalog  = window.CATALOG_DATA  || {};

  const packageSelect   = document.getElementById("package-select");
  const packagePreview  = document.getElementById("package-preview");
  const pkgPreviewName  = document.getElementById("package-preview-name");
  const pkgPreviewDesc  = document.getElementById("package-preview-desc");
  const tbody           = document.getElementById("device-tbody");
  const emptyRow        = document.getElementById("device-empty-row");
  const totalRow        = document.getElementById("device-total-row");
  const totalCell       = document.getElementById("device-total");
  const addDeviceBtn    = document.getElementById("add-device-btn");
  const addPanel        = document.getElementById("add-device-panel");
  const newDeviceSelect = document.getElementById("new-device-select");
  const newDeviceQty    = document.getElementById("new-device-qty");
  const newDeviceNotes  = document.getElementById("new-device-notes");
  const addConfirmBtn   = document.getElementById("add-device-confirm");
  const addCancelBtn    = document.getElementById("add-device-cancel");
  const packageIdInput  = document.getElementById("id_package_id");
  const devicesJsonInput = document.getElementById("id_devices_json");

  // ── Build a flat device lookup {id: {label, unit_cost}} ──
  const deviceLookup = {};
  Object.values(catalog).forEach((devices) => {
    devices.forEach((d) => { deviceLookup[d.device_id] = d; });
  });

  // ── Populate package dropdown ──
  packages.forEach((pkg) => {
    const opt = document.createElement("option");
    opt.value = pkg.id;
    opt.textContent = pkg.name + (pkg.base_price ? ` — $${pkg.base_price}` : "");
    packageSelect.appendChild(opt);
  });

  // ── Populate device dropdown (grouped by type) ──
  Object.entries(catalog).forEach(([typeName, devices]) => {
    const group = document.createElement("optgroup");
    group.label = typeName;
    devices.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d.device_id;
      opt.textContent = d.label + (d.unit_cost ? ` ($${d.unit_cost})` : "");
      group.appendChild(opt);
    });
    newDeviceSelect.appendChild(group);
  });

  // ── Device line tracking ──
  const lines = []; // [{device_id, quantity, notes, _fromPackage}]

  function refreshTable() {
    // Remove dynamic rows
    tbody.querySelectorAll("tr.device-line").forEach((r) => r.remove());

    const hasLines = lines.length > 0;
    emptyRow.hidden = hasLines;

    let total = 0;
    let totalKnown = true;

    lines.forEach((line, idx) => {
      const d = deviceLookup[line.device_id] || {};
      const cost = d.unit_cost ? parseFloat(d.unit_cost) : null;
      const lineTotal = cost !== null ? cost * line.quantity : null;

      if (cost === null) totalKnown = false;
      else total += lineTotal;

      const tr = document.createElement("tr");
      tr.className = "device-line";
      tr.innerHTML = `
        <td>${d.label || "Unknown device"}</td>
        <td class="col-qty">${line.quantity}</td>
        <td class="col-cost">${cost !== null ? "$" + cost.toFixed(2) : "—"}</td>
        <td class="col-notes">${escHtml(line.notes || "")}</td>
        <td class="col-del"><button type="button" class="del-line-btn" data-idx="${idx}" title="Remove">×</button></td>
      `;
      tbody.insertBefore(tr, emptyRow);
    });

    // Total row
    totalRow.hidden = !hasLines;
    if (hasLines) {
      totalCell.textContent = totalKnown ? "$" + total.toFixed(2) : "—";
    }

    // Sync hidden inputs
    if (packageIdInput) packageIdInput.value = packageSelect.value || "";
    if (devicesJsonInput) devicesJsonInput.value = JSON.stringify(
      lines.map(({ device_id, quantity, notes }) => ({ device_id, quantity, notes }))
    );
  }

  function escHtml(s) {
    return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  // ── Remove line button (delegated) ──
  tbody.addEventListener("click", (e) => {
    const btn = e.target.closest(".del-line-btn");
    if (!btn) return;
    const idx = parseInt(btn.dataset.idx, 10);
    lines.splice(idx, 1);
    refreshTable();
  });

  // ── Package selection ──
  packageSelect.addEventListener("change", () => {
    const pkgId = parseInt(packageSelect.value, 10);
    const pkg = packages.find((p) => p.id === pkgId);

    // Remove any previously package-sourced lines
    for (let i = lines.length - 1; i >= 0; i--) {
      if (lines[i]._fromPackage) lines.splice(i, 1);
    }

    if (pkg) {
      pkg.devices.forEach((pd) => {
        lines.unshift({
          device_id: pd.device_id,
          quantity: pd.quantity,
          notes: "",
          _fromPackage: true,
        });
      });
      packagePreview.hidden = false;
      pkgPreviewName.textContent = pkg.name;
      pkgPreviewDesc.textContent = pkg.description || "";
    } else {
      packagePreview.hidden = true;
    }

    refreshTable();
  });

  // ── Add device panel ──
  addDeviceBtn.addEventListener("click", () => {
    addPanel.hidden = false;
    addDeviceBtn.hidden = true;
    newDeviceSelect.value = "";
    newDeviceQty.value = 1;
    newDeviceNotes.value = "";
    newDeviceSelect.focus();
  });

  addCancelBtn.addEventListener("click", () => {
    addPanel.hidden = true;
    addDeviceBtn.hidden = false;
  });

  addConfirmBtn.addEventListener("click", () => {
    const deviceId = parseInt(newDeviceSelect.value, 10);
    if (!deviceId) { newDeviceSelect.focus(); return; }
    const quantity = Math.max(1, parseInt(newDeviceQty.value, 10) || 1);
    const notes = newDeviceNotes.value.trim();
    lines.push({ device_id: deviceId, quantity, notes, _fromPackage: false });
    addPanel.hidden = true;
    addDeviceBtn.hidden = false;
    refreshTable();
  });

  // Allow Enter in the panel to confirm
  addPanel.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); addConfirmBtn.click(); }
    if (e.key === "Escape") addCancelBtn.click();
  });

  // ── Form submission guard ──
  const form = document.querySelector("form");
  if (form) {
    form.addEventListener("submit", () => {
      refreshTable(); // ensure hidden fields are up to date
      const btn = form.querySelector(".submit-btn");
      if (btn) { btn.disabled = true; btn.textContent = "Creating…"; }
    });
  }

  refreshTable();
})();
