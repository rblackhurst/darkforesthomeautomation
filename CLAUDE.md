# DFHA Internal Tools — Session Handoff

`PLANNING.md` is the source of truth for product direction, stack, and the
90-day build order. Read it first.

## Where we are

- Weeks 1–2 ✅ — Hetzner VPS, Django + Postgres, `app.darkforesthomeautomation.com`
  live behind Cloudflare with SSL, Postmark sending domain verified. Employee
  login + TOTP 2FA shipped (`accounts` app).
- Weeks 3–4 ✅ — Data model in `app/jobs/` (Customer, Job, four install
  records, walkthrough sign-off, audit log, service subscription, trouble
  request, credential bundle). Django admin wired up as day-one internal CRUD.
- Weeks 5–6 ✅ — Sales form, packages, edit-sale flow, pre-install checklist
  with room walkthrough, CatalogDevice (46 seeded), internal prep page,
  invoice auto-generation, finalize flow with Postmark quote email.
- Weeks 6–7 ✅ — PickSheet computed live from SaleLine + confirmed RoomDevice,
  grouped by device type, printable. `/jobs/<invoice>/pick-sheet/`.
- Weeks 7–8 (in progress) — PairingSheet ✅ landed (per-room rows, formula HA/Z2M
  names, paired ✓ with audit, lock/unlock). OnsiteInstall ✅ landed (hybrid
  cards: VLAN/DHCP, Tailscale, remote monitoring, with confirmation flags;
  "Mark complete" advances Job → WALKTHROUGH). Still to do: AutomationConfig,
  walkthrough sign-off.
- Up next — finish Weeks 7–8: AutomationConfig form, walkthrough sign-off
  (locks protected sections, starts audit trail, triggers post-install email).

**Keep this section current** — update "Where we are" with any milestone-
shifting commit so the next session inherits accurate state. PLANNING.md
remains the long-form source of truth.

## Working in this repo

- Marketing site (HTML at the repo root) is independent of the Django app.
- All app code lives under `app/`. See `app/README.md` for local run steps.
- Short-lived feature branches off `main`. **Deploy is automatic** — pushes
  to `main` fire `.github/workflows/deploy.yml`, which SSHes to `dfha-app-01`
  and runs `dfha-deploy`. Manually deploy a non-main branch via the Actions
  tab → "Deploy to production" → Run workflow. For hands-on recovery,
  `sudo dfha-deploy` on the server still works.

## Dev vs. prod environments

Ron's dev machine is **Windows** (PowerShell). The production server
(`dfha-app-01`, Hetzner CX22, Ubuntu 24.04) is **Linux** (bash). When
giving Ron commands to run, match the environment:

- **Local dev (Windows PowerShell):** backslashes and `.venv\Scripts\…`.

  ```
  .venv\Scripts\pip install -r requirements.txt
  .venv\Scripts\python manage.py migrate
  .venv\Scripts\python manage.py runserver
  ```

- **Production (Linux, over SSH):** forward slashes, `.venv/bin/…`, and
  the installed `dfha-deploy` command for routine updates:

  ```
  sudo -u dfha dfha-deploy
  ```

When in doubt which box a command is for, label it explicitly
("on your Windows machine:" / "on the server:").
