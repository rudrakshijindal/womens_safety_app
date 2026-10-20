# Handoff: Teammate 1 -> Teammate 2

Teammate 1's part (Steps 1.1 - 1.6) is finished and tested (`pytest -q` -> 82 passed).

## Setup (Windows, PowerShell)
```powershell
git clone <repo-url>
cd womens_safety_app
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # put a random SECRET_KEY in .env
flask --app app init-db
python -m scripts.seed_demo
flask --app app run
```
Demo logins (password `Demo@1234`): admin@, riya@ (user), priya@ (guardian) `@safecircle.demo`.

## Rules from the contract
- Teammate 1 owns: `routes/auth.py`, `routes/guardian.py`, `routes/admin.py`, `services/auth.py`, `services/matching.py`, `services/notifications.py`, `models/`.
- Teammate 2 owns: `routes/main.py`, `routes/profile.py`, `routes/sos.py`, `routes/journey.py`, `routes/notifications.py`.
- Teammate 2 only CALLS the shared functions, and never rewrites them.
- Work on branches named `teammate2-*` and merge through pull requests.

## What Teammate 2 calls

```python
from services.auth import role_required                 # @role_required("user")
from services.notifications import notify                # notify(user_id, type, message, link)
from services.matching import find_eligible_guardians, dispatch_to_guardians
```

SOS flow (Step 2.3), after creating the `EmergencyRequest`:
```python
matches = find_eligible_guardians(req.latitude, req.longitude, limit=5)
dispatch_to_guardians(req, matches)   # saves the matches + notifies each guardian in-app
notify(current_user.id, "request_created", "In-app alert created (demo).", "/dashboard")
```
After that the guardian dashboard, accept/reject, the user's live request tracker and the admin analytics all work with no more code.

## Things already built that Teammate 2 can reuse (do not rebuild)
- `templates/base.html`, `static/css/custom.css`, `static/js/live.js`: layout, theme, navbar, bell with unread count, toasts and live refresh. To make a region update live, add `data-live="some-unique-id"` to its container (never to a form being typed in).
- Notification bell + `unread_count` context processor (Step 2.5 only needs the full notifications page).
- `_macros.html`: `status_badge`, `stat_card`, `csrf_field`.

## Temporary stand-ins to remove or replace
- `routes/demo.py` and the "Try a demo emergency" card on `templates/user/dashboard.html` stand in for the SOS button. Delete them when `routes/sos.py` works.
- `routes/main.py` has one small edit by Teammate 1 (it passes `presets` to the dashboard). Keep or remove it together with the demo card.
- The admin "Create demo emergency" tool can stay as a backup for the demo.
