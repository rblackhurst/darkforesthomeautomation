# DFHA Internal Tools — Session Handoff

`PLANNING.md` is the source of truth for product direction, stack, and the
90-day build order. Read it first.

## Where we are

- Weeks 1–2 ✅ — Hetzner VPS, Django + Postgres, `app.darkforesthomeautomation.com`
  live behind Cloudflare with SSL, Postmark sending domain verified.
- Weeks 3–4 ✅ — Data model in `app/jobs/` (Customer, Job, four install
  records, walkthrough sign-off, audit log, service subscription, trouble
  request, credential bundle). Django admin wired up as day-one internal CRUD.
- Up next — Weeks 5–6: port `install.html` content into the BackendInstall
  form; sales form + pre-install checklist.

## Working in this repo

- Marketing site (HTML at the repo root) is independent of the Django app.
- All app code lives under `app/`. See `app/README.md` for local run steps.
- Short-lived feature branches off `main`. Push to `main` triggers
  `dfha-deploy` on the server.

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
