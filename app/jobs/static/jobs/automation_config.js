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

// ── Blueprint list ────────────────────────────────────────────────────────────

let blueprints = window.AC_BLUEPRINTS || [];

function renderBlueprints() {
  const list = document.getElementById('blueprint-list');
  if (!list) return;
  list.innerHTML = '';
  if (blueprints.length === 0) {
    list.innerHTML = '<li class="blueprint-empty"><em>No blueprints added yet.</em></li>';
    return;
  }
  blueprints.forEach(bp => {
    const li = document.createElement('li');
    li.className = 'blueprint-item';
    li.dataset.id = bp.id;
    li.innerHTML = `
      <div class="bp-content">
        <div class="bp-name">${escHtml(bp.name)}</div>
        ${bp.notes ? `<div class="bp-notes">${escHtml(bp.notes)}</div>` : ''}
      </div>
      <button type="button" class="bp-remove" title="Remove">×</button>
    `;
    li.querySelector('.bp-remove').addEventListener('click', () => removeBlueprint(bp.id));
    list.appendChild(li);
  });
}

function removeBlueprint(id) {
  post(window.AC_URLS.removeBlueprint, { id })
    .then(data => {
      if (data.ok) { blueprints = data.blueprints; renderBlueprints(); showToast(); }
    });
}

const addForm = document.getElementById('add-blueprint-form');
if (addForm) {
  addForm.addEventListener('submit', e => {
    e.preventDefault();
    const nameEl = document.getElementById('bp-name');
    const notesEl = document.getElementById('bp-notes');
    const name = nameEl.value.trim();
    if (!name) { nameEl.focus(); return; }
    post(window.AC_URLS.addBlueprint, { name, notes: notesEl.value.trim() })
      .then(data => {
        if (data.ok) {
          blueprints = data.blueprints;
          renderBlueprints();
          nameEl.value = '';
          notesEl.value = '';
          nameEl.focus();
          showToast();
        }
      });
  });
}

renderBlueprints();

// ── Custom YAML ───────────────────────────────────────────────────────────────

const yamlEl = document.getElementById('custom-yaml');
if (yamlEl) {
  let yamlTimer;
  yamlEl.addEventListener('input', () => {
    clearTimeout(yamlTimer);
    yamlTimer = setTimeout(() => {
      post(window.AC_URLS.saveYaml, { value: yamlEl.value }).then(() => showToast());
    }, 800);
  });
}

// ── Complete ──────────────────────────────────────────────────────────────────

const completeBtn = document.getElementById('complete-btn');
if (completeBtn) {
  completeBtn.addEventListener('click', () => {
    completeBtn.disabled = true;
    completeBtn.textContent = 'Saving…';
    post(window.AC_URLS.complete, {}).then(data => {
      if (data.ok) {
        window.location.href = window.AC_URLS.onsiteUrl;
      } else {
        completeBtn.disabled = false;
        completeBtn.textContent = 'Mark automation config complete';
      }
    });
  });
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
