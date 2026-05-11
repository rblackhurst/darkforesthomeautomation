# Dark Forest Home Automation — Planning & Decision Log

This document is the single source of truth for product direction, architecture
decisions, and what we're building when. Update it as decisions change. Older
decisions are kept in the **Decision Log** at the bottom rather than deleted,
so we can see *why* something changed.

---

## 1. Product Vision

DFHA delivers locally-hosted home automation backends (Home Assistant + paired
devices) installed in customers' homes. The product has three audiences:

1. **Public** — marketing site and (eventually) DIY-package online sales.
2. **DFHA staff** — installer tools: sales form, pre-install checklist, backend
   install guide, pairing sheet, automation install, on-site install, and
   customer walkthrough form. One job record carries from sale through
   walkthrough.
3. **Customers** — individual portal per install: view their package and docs,
   choose an uptime service tier, submit trouble/automation requests, and (key
   brand promise) **export everything and walk away** at any time. "You own
   everything."

---

## 2. Stack & Hosting

| Layer | Choice | Why |
|---|---|---|
| Language / framework | **Python + Django** | Forms-heavy app; Django admin gives us a free internal CRUD UI; `django-allauth` covers auth + 2FA + invite codes; one process, one box, one deploy. |
| Database | **Postgres** on the same VPS | Simple for v1; can split off to managed Postgres later. |
| Hosting | **Hetzner Cloud CX22** (~$5/mo) | Vendor-neutral (not AWS/Google), cheap, EU-hosted. |
| CDN / DNS | **Cloudflare** | Already used for DNS; free tier; sits in front of the app. |
| Email (transactional) | **Postmark** | Best inbox-placement reputation; free <100/mo then $15/mo. |
| Payments | **Stripe Billing** | Subscriptions for uptime tiers + one-off DIY-package sales. |
| Backups | **Backblaze B2** | ~$1/mo for nightly Postgres dumps. |
| Marketing site | **GitHub Pages** (unchanged) | No reason to move it. |

**Target monthly cost: $5–25.** Hard ceiling: $50.

**Mail strategy:** Protonmail stays for personal/business inbox. Postmark
handles all app-generated mail (invites, password resets, walkthrough
confirmations, billing receipts) with proper SPF/DKIM/DMARC records on the
sending domain via Cloudflare.

---

## 3. Domain Strategy

| Domain | Role |
|---|---|
| `darkforesthomeautomation.com` | Public marketing site, stays on GitHub Pages. |
| `app.darkforesthomeautomation.com` | The Django app. Single login routes employees → installer tools, customers → portal. |
| `darkforesthomeautomation.net` | 301 redirect to `.com`. Defensive only. |
| `dfha.net` | **Short-link domain** for outgoing email and printed handouts (e.g., `dfha.net/setup/abc123`, `dfha.net/portal`). Points at the same Django app. |

---

## 4. Auth & Roles

- **Employees** (3–4 in foreseeable future): email + password + **TOTP 2FA**.
  Role-based access (admin, installer).
- **Customers**: one account per install. **Invite-by-email** with a one-time
  setup code embedded in the link. Customer chooses their own password at
  setup; 2FA required.
- **Public**: no auth.

Invoice number is the canonical job ID. Last name and install date are
searchable fields, not keys.

---

## 5. Data Model (v1 outline)

- **Customer** — name, address, contact info.
- **Job** — pk = invoice #; FK to Customer; install date; status; sign-off
  state. One Job has **four install records**, each independently resumable:
  1. **BackendInstall** — current `install.html` content (Backend Office &
     Shop Prep).
  2. **PairingSheet** — devices on hand, paired in Home Assistant.
  3. **AutomationConfig** — blueprint automations + custom automations.
  4. **OnsiteInstall** — on-site work: VLAN/DHCP changes, Tailscale signup,
     remote-monitoring config.
- **WalkthroughSignoff** — locks protected sections of the Job; triggers the
  post-install email and customer portal activation.
- **AuditLogEntry** — records all changes to **protected sections** after
  walkthrough sign-off only (not every field, not pre-sign-off changes).
- **ServiceSubscription** — Stripe-linked, one of three uptime tiers.
- **TroubleRequest** — customer-submitted; v1 just emails the team.
- **CredentialBundle** — encrypted store of HA/Tailscale/etc. credentials for
  this install; visible in portal only after re-auth.

---

## 6. Credential Handling ("You Own Everything")

**No plain PDF of credentials by email — ever.**

- While customer is active: credentials encrypted at rest, visible only inside
  the portal behind 2FA + a re-auth prompt to reveal.
- **Export ("Download my credentials")**: generates a **one-time encrypted ZIP**
  (customer sets the password at export time, shown once) containing JSON +
  a printable PDF. Clear "this is your only copy" warning.
- The customer's actual upstream accounts (Home Assistant, Tailscale, GitHub,
  HACS) are already created in the customer's name from day one. They can
  detach by simply taking their credentials and revoking our access.

A deterministic password-derivation scheme was considered and rejected: many
credentials (Tailscale keys, GitHub PATs, HACS tokens) are issued opaque
strings that can't follow a formula; one master secret = catastrophic blast
radius; rotation breaks the derivation. The encrypted-export approach gives
the same functional outcome with none of the downsides.

---

## 7. 90-Day Build Order

Target: live, paying-customer-ready app on `app.darkforesthomeautomation.com`
within 90 days. Manual fallbacks ship first so DFHA can sell *now* without
waiting on software.

| Week | Milestone |
|---|---|
| 1–2 | Hetzner box provisioned, Django + Postgres deployed, `app.` subdomain live behind Cloudflare, Postmark wired, employee login + 2FA working. |
| 3–4 | Data model (Customer, Job, four install records, audit log). Django admin usable as internal CRUD UI on day one. |
| 5–6 | Port existing `install.html` content into the BackendInstall form. Sales form + pre-install checklist. |
| 7–8 | PairingSheet, AutomationConfig, OnsiteInstall forms. Walkthrough sign-off (locks job, starts audit trail, triggers post-install email). |
| 9–10 | Customer portal — invite email with setup code, customer signup w/ 2FA, view package + docs, trouble-request form. |
| 11–12 | Stripe Billing (3 uptime tiers + DIY-package quote-request form). "Download my credentials" encrypted export. Polish. |

Pace can accelerate if we move faster than expected.

### Manual fallbacks for v1 (so selling can start before software ships)

- **Post-install credentials**: hand-delivered on a printed sheet until the
  portal reveal ships (Week 9).
- **DIY backend sales**: Stripe Payment Link on the marketing site, no
  checkout UI yet.
- **Trouble tickets**: form posts to email; team replies manually.
- **Customer onboarding emails**: composed manually in Protonmail until
  Postmark templates ship.

---

## 8. Working Agreement

Ron doesn't read code; Claude owns implementation end-to-end.

- Every milestone deploys to a real URL Ron can click through.
- Each milestone ships with a **plain-English test plan** — a checklist of
  things to try and what should happen.
- Claude asks UX questions, never code questions.
- Frequent small commits with descriptive messages so the GitHub timeline is
  human-readable.
- Decisions get logged here in PLANNING.md as we make them.
- Ron signs off on each milestone before the next begins.

---

## 9. Open Questions / Parking Lot

Things we've deferred or haven't decided yet. Add freely.

- Final wording / styling of the post-install email and the in-portal
  "Download my credentials" warning copy.
- Pricing for the three uptime service tiers.
- Whether the trouble-request form should accept photo attachments in v1.
- Whether customer portal should show install photos (and if so, where they're
  stored — Backblaze B2 likely).
- Whether the public DIY-package store needs its own separate app or can live
  as a section of the Django app behind a different theme.

---

## 10. Decision Log

Newest first. Each entry: date, decision, rationale.

- **2026-05-11** — Adopted Django + Hetzner + Cloudflare + Postmark + Stripe
  stack. Rejected Supabase (AWS-hosted), Firebase (Google), and pure
  Cloudflare D1 stack (less batteries-included for a forms-heavy app and a
  first-time builder).
- **2026-05-11** — Rejected deterministic password-derivation scheme for
  credential handoff. Replaced with encrypted one-time export. See §6.
- **2026-05-11** — `app.darkforesthomeautomation.com` for the unified app
  (employees + customers behind one login). `dfha.net` repurposed as
  short-link domain. `.net` parked as redirect.
- **2026-05-11** — Invoice # is the canonical Job primary key.
- **2026-05-11** — Audit trail covers only protected sections after
  walkthrough sign-off, not every field.
- **2026-05-11** — Trouble tickets are a simple submit form in v1; no
  ticketing system.
