'use strict';

const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: JSON.stringify(body),
  }).then(r => r.json());
}

function showToast() {
  const t = document.getElementById('save-toast');
  t.classList.add('visible');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('visible'), 1800);
}

function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

// ── Restore standard checklist state from server ──────────────────────────────
const state = window.OI_STANDARD_STATE || {};
document.querySelectorAll('.standard-check').forEach(cb => {
  const key = cb.dataset.key;
  if (state[key]) cb.checked = true;
});

// ── Standard checklist toggles ────────────────────────────────────────────────
document.querySelectorAll('.standard-check').forEach(cb => {
  cb.addEventListener('change', () => {
    post(window.OI_URLS.toggleStandard, { key: cb.dataset.key, checked: cb.checked })
      .then(() => showToast());
  });
});

// ── Device installed/tested toggles ──────────────────────────────────────────
document.querySelectorAll('.device-row').forEach(row => {
  const checkId = row.dataset.checkId;

  row.querySelector('.installed-check')?.addEventListener('change', function () {
    post(window.OI_URLS.toggleInstalled(checkId), {}).then(data => {
      if (data.ok) { updateRowDone(row); showToast(); }
    });
  });

  row.querySelector('.tested-check')?.addEventListener('change', function () {
    post(window.OI_URLS.toggleTested(checkId), {}).then(data => {
      if (data.ok) { updateRowDone(row); showToast(); }
    });
  });
});

function updateRowDone(row) {
  const installed = row.querySelector('.installed-check')?.checked;
  const tested = row.querySelector('.tested-check')?.checked;
  row.classList.toggle('done', !!(installed && tested));
}

// ── IP address saves ──────────────────────────────────────────────────────────
document.querySelectorAll('.ip-input').forEach(input => {
  const checkId = input.dataset.checkId;
  const save = debounce(() => {
    post(window.OI_URLS.saveIp(checkId), { value: input.value.trim() }).then(() => showToast());
  }, 600);
  input.addEventListener('input', save);
});

// ── Device notes saves ────────────────────────────────────────────────────────
document.querySelectorAll('.device-notes-input').forEach(input => {
  const row = input.closest('.device-row');
  const checkId = row?.dataset.checkId;
  if (!checkId) return;
  const save = debounce(() => {
    post(window.OI_URLS.saveNotes(checkId), { value: input.value }).then(() => showToast());
  }, 600);
  input.addEventListener('input', save);
});

// ── LAN subnet + textarea fields ──────────────────────────────────────────────
const subnetInput = document.getElementById('lan-subnet');
if (subnetInput) {
  subnetInput.addEventListener('input', debounce(() => {
    post(window.OI_URLS.saveField, { field: 'lan_subnet', value: subnetInput.value.trim() })
      .then(() => showToast());
  }, 600));
}

document.querySelectorAll('.notes-textarea').forEach(ta => {
  const field = ta.dataset.field;
  if (!field) return;
  ta.addEventListener('input', debounce(() => {
    post(window.OI_URLS.saveField, { field, value: ta.value }).then(() => showToast());
  }, 600));
});

// ── Mark complete ─────────────────────────────────────────────────────────────
const completeBtn = document.getElementById('complete-btn');
if (completeBtn) {
  completeBtn.addEventListener('click', () => {
    completeBtn.disabled = true;
    completeBtn.textContent = 'Saving…';
    post(window.OI_URLS.complete, {}).then(data => {
      if (data.ok) {
        window.location.href = window.OI_URLS.walkthroughUrl;
      } else {
        completeBtn.disabled = false;
        completeBtn.textContent = 'Mark onsite install complete';
      }
    });
  });
}
