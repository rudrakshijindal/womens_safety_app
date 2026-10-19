import pytest

from extensions import db
from models import EmergencyRequest, GuardianProfile, GuardianResponse, Notification, RequestMatch, User
from services import admin_service, guardian_service
from services.matching import dispatch_to_guardians, find_eligible_guardians

LAT, LNG = 28.6700, 77.4450  # Raj Nagar


@pytest.fixture
def make_guardian(make_user):
    counter = {"n": 0}

    def _make(status="approved", on_duty=True, lat=LAT, lng=LNG, name=None):
        counter["n"] += 1
        user = make_user(f"g{counter['n']}@example.com", role="guardian", name=name or f"Guardian {counter['n']}")
        db.session.add(
            GuardianProfile(
                user_id=user.id, organisation="NGO", id_proof_note="Aadhaar 1234",
                status=status, on_duty=on_duty, latitude=lat, longitude=lng,
            )
        )
        db.session.commit()
        return user

    return _make


def raise_request(user, guardians_lat=LAT, guardians_lng=LNG, limit=5):
    req = EmergencyRequest(user_id=user.id, latitude=guardians_lat, longitude=guardians_lng, location_is_simulated=True)
    db.session.add(req)
    db.session.commit()
    matches = find_eligible_guardians(req.latitude, req.longitude, limit=limit)
    dispatch_to_guardians(req, matches)
    return req


def login_as(app, email):
    c = app.test_client()
    c.post("/login", data={"email": email, "password": "Secret@123"})
    return c


# ---------- dispatch ----------

def test_dispatch_links_and_notifies_matched_guardians(make_user, make_guardian):
    user = make_user("requester@example.com")
    near = make_guardian(name="Near")
    off = make_guardian(name="Off", on_duty=False)
    req = raise_request(user)

    matched_ids = {m.guardian_id for m in RequestMatch.query.filter_by(request_id=req.id)}
    assert matched_ids == {near.id}
    assert Notification.query.filter_by(user_id=near.id, type="emergency_request").count() == 1
    assert Notification.query.filter_by(user_id=off.id).count() == 0


# ---------- accept / reject ----------

def test_guardian_accepts_request(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    guardian = make_guardian()
    req = raise_request(user)

    client = login_as(app, guardian.email)
    html = client.get("/guardian/dashboard").get_data(as_text=True)
    assert f"#{req.id}" in html and "Accept" in html

    response = client.post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"})
    assert response.status_code == 302

    db.session.refresh(req)
    assert req.status == "accepted"
    assert req.accepted_by_id == guardian.id
    assert req.accepted_at is not None
    answer = GuardianResponse.query.filter_by(request_id=req.id, guardian_id=guardian.id).one()
    assert answer.action == "accepted"
    note = Notification.query.filter_by(user_id=user.id, type="request_accepted").one()
    assert guardian.name in note.message

    # requester details appear only after accepting
    page = client.get("/guardian/dashboard").get_data(as_text=True)
    assert "Active request" in page and user.name in page


def test_requester_details_hidden_before_accepting(app, make_user, make_guardian):
    user = make_user("secret@example.com", name="Hidden Person")
    guardian = make_guardian()
    raise_request(user)
    page = login_as(app, guardian.email).get("/guardian/dashboard").get_data(as_text=True)
    assert "Hidden Person" not in page


def test_reject_keeps_request_open_for_others(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    first = make_guardian(name="First")
    second = make_guardian(name="Second")
    req = raise_request(user)

    login_as(app, first.email).post(f"/guardian/requests/{req.id}/respond", data={"action": "reject"})
    db.session.refresh(req)
    assert req.status == "pending"
    assert GuardianResponse.query.filter_by(request_id=req.id, guardian_id=first.id).one().action == "rejected"

    # the rejecting guardian no longer sees it; the other still does
    assert f"#{req.id}" not in login_as(app, first.email).get("/guardian/dashboard").get_data(as_text=True).split("Incoming requests")[1].split("Duty status")[0]
    login_as(app, second.email).post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"})
    db.session.refresh(req)
    assert req.accepted_by_id == second.id


def test_only_one_guardian_can_accept(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    first = make_guardian(name="First")
    second = make_guardian(name="Second")
    req = raise_request(user)

    login_as(app, first.email).post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"})
    response = login_as(app, second.email).post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"}, follow_redirects=True)
    assert b"no longer open" in response.data

    db.session.refresh(req)
    assert req.accepted_by_id == first.id
    assert GuardianResponse.query.filter_by(request_id=req.id, guardian_id=second.id).count() == 0


def test_guardian_cannot_respond_twice(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    guardian = make_guardian()
    req = raise_request(user)
    client = login_as(app, guardian.email)
    client.post(f"/guardian/requests/{req.id}/respond", data={"action": "reject"})
    response = client.post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"}, follow_redirects=True)
    assert b"already responded" in response.data
    db.session.refresh(req)
    assert req.status == "pending"


def test_unmatched_guardian_gets_403(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    matched = make_guardian(name="Matched")
    outsider = make_guardian(name="Far away", lat=19.0760, lng=72.8777, on_duty=False)
    req = raise_request(user)

    response = login_as(app, outsider.email).post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"})
    assert response.status_code == 403
    db.session.refresh(req)
    assert req.status == "pending"


def test_pending_guardian_and_plain_user_cannot_respond(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    make_guardian()
    req = raise_request(user)
    pending = make_guardian(status="pending", on_duty=False)
    assert login_as(app, pending.email).post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"}).status_code == 302
    assert login_as(app, user.email).post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"}).status_code == 403
    db.session.refresh(req)
    assert req.status == "pending"


def test_invalid_action_is_rejected(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    guardian = make_guardian()
    req = raise_request(user)
    response = login_as(app, guardian.email).post(f"/guardian/requests/{req.id}/respond", data={"action": "hack"})
    assert response.status_code == 400


# ---------- resolve + metrics ----------

def test_only_accepting_guardian_can_resolve(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    first = make_guardian(name="First")
    second = make_guardian(name="Second")
    req = raise_request(user)
    c1, c2 = login_as(app, first.email), login_as(app, second.email)
    c1.post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"})

    assert c2.post(f"/guardian/requests/{req.id}/resolve").status_code == 403
    db.session.refresh(req)
    assert req.status == "accepted"

    assert c1.post(f"/guardian/requests/{req.id}/resolve").status_code == 302
    db.session.refresh(req)
    assert req.status == "resolved"
    assert req.resolved_at is not None
    assert Notification.query.filter_by(user_id=user.id, type="request_resolved").count() == 1
    assert c1.post(f"/guardian/requests/{req.id}/resolve").status_code == 403  # cannot resolve twice


def test_metrics_use_real_timestamps(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    guardian = make_guardian()
    req = raise_request(user)
    client = login_as(app, guardian.email)
    client.post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"})
    client.post(f"/guardian/requests/{req.id}/resolve")

    m = guardian_service.metrics(guardian.id)
    assert m["accepted"] == 1 and m["rejected"] == 0 and m["resolved"] == 1
    assert m["avg_response_min"] is not None and m["avg_response_min"] < 1


def test_metrics_empty_for_new_guardian(make_guardian):
    guardian = make_guardian()
    assert guardian_service.metrics(guardian.id) == {"accepted": 0, "rejected": 0, "resolved": 0, "avg_response_min": None}


# ---------- admin: demo emergency and analytics ----------

def test_admin_creates_demo_emergency(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    near = make_guardian(name="Near")
    make_user("boss@example.com", role="admin", name="Admin")
    admin = login_as(app, "boss@example.com")

    response = admin.post("/admin/demo-emergency", data={"user_id": user.id, "preset": "raj_nagar"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Matched nearest first" in response.data

    req = EmergencyRequest.query.one()
    assert req.user_id == user.id and req.location_is_simulated is True
    assert RequestMatch.query.filter_by(request_id=req.id, guardian_id=near.id).count() == 1
    assert Notification.query.filter_by(user_id=user.id, type="request_created").count() == 1


def test_demo_emergency_with_nobody_on_duty(app, make_user):
    user = make_user("requester@example.com")
    make_user("boss@example.com", role="admin", name="Admin")
    admin = login_as(app, "boss@example.com")
    response = admin.post("/admin/demo-emergency", data={"user_id": user.id, "preset": "raj_nagar"}, follow_redirects=True)
    assert b"no guardian is on duty" in response.data


def test_demo_emergency_rejects_bad_input(app, make_user):
    user = make_user("requester@example.com")
    make_user("boss@example.com", role="admin", name="Admin")
    admin = login_as(app, "boss@example.com")
    admin.post("/admin/demo-emergency", data={"user_id": "abc", "preset": "raj_nagar"})
    admin.post("/admin/demo-emergency", data={"user_id": user.id, "preset": "nowhere"})
    admin.post("/admin/demo-emergency", data={"user_id": 9999, "preset": "raj_nagar"})
    assert EmergencyRequest.query.count() == 0


def test_demo_emergency_is_admin_only(app, make_user):
    user = make_user("requester@example.com")
    client = login_as(app, user.email)
    assert client.post("/admin/demo-emergency", data={"user_id": user.id, "preset": "raj_nagar"}).status_code == 403
    assert client.get("/admin/requests").status_code == 403
    assert client.get("/admin/users").status_code == 403
    assert EmergencyRequest.query.count() == 0


def test_admin_counts_match_the_database(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    make_guardian(name="One")
    make_guardian(name="Two")
    make_guardian(status="pending", on_duty=False)
    r1 = raise_request(user)
    raise_request(user)
    login_as(app, "g1@example.com").post(f"/guardian/requests/{r1.id}/respond", data={"action": "accept"})

    s = admin_service.stats()
    assert s["users"] == 1
    assert s["approved_guardians"] == 2 and s["pending_guardians"] == 1 and s["on_duty_guardians"] == 2
    assert s["requests"] == 2
    assert s["by_status"] == {"pending": 1, "accepted": 1, "resolved": 0, "cancelled": 0}
    assert s["avg_accept_min"] is not None and s["avg_resolve_min"] is None


def test_admin_pages_render_with_data(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    make_guardian(name="One")
    raise_request(user)
    make_user("boss@example.com", role="admin", name="Admin")
    admin = login_as(app, "boss@example.com")
    for url in ("/admin/", "/admin/requests", "/admin/users", "/admin/guardians", "/admin/applications"):
        assert admin.get(url).status_code == 200, url
    assert b"One" in admin.get("/admin/requests").data


def test_user_sees_status_and_guardian_name(app, make_user, make_guardian):
    user = make_user("requester@example.com")
    guardian = make_guardian(name="Helpful Guardian")
    req = raise_request(user)
    login_as(app, guardian.email).post(f"/guardian/requests/{req.id}/respond", data={"action": "accept"})
    page = login_as(app, user.email).get("/dashboard").get_data(as_text=True)
    assert "status-accepted" in page and "Helpful Guardian" in page
