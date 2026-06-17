'use strict';

const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: JSON.stringify(body),
  }).then(r => r.json());
}

function showToast(isError) {
  const id = isError ? 'save-toast-err' : 'save-toast';
  const t = document.getElementById(id);
  if (!t) return;
  t.classList.add('visible');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('visible'), 2200);
}

function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

// ── Tailscale field ───────────────────────────────────────────────────────────
const tailscaleInput = document.getElementById('tailscale-account');
if (tailscaleInput) {
  tailscaleInput.addEventListener('input', debounce(() => {
    post(window.WT_URLS.saveField, { field: 'tailscale_account', value: tailscaleInput.value.trim() })
      .then(() => showToast(false));
  }, 600));
}

// ── Walkthrough notes ─────────────────────────────────────────────────────────
const notesEl = document.getElementById('walkthrough-notes');
if (notesEl) {
  notesEl.addEventListener('input', debounce(() => {
    post(window.WT_URLS.saveField, { field: 'customer_acknowledgement', value: notesEl.value })
      .then(() => showToast(false));
  }, 600));
}

// ── Service plan selector ─────────────────────────────────────────────────────
let selectedPlan = window.WT_CURRENT_PLAN || 'none';

const planLabelMap = {};
(window.WT_PLAN_LABELS || []).forEach(c => { planLabelMap[c.value] = c.label; });

document.querySelectorAll('.plan-option').forEach(opt => {
  opt.addEventListener('click', () => {
    selectedPlan = opt.dataset.value;
    document.querySelectorAll('.plan-option').forEach(o => {
      o.classList.toggle('selected', o.dataset.value === selectedPlan);
      o.querySelector('input').checked = o.dataset.value === selectedPlan;
    });

    // Update Section 6 hint + enable/disable activate button
    const activationLabel = document.getElementById('activation-plan-label');
    const activateBtn = document.getElementById('activate-btn');
    if (activationLabel) {
      if (selectedPlan && selectedPlan !== 'none') {
        activationLabel.textContent = (planLabelMap[selectedPlan] || selectedPlan)
          + '. Billing starts the first of next month after activation.';
        if (activateBtn && window.WT_SIGNED) activateBtn.disabled = false;
      } else {
        activationLabel.textContent = 'No service plan selected — choose one in section 5 above.';
        if (activateBtn) activateBtn.disabled = true;
      }
    }

    const hintEl = document.getElementById('plan-save-hint');
    post(window.WT_URLS.savePlan, { plan: selectedPlan }).then(data => {
      if (data.ok) {
        showToast(false);
        if (hintEl) { hintEl.textContent = ''; }
      } else {
        showToast(true);
        if (hintEl) {
          hintEl.textContent = `Could not save: ${data.error || 'unknown error'}`;
          hintEl.className = 'plan-save-hint err';
        }
      }
    }).catch(() => {
      showToast(true);
      if (hintEl) {
        hintEl.textContent = 'Network error — plan not saved';
        hintEl.className = 'plan-save-hint err';
      }
    });
  });
});

// ── Sign walkthrough ──────────────────────────────────────────────────────────
const signBtn = document.getElementById('sign-btn');
if (signBtn) {
  signBtn.addEventListener('click', () => {
    const nameInput = document.getElementById('customer-name');
    const customerName = nameInput?.value.trim();
    if (!customerName) {
      nameInput?.focus();
      nameInput?.setCustomValidity('Required');
      return;
    }
    signBtn.disabled = true;
    signBtn.textContent = 'Signing…';
    post(window.WT_URLS.sign, { customer_name: customerName })
      .then(data => {
        if (data.ok) {
          window.location.reload();
        } else {
          signBtn.disabled = false;
          signBtn.textContent = 'Sign walkthrough';
          alert(data.error || 'Sign failed');
        }
      });
  });
}

// ── Send final invoice ────────────────────────────────────────────────────────
const invoiceBtn = document.getElementById('invoice-btn');
if (invoiceBtn) {
  invoiceBtn.addEventListener('click', () => {
    invoiceBtn.disabled = true;
    invoiceBtn.textContent = 'Sending…';
    const statusEl = document.getElementById('invoice-status');

    post(window.WT_URLS.finalInvoice, {}).then(data => {
      if (data.ok && data.stripe_invoice_sent) {
        if (statusEl) {
          statusEl.className = 'invoice-hint ok';
          const link = data.stripe_invoice_url
            ? ` <a href="${data.stripe_invoice_url}" target="_blank" rel="noopener">View in Stripe →</a>`
            : '';
          statusEl.innerHTML = `Invoice sent.${link} Reload to see payment status.`;
        }
        invoiceBtn.textContent = 'Invoice sent';
      } else if (data.ok && !data.stripe_invoice_sent) {
        invoiceBtn.disabled = false;
        invoiceBtn.textContent = 'Send final invoice';
        if (statusEl) {
          statusEl.className = 'invoice-hint err';
          statusEl.textContent = `Stripe error: ${data.stripe_invoice_error || 'unknown error'}`;
        }
      } else {
        invoiceBtn.disabled = false;
        invoiceBtn.textContent = 'Send final invoice';
        if (statusEl) {
          statusEl.className = 'invoice-hint err';
          statusEl.textContent = data.error || 'Failed to send invoice';
        }
      }
    });
  });
}

// ── Activate service plan ─────────────────────────────────────────────────────
const activateBtn = document.getElementById('activate-btn');
if (activateBtn) {
  activateBtn.addEventListener('click', () => {
    activateBtn.disabled = true;
    activateBtn.textContent = 'Activating…';
    const statusEl = document.getElementById('activate-status');

    post(window.WT_URLS.activatePlan, {}).then(data => {
      if (data.ok) {
        if (statusEl) {
          statusEl.className = 'invoice-hint ok';
          statusEl.textContent = `Subscription activated (${data.subscription_status || 'active'}). Reload to update status.`;
        }
        activateBtn.textContent = 'Activated';
      } else {
        activateBtn.disabled = false;
        activateBtn.textContent = 'Activate service plan';
        if (statusEl) {
          statusEl.className = 'invoice-hint err';
          statusEl.textContent = data.error || 'Activation failed';
        }
      }
    }).catch(() => {
      activateBtn.disabled = false;
      activateBtn.textContent = 'Activate service plan';
      if (statusEl) {
        statusEl.className = 'invoice-hint err';
        statusEl.textContent = 'Network error — try again';
      }
    });
  });
}
