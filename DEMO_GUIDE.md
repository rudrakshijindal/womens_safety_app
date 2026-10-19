# Demo guide (about 6 minutes)

## Before you present (10 minutes earlier)

1. Charge the laptop. Connect to the internet (fonts and icons load online).
2. Open PowerShell in the project folder:
   ```powershell
   cd "C:\Users\HP PAVILION GAMING\womens_safety_app"
   .venv\Scripts\activate
   python -m scripts.seed_demo --reset
   ```
   Type `YES`. This gives a clean, known starting state.
3. Run `pytest -v` once so you can say "74 passed" with confidence.
4. Start the site: `flask --app app run`
5. Open **three different browsers** (for example Brave, Chrome, Edge), each at http://127.0.0.1:5000, and log in:
   - Browser 1: `admin@safecircle.demo`
   - Browser 2: `priya@safecircle.demo` (guardian)
   - Browser 3: `riya@safecircle.demo` (user)
   Password for all: `Demo@1234`
6. Keep the terminal window ready for the tests at the end.

## The script

**1. Landing page (30 s)**
"This is SafeCircle, a Verified Guardian Network. Guardians are approved by an administrator, and the nearest ones on duty are matched to a request. This is my part: accounts, guardian approval, matching and the admin side."
Point at the banner: "It's an academic prototype, and it's honest about its limits."

**2. Guardian signup and approval (1 min)**
- Open a private window, go to **Become a guardian**, apply with new test details. Show that the status is **Pending**, and that `/guardian/dashboard` sends them back to the status page.
- Admin browser: **Applications**, click **Approve**.
- Private window: refresh. The bell shows "Approved by admin".
"Only an administrator can approve. Nothing in the form can change the role or the status."
(Shortcut if short on time: use `kavita@safecircle.demo`, the pending sample guardian, from the admin Applications page.)

**3. Guardian goes on duty (30 s)**
Guardian browser: show the duty toggle and the location card (area list, coordinates, or "Use my current location"). "A location is saved only when they press Save. There's no background tracking."

**4. Demo emergency and matching (1 min)**
Admin browser: **Requests**, choose Riya Sharma and **Raj Nagar**, click **Create demo emergency**.
Read the green message: "Matched nearest first: Priya 0.0 km, Neha 7.9 km, Pooja 10.5 km. Sunita is off duty so she's skipped."
"Distance uses the Haversine formula on stored coordinates, so no paid map API is needed. Users only see approximate distance, never exact coordinates."

**5. Guardian responds (1 min)**
Guardian browser: refresh. The request appears with its distance. Click **Accept**.
"Only after accepting does the guardian see the requester's details. If a second guardian tries to accept, they're told it's no longer open."
User browser: refresh. Status **Accepted** with Priya's name, plus a notification.
Guardian browser: **Mark as resolved**.

**6. Admin analytics (30 s)**
Admin browser: **Admin** dashboard. "These numbers are calculated from the database: counts, status chart, average time to accept and resolve."

**7. Tests and security (1 min)**
Terminal: `pytest -v`. "74 automated tests pass."
Then in the user browser open http://127.0.0.1:5000/admin/ and show **Access denied (403)**.
"Passwords are hashed, every form has a CSRF token, and role checks run on the server."

**8. Close (15 s)**
"Not included: real SMS or calls, police integration, background tracking, document verification. The SOS button is my teammate's module, and it plugs in through one function, `dispatch_to_guardians`."

## Questions the mam may ask

**How does matching work?**
It loads approved guardians who are on duty and have a location, computes the great-circle distance to the request with the Haversine formula, sorts nearest first and takes the top five. Code: `services/matching.py`.

**How do you stop a user making themselves an admin?**
The register route sets the role on the server and ignores any role in the form. Admin accounts can only be created from the command line (`flask create-admin`) or the seed script. There's a test for it.

**How are passwords stored?**
As salted hashes with Werkzeug. The database never holds the real password.

**What if two guardians accept at the same time?**
The first one's accept changes the request status. The second sees it is no longer pending and gets a message. Only one guardian can ever be recorded. There's a test for it.

**How is "verified" guaranteed?**
It isn't, and we don't claim it. "Approved by admin" means an administrator reviewed the application. No documents are uploaded or checked in this prototype. A real system would need ID verification and background checks.

**Are the guardians real?**
No. The sample guardians are labelled `[SAMPLE]` and their locations are simulated (Ghaziabad areas).

**What stops a guardian seeing someone else's request?**
A guardian can only respond to requests they were matched to. Responding to any other request returns 403. There's a test for it.

**What would you add next?**
Real SMS and call delivery, live location with consent and expiry, ID verification, rate limiting, and a production database and server.

## If something goes wrong

| Problem | Fix |
|---|---|
| Page looks unstyled | No internet. Reconnect and refresh (Bootstrap and fonts load online) |
| Login fails | You may have reseeded. Use password `Demo@1234`, and the `@safecircle.demo` emails |
| "Access denied" for the wrong role | You are logged in as a different account in that browser. Log out and log in again |
| Nothing is matched | The guardians are off duty. Reseed with `python -m scripts.seed_demo --reset`, or turn Priya on duty |
| Page not updating | Press the **Refresh** button or reload. Pages don't auto-refresh |
| Server stopped | Run `flask --app app run` again in the terminal |
