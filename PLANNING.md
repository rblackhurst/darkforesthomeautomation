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

## 3a. Server Operations

The Django app lives on a single Hetzner CX22 VPS (`dfha-app-01`, Helsinki).
Three scripts manage its lifecycle, all at the repo root:

| Script | When to run | What it does |
|---|---|---|
| `bootstrap.sh` | Once, on a fresh Ubuntu 24.04 box | Installs nginx + Postgres + Python + certbot, creates the `dfha` user and database, clones the repo, configures gunicorn + nginx + SSL, installs `dfha-deploy`. Idempotent. |
| `harden.sh` | Once, after bootstrap | SSH key-only, root password locked, unattended security upgrades, fail2ban for SSH brute-force protection. |
| `deploy.sh` | Every subsequent update (installed as `/usr/local/bin/dfha-deploy`) | `git pull` → `pip install -r requirements.txt` → `migrate` → `collectstatic` → `systemctl restart dfha`. Takes ~5 seconds. |

**Recovery fallback if SSH is ever broken:** Hetzner web console at
`console.hetzner.cloud` → server → **Console** button. Browser-based VNC
straight into the running OS, no SSH involved.

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
- **CatalogDevice** — entry on the price sheet: device type, model, default
  supplier, supplier SKU, purchase URL, default cost. Maintained in admin.
  Future inventory app extends this row with on-hand quantity and location.
- **PickSheet** — one per Job, generated from the sale + pre-install
  checklist. Snapshot: re-generate by hand if upstream changes. Holds
  `PickSheetLine` rows (FK to CatalogDevice, quantity, optional per-line
  notes for substitutions), grouped by device type then quantity in the
  rendered view. Lives in the flow **between sale and config** — generated
  after pre-install walkthrough, before pairing/automation work begins.

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
| 1–2 | ✅ Hetzner box provisioned, Django + Postgres deployed, `app.` subdomain live behind Cloudflare with SSL, Postmark domain verified. Employee login + TOTP 2FA shipped (`accounts` app). |
| 3–4 | ✅ Data model live in the `jobs` app (Customer, Job, four install records, walkthrough sign-off, audit log, service subscription, trouble request, credential bundle). Django admin wired up as internal CRUD on day one. |
| 5–6 | Port existing `install.html` content into the BackendInstall form (DB-backed, admin-editable checklist templates so content fixes don't need a code deploy). Sales form + pre-install checklist (reuses checklist template infra). CatalogDevice model + admin (price sheet). |
| 6–7 | **PickSheet** generated from sale + pre-install: grouped by device type then quantity, with per-line supplier/SKU/URL pulled from CatalogDevice. Prints clean; re-generate to refresh. Sits between sale and config in the staff flow. |
| 7–8 | **PairingSheet** ✅ landed — per-room device rows with formula-generated HA / Z2M names (`{room_slug}_{device_kind}_{function_slug}`), paired ✓ with timestamp + audit, copy-to-clipboard, lock/unlock. AutomationConfig, OnsiteInstall forms still to do. Walkthrough sign-off (locks job, starts audit trail, triggers post-install email). |
| 9–10 | Customer portal — invite email with setup code, customer signup w/ 2FA, view package + docs, trouble-request form. **Account management** ships alongside: self-service password reset (Django built-ins + Postmark) and a unified "Invite a user" page that covers both employees and customers. |
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
- ~~Pricing for the three uptime service tiers.~~ → Resolved — see `docs/internal/pricing.md`.
- **Account management UX:** for now, employee accounts are created and
  reset via `/admin/auth/user/` (Django admin) and `/admin/accounts/employeetotp/`
  ("Reset TOTP enrolment" action). That's fine for 3–4 staff. Once
  customers exist (Weeks 9–10) we need:
    1. A self-service password-reset flow (forgot password → emailed link),
       wiring Django's built-in reset views to Postmark and theming the
       four templates. Useful for employees too; cheap to ship early.
    2. A purpose-built "manage users" page that handles invite + disable
       + reset-2FA with one set of templates for both employees and
       customers — same UX for "invite an installer" as "invite a
       customer." Bundling it with the customer portal avoids building
       two parallel invite flows.
- Whether the trouble-request form should accept photo attachments in v1.
- Whether customer portal should show install photos (and if so, where they're
  stored — Backblaze B2 likely).
- Whether the public DIY-package store needs its own separate app or can live
  as a section of the Django app behind a different theme.
- Inventory app scope: on-hand quantity + location per CatalogDevice, reorder
  thresholds, multiple stocking locations? Likely a separate app once the
  pick sheet has been in use long enough to learn what we actually need.
- Procurement flow: should "out of stock at pick time" push the buyer to a
  generated procurement page (links to supplier carts pre-populated from
  CatalogDevice rows), or just surface a shortage list to email manually?
- Whether CatalogDevice needs price history (cost changes over time) or a
  single current cost is good enough for v1.

---

## 10. Decision Log

Newest first. Each entry: date, decision, rationale.

- **2026-05-14** — **Employee login + TOTP 2FA shipped** as a small in-house
  `accounts` Django app rather than `django-allauth`. Allauth was named in §2
  as the likely choice; in practice we need ~150 lines (email-or-username
  auth backend, 2-step login → TOTP verify, forced enrolment on first login,
  10 one-time recovery codes hashed at rest, "reset enrolment" admin action,
  middleware that gates staff users out of the app until TOTP is confirmed).
  Allauth would have brought ~25 models, ~12 migrations, and a templating
  surface we'd have had to override anyway for the DFHA look. Customer
  signup + invite codes (Weeks 9–10) can revisit allauth then if its
  invite-flow batteries become valuable; for now we own a smaller surface.
  Dependencies added: `pyotp` (TOTP) + `segno` (pure-Python QR, no Pillow).
  `LOGIN_URL` moved from `/admin/login/` to `/accounts/login/`; `/admin/login/`
  still works as a superuser escape hatch but the middleware enforces 2FA
  on `/admin/` once you're in.

- **2026-05-13** — **Internal pricing reference** committed at
  `docs/internal/pricing.md` (not for client distribution). Source: Session 6 /
  April 2026 PDF. Covers backend setup ($499), UPS, all room kits (comfort +
  safety + entry + outdoor), smart lock options, Connected Home bundle packages
  (1/2/3 BR), per-room add-ons, monitoring plans (Basic $29/mo, Standard
  $49/mo, Premium $79/mo), and full internal BOM costs. Monitoring tier mapping
  for invoice number: 0=none, 1=Basic, 2=Standard, 3=Premium (set per Package
  in admin via `monitoring_tier` field).

- **2026-05-13** — **Invoice number auto-generation.** `invoice_number` (the URL
  key / PK) is now a system-generated temp ID (`DRAFT-XXXXXXXXXXXX`) assigned at
  sale creation — staff no longer type it. The customer-facing formatted code
  (`display_invoice_number`) is generated at pre-install finalization and encodes:
  YYMMDD + M (monitoring tier 0–9) + RR (room count 01–99) + AAA (à-la-carte
  items 001–999) + SS (day sequence 01–99) = 14 chars. Example: `26051320300501`.
  Payment quote email (Postmark) sent at finalization unless override flag is set.

- **2026-05-13** — **Internal prep** is now a standalone page (`/jobs/<invoice>/internal-prep/`)
  rather than a checklist step. It shows the device list from the sale (with per-line
  "confirmed in stock" checkboxes), a GitHub username field + "account created" toggle,
  and a "picklist picked" checkbox. The pre-install checklist's Step 4 becomes a single
  checkbox ("internal prep complete") that links to the dedicated page.

- **2026-05-13** — **Room walkthrough** added to the pre-install checklist page as a
  dynamic section below the checklist steps. Staff adds rooms by type (Bedroom, Kitchen,
  etc.) with an optional custom name to distinguish multiples (e.g. "Master", "Kids").
  Devices are assigned per room via a modal; customers confirm each one. Confirmed room
  devices combine with sale-line devices on the pick sheet.

- **2026-05-13** — **Package model** added for predefined device bundles (Starter,
  Standard, Premium, etc.). `PackageDevice` holds the M2M relationship with quantities.
  Selecting a package on the sales form pre-fills the device table; staff can add
  à-la-carte devices on top. `SaleLine` is the per-job snapshot of what was sold
  (device + quantity + cost snapshot + confirmed-in-stock flag).

- **2026-05-13** — **Pick sheet** is now computed dynamically from `SaleLine` rows
  (from the sale) plus confirmed `RoomDevice` rows (from the pre-install walkthrough),
  grouped by device type then sorted by descending quantity. No stored snapshot —
  "re-generate" means reload. Supplier/SKU/URL pulled live from `CatalogDevice`.
  Printable via browser print dialog. URL: `/jobs/<invoice>/pick-sheet/`.

- **2026-05-12** — Picked **DB-backed checklist templates** for porting
  `install.html` into the `BackendInstall` form. New models in the `jobs`
  app: `ChecklistTemplate` (slug + integer version, e.g. `backend-install`
  v1, v2 …), `ChecklistStep` (ordered, optional Markdown intro),
  `ChecklistItem` (Markdown body — supports the code blocks/tables/links
  install.html already uses), and `BackendInstallItemState` (per-job,
  per-item: checked, by, when, plus per-item installer notes). `BackendInstall`
  has a `template` FK that **snapshots** the version it started against —
  publishing a new template version doesn't disturb in-progress jobs.
  Trade-off vs. defining steps in Python: more upfront porting work,
  but content fixes become admin edits with no code deploy, which is the
  whole point. The template + step + item models are generic; the
  pre-install checklist (Weeks 5–6) and other install records can reuse
  them by adding their own `…ItemState` model. Migration removes the
  unused `BackendInstall.progress` JSON field — replaced by item-state rows.
- **2026-05-12** — Added **pick sheet** to the flow between sale and config.
  Two new models in §5: `CatalogDevice` (price sheet: device type, model,
  supplier, SKU, URL, cost) maintained in admin, and `PickSheet` per Job
  with line items grouped by device type then quantity. Pick sheet is a
  **snapshot** generated on demand from sale + pre-install — re-generate
  manually if upstream changes (matches how a paper pick sheet behaves on
  the warehouse floor). Catalog lives inside the Django app rather than an
  external sheet so procurement fields and (later) inventory data can hang
  off the same row. Slotted into Weeks 5–6 (catalog) and 6–7 (pick sheet).
  Inventory app and procurement-page push deferred to §9.
- **2026-05-12** — Data model landed as a single `jobs` Django app rather than
  splitting Customer/Job/billing/portal into separate apps. Everything in v1
  pivots around Job; one app keeps imports flat and the admin coherent. Can
  split later if (e.g.) the customer portal grows its own surface area.
  `Job.invoice_number` is a `CharField` PK so alphanumeric invoice IDs work.
  `CredentialBundle.payload` is plaintext JSON for now — the admin gates it
  behind `is_superuser`; encryption + one-time encrypted export ship in
  Weeks 11–12 (§6).
- **2026-05-12** — Added `harden.sh` (SSH key-only, root password locked,
  unattended-upgrades, fail2ban). Hetzner web console is the recovery
  fallback if SSH ever breaks.
- **2026-05-12** — Added `deploy.sh` (installed as `/usr/local/bin/dfha-deploy`)
  so subsequent updates don't require running the full bootstrap. Eventually
  a GitHub Action will run this on every push to `main`.
- **2026-05-12** — Branch `claude/plan-dark-forest-architecture-qMxhN` merged
  to `main`. Working in short-lived feature branches off `main` from here.
- **2026-05-12** — Deployment pipeline live at
  `https://app.darkforesthomeautomation.com`. `dfha-app-01` is a Hetzner CX22
  in Helsinki (Falkenstein had no CX22 capacity at provisioning time).
  Hello-world page confirms Hetzner → Cloudflare DNS → nginx → gunicorn →
  Django → Postgres all work with a valid Let's Encrypt cert.
- **2026-05-12** — Postmark sending domain verified (DKIM + Return-Path
  records propagated through Cloudflare).
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
