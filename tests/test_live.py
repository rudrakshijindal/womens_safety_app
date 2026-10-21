"""Live-update support: marked regions, notification badge data, demo emergency + cancel."""
from models import EmergencyRequest, Notification
from scripts.seed_demo import DEMO_PASSWORD, seed


def _login(client, email):
    r = client.post("/login", data={"email": email, "password": DEMO_PASSWORD})
    assert r.status_code == 302


def test_live_script_is_served_and_loaded_when_logged_in(app):
    seed()
    c = app.test_client()
    assert c.get("/static/js/live.js").status_code == 200
    assert b"live.js" not in c.get("/").data          # not for anonymous visitors
    _login(c, "riya@safecircle.demo")
    assert b"js/live.js" in c.get("/dashboard").data


def test_dashboards_have_live_regions(app):
    seed()
    expected = {
        "riya@safecircle.demo": [b'data-live="u-history"', b'data-live="bell-badge"'],
        "priya@safecircle.demo": [b'data-live="g-incoming"', b'data-live="g-active"', b'data-live="g-metrics"'],
        "admin@safecircle.demo": [b'data-live="a-cards"', b'data-live="a-chart"'],
    }
    paths = {"riya@safecircle.demo": "/dashboard", "priya@safecircle.demo": "/guardian/dashboard",
             "admin@safecircle.demo": "/admin/"}
    for email, markers in expected.items():
        c = app.test_client()
        _login(c, email)
        body = c.get(paths[email]).data
        for m in markers:
            assert m in body, (email, m)


def test_user_demo_emergency_reaches_guardians_and_updates_bell(app):
    seed()
    user, guardian = app.test_client(), app.test_client()
    _login(user, "riya@safecircle.demo")
    _login(guardian, "priya@safecircle.demo")

    page = guardian.get("/guardian/dashboard").data
    assert b'data-unread="0"' in page

    r = user.post("/demo/emergency", data={"preset": "raj_nagar"})
    assert r.status_code == 302
    assert EmergencyRequest.query.count() == 1

    page = guardian.get("/guardian/dashboard").data
    assert b'data-unread="1"' in page                       # bell badge data a live poll reads
    assert b"New emergency request" in page                 # toast text
    assert b"Accept" in page

    tracker = user.get("/dashboard").data
    assert b"Waiting for a guardian to respond" in tracker
    assert b"Cancel this request" in tracker


def test_only_one_open_request_per_user(app):
    seed()
    user = app.test_client()
    _login(user, "riya@safecircle.demo")
    user.post("/demo/emergency", data={"preset": "raj_nagar"})
    user.post("/demo/emergency", data={"preset": "raj_nagar"})
    assert EmergencyRequest.query.count() == 1


def test_demo_emergency_rejects_unknown_location_and_wrong_role(app):
    seed()
    user, guardian = app.test_client(), app.test_client()
    _login(user, "riya@safecircle.demo")
    user.post("/demo/emergency", data={"preset": "../../etc"})
    assert EmergencyRequest.query.count() == 0
    _login(guardian, "priya@safecircle.demo")
    assert guardian.post("/demo/emergency", data={"preset": "raj_nagar"}).status_code == 403


def test_cancel_removes_request_from_guardians_and_checks_owner(app):
    seed()
    owner, other, guardian = app.test_client(), app.test_client(), app.test_client()
    _login(owner, "riya@safecircle.demo")
    _login(other, "ananya@safecircle.demo")
    _login(guardian, "priya@safecircle.demo")
    owner.post("/demo/emergency", data={"preset": "raj_nagar"})
    req = EmergencyRequest.query.first()

    assert other.post(f"/demo/requests/{req.id}/cancel").status_code == 404   # not their request
    assert EmergencyRequest.query.first().status == "pending"

    assert owner.post(f"/demo/requests/{req.id}/cancel").status_code == 302
    assert EmergencyRequest.query.first().status == "cancelled"
    assert f"Request #{req.id}".encode() not in guardian.get("/guardian/dashboard").data.split(b"Duty status")[0].split(b"Incoming requests")[1]
    assert Notification.query.filter_by(type="request_cancelled").count() >= 1


def test_cannot_cancel_after_a_guardian_accepts(app):
    seed()
    owner, guardian = app.test_client(), app.test_client()
    _login(owner, "riya@safecircle.demo")
    _login(guardian, "priya@safecircle.demo")
    owner.post("/demo/emergency", data={"preset": "raj_nagar"})
    req = EmergencyRequest.query.first()
    guardian.post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"})
    owner.post(f"/demo/requests/{req.id}/cancel")
    assert EmergencyRequest.query.first().status == "accepted"
    assert b"Priya Verma" in owner.get("/dashboard").data     # tracker shows who accepted


def test_guardian_going_on_duty_later_still_gets_open_requests(app, make_user):
    """The reported bug: a new guardian who sets location + goes on duty AFTER an alert saw nothing."""
    from models import GuardianProfile, utcnow
    from extensions import db
    seed()
    user = app.test_client()
    _login(user, "riya@safecircle.demo")
    user.post("/demo/emergency", data={"preset": "raj_nagar"})

    g = make_user("newguard@example.com", role="guardian", name="New Guardian")
    db.session.add(GuardianProfile(user_id=g.id, status="approved", approved_at=utcnow(),
                                   organisation="Test", id_proof_note="college card", on_duty=False))
    db.session.commit()
    gc = app.test_client()
    assert gc.post("/login", data={"email": "newguard@example.com", "password": "Secret@123"}).status_code == 302

    body = gc.get("/guardian/dashboard").data
    assert b"You are not receiving requests yet" in body          # clear warning, not silence
    assert b">Accept</button>" not in body

    gc.post("/guardian/location", data={"preset": "raj_nagar"})
    gc.post("/guardian/duty")
    body = gc.get("/guardian/dashboard").data
    assert b"You are not receiving requests yet" not in body
    assert b"Incoming requests (1)" in body and b">Accept</button>" in body


def test_fresh_start_creates_tables_without_init_db(tmp_path):
    """A teammate who clones the repo and forgets `flask init-db` must not get 'no such table'."""
    from app import create_app
    from config import Config
    from models import User

    class FreshConfig(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
        WTF_CSRF_ENABLED = False

    fresh = create_app(FreshConfig)
    with fresh.app_context():
        assert User.query.count() == 0
    c = fresh.test_client()
    assert c.get("/").status_code == 200
    assert c.post("/login", data={"email": "a@b.com", "password": "x"}).status_code == 401  # normal "wrong login", not a 500 crash
