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

// ── Tailscale field ───────────────────────────────────────────────────────────
const tailscaleInput = document.getElementById('tailscale-account');
if (tailscaleInput) {
  tailscaleInput.addEventListener('input', debounce(() => {
    post(window.WT_URLS.saveField, { field: 'tailscale_account', value: tailscaleInput.value.trim() })
      .then(() => showToast());
  }, 600));
}

// ── Walkthrough notes ─────────────────────────────────────────────────────────
const notesEl = document.getElementById('walkthrough-notes');
if (notesEl) {
  notesEl.addEventListener('input', debounce(() => {
    post(window.WT_URLS.saveField, { field: 'customer_acknowledgement', value: notesEl.value })
      .then(() => showToast());
  }, 600));
}

// ── Service plan selector ─────────────────────────────────────────────────────
let selectedPlan = window.WT_CURRENT_PLAN || 'none';

document.querySelectorAll('.plan-option').forEach(opt => {
  opt.addEventListener('click', () => {
    selectedPlan = opt.dataset.value;
    document.querySelectorAll('.plan-option').forEach(o => {
      o.classList.toggle('selected', o.dataset.value === selectedPlan);
      o.querySelector('input').checked = o.dataset.value === selectedPlan;
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

    const body = selectedPlan && selectedPlan !== 'none'
      ? { service_plan: selectedPlan }
      : {};

    post(window.WT_URLS.finalInvoice, body).then(data => {
      if (data.ok && data.stripe_invoice_sent) {
        if (statusEl) {
          statusEl.className = 'invoice-hint ok';
          const link = data.stripe_invoice_url
            ? ` <a href="${data.stripe_invoice_url}" target="_blank" rel="noopener">View in Stripe →</a>`
            : '';
          statusEl.innerHTML = `Invoice sent.${link}`;
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
