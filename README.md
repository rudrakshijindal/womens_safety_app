# SafeCircle - Women's Safety & Emergency Response System

**Teammate 1 module: authentication, Verified Guardian Network, matching and admin.**
An academic prototype built with Flask. It is not a substitute for emergency services.
In an emergency call **112**.

## What this module does

| Area | Features |
|---|---|
| Accounts | Registration, login, logout, three roles (user, guardian, admin), hashed passwords, CSRF protection |
| Guardian network | Guardian application, admin approve / reject, in-app notification of the decision |
| Duty and location | Approved guardians set a location (area list, coordinates or browser location) and switch on duty |
| Matching | Approved + on-duty guardians ranked by distance with the Haversine formula. Only approximate distance is shown |
| Requests | Guardian accepts or rejects, only one guardian can accept, the accepting guardian marks it resolved |
| Admin | Live analytics, applications, guardians, users, requests, and a demo-emergency tool |
| Live updates | Dashboards, bell and request tracker refresh by themselves every ~4 s (polling), with a toast for new notifications |
| Data | Seed script that creates a demo admin, users and sample guardians |

## What it does NOT do (be honest about this)

- It does not send SMS or make phone calls. Alerts are in-app notifications and records only.
- It does not contact the police.
- It does not track location in the background. A location is saved only when the guardian presses Save.
- Sample guardians are simulated people with simulated locations.
- "Approved by admin" means an administrator reviewed the submitted details. No documents are uploaded or verified.
- The SOS button itself belongs to another team member. The "Try a demo emergency" card on the user dashboard (`routes/demo.py`) and the admin "Create demo emergency" tool stand in for it.

## Setup (Windows, PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then put a long random SECRET_KEY in .env
flask --app app init-db
python -m scripts.seed_demo     # demo accounts (add --reset to wipe and recreate)
flask --app app run
```

Open http://127.0.0.1:5000. Generate a secret key with:
`python -c "import secrets; print(secrets.token_hex(32))"`

Run the tests with `pytest -v`.

To create your own admin account: `flask --app app create-admin`

## Demo accounts (password for all: `Demo@1234`)

| Role | Email |
|---|---|
| Admin | admin@safecircle.demo |
| User | riya@safecircle.demo, ananya@safecircle.demo |
| Guardian (approved, on duty) | priya@, neha@, pooja@safecircle.demo |
| Guardian (approved, off duty) | sunita@safecircle.demo |
| Guardian (pending) | kavita@safecircle.demo |

## Project structure

```
app.py               app factory, template helpers, CLI commands
config.py            settings (SECRET_KEY from .env)
extensions.py        db, login manager, CSRF
models/models.py     8 database tables
services/            business logic (auth, matching, guardian, admin, notifications, validators)
routes/              thin web routes (main, auth, guardian, admin)
templates/ static/   pages and styling
scripts/seed_demo.py demo data
tests/               pytest suite
```

## For the SOS module (integration)

After creating an `EmergencyRequest`, call:

```python
from services.matching import find_eligible_guardians, dispatch_to_guardians

matches = find_eligible_guardians(req.latitude, req.longitude, limit=5)
dispatch_to_guardians(req, matches)
```

This links the matched guardians to the request and sends them an in-app notification.
Guardians then accept or reject from their dashboard, and the requester's dashboard shows the status.

## Security notes

- Passwords are stored only as salted hashes (Werkzeug).
- Every form has a CSRF token; logout is a POST request.
- Roles are fixed on the server. Nothing in a form can make an account an admin or approve a guardian.
- Admin and guardian pages check the role on the server (403 for the wrong role).
- Guardians' exact coordinates are never shown to users or to the matching result.
- Redirect targets after login are restricted to this site.
