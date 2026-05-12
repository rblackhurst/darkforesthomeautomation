# DFHA App

The Django app that powers `app.darkforesthomeautomation.com` — installer
tools (employees) and customer portal in one codebase, behind one login.

This directory is independent of the marketing site at the repo root, which
remains a static GitHub Pages site.

See `../PLANNING.md` for product direction, stack, and build order.

---

## Run locally

```bash
cd app
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Then visit http://127.0.0.1:8000/.

## Layout

```
app/
├── manage.py            # Django's CLI entry point
├── requirements.txt     # Python dependencies
├── dfha/                # Project settings module
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py          # Production entry point (gunicorn)
│   └── asgi.py
└── README.md            # this file
```

Apps for Customer, Job, install records, etc. will live as sibling
directories alongside `dfha/` once we start the data model (Week 3 of the
build order).
