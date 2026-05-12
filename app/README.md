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
├── jobs/                # Data model + admin (Customer, Job, install records,
│   │                    # walkthrough sign-off, audit log, service
│   │                    # subscriptions, trouble requests, credentials)
│   ├── models.py
│   ├── admin.py
│   └── migrations/
└── README.md            # this file
```

## Internal CRUD (Django admin)

After `migrate`, create a superuser and visit `/admin/`:

```bash
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver
```

The admin is the day-one CRUD UI for staff: add a Customer, then a Job
(invoice number is the PK), and the four install records + walkthrough +
subscription appear as inlines on the Job page.
