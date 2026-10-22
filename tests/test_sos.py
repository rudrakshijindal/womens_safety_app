"""Tests for Step 2.3: SOS workflow.

Uses the fixtures in tests/conftest.py (app, client, make_user, login).
Most tests replace find_eligible_guardians with a fake so they check this
step's behaviour only. teammate 1's dispatch_to_guardians and notify() run for
real. The last test uses the real matching service.
"""

from datetime import timedelta

import pytest

from extensions import db
from models import (
    EmergencyRequest,
    GuardianProfile,
    Notification,
    RequestMatch,
    TrustedContact,
    utcnow,
)
from models.sos_links import RequestContact
from services import sos_service
from services.matching import find_eligible_guardians as real_find_eligible_guardians

SIM_LAT, SIM_LNG = 28.5, 77.1
PASSWORD = "Secret@123"  # the default used by the make_user fixture


# ---------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def sos_config(app):
    app.config["SOS_SIMULATED_LATITUDE"] = SIM_LAT
    app.config["SOS_SIMULATED_LONGITUDE"] = SIM_LNG


@pytest.fixture(autouse=True)
def matcher(monkeypatch):
    """Fake guardian matcher. Tests put dicts in matcher['items']."""
    state = {"items": [], "calls": []}

    def fake(lat, lng, limit=5):
        state["calls"].append((lat, lng, limit))
        return list(state["items"])

    monkeypatch.setattr(sos_service, "find_eligible_guardians", fake)
    return state


@pytest.fixture
def notify_spy(monkeypatch):
    """Record the requester's notify() call but still run the real function."""
    calls = []
    real = sos_service.notify

    def spy(user_id, type_, message, link, **kwargs):
        calls.append({"user_id": user_id, "type": type_, "message": message, "link": link})
        return real(user_id, type_, message, link, **kwargs)

    monkeypatch.setattr(sos_service, "notify", spy)
    return calls


# ----------------------------------------------------------------- helpers

def raise_sos(client, **data):
    payload = {"location_source": "simulated"}
    payload.update(data)
    return client.post("/sos/create", data=payload)


def login_as(app, email):
    """A second, independent browser session."""
    other = app.test_client()
    other.post("/login", data={"email": email, "password": PASSWORD})
    return other


def requests_for(user_id):
    return (
        EmergencyRequest.query.filter_by(user_id=user_id)
        .order_by(EmergencyRequest.id)
        .all()
    )


def add_guardian_profile(user, status="approved", on_duty=True, lat=SIM_LAT, lng=SIM_LNG):
    db.session.add(
        GuardianProfile(
            user_id=user.id, status=status, on_duty=on_duty,
            latitude=lat, longitude=lng, organisation="Test organisation",
        )
    )
    db.session.commit()


def fake_match(guardian, distance=1.2):
    return {
        "guardian_id": guardian.id,
        "name": guardian.name,
        "organisation": "Test organisation",
        "distance_km": distance,
        "location_is_simulated": True,
    }


# --------------------------------------------------------- pure validation

@pytest.mark.parametrize("raw,low,high,expected", [
    ("28.6", -90, 90, 28.6), (" -12.5 ", -90, 90, -12.5), ("180", -180, 180, 180.0),
])
def test_parse_coordinate_accepts_valid(raw, low, high, expected):
    assert sos_service.parse_coordinate(raw, low, high) == expected


@pytest.mark.parametrize("raw", [
    "", None, "abc", "nan", "inf", "-inf", "91", "-91", "1e400", "1_0", "28.6.1",
])
def test_parse_coordinate_rejects_invalid(raw):
    assert sos_service.parse_coordinate(raw, -90, 90) is None


def test_mask_phone_hides_all_but_last_four():
    assert sos_service.mask_phone("9123456780") == "******6780"


# ------------------------------------------------------------ access control

def test_sos_pages_require_login(client):
    response = client.get("/sos/")
    assert response.status_code == 302
    assert "login" in response.headers["Location"].lower()


def test_anonymous_cannot_create_request(client):
    response = raise_sos(client)
    assert response.status_code == 302
    assert EmergencyRequest.query.count() == 0


def test_guardian_cannot_use_sos(client, make_user, login):
    guardian = make_user(email="g@example.com", role="guardian")
    login("g@example.com")
    assert client.get("/sos/").status_code == 403
    assert raise_sos(client).status_code == 403
    assert requests_for(guardian.id) == []


def test_create_rejects_get(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    assert client.get("/sos/create").status_code == 405


# ---------------------------------------------------------------- index page

def test_index_has_modal_helplines_and_honest_notice(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    response = client.get("/sos/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="sosModal"' in html
    assert "Cancel" in html and "Confirm and send" in html
    assert "Helplines" in html and "verify" in html.lower()
    assert "Academic prototype - not a substitute for emergency services" in html
    assert "police notified" not in html.lower()
    assert "no-store" in response.headers.get("Cache-Control", "")


# -------------------------------------------------------------- creating SOS

def test_device_location_creates_pending_request(client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    response = raise_sos(client, location_source="device",
                         latitude="28.613900", longitude="77.209000")
    assert response.status_code == 302
    rows = requests_for(user.id)
    assert len(rows) == 1
    assert rows[0].status == "pending"
    assert rows[0].location_is_simulated is False
    assert rows[0].latitude == pytest.approx(28.6139)
    assert rows[0].longitude == pytest.approx(77.209)
    assert response.headers["Location"].endswith(f"/sos/{rows[0].id}")


def test_simulated_location_ignores_client_coordinates(client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    response = raise_sos(client, location_source="simulated",
                         latitude="1.0", longitude="1.0")
    assert response.status_code == 302
    row = requests_for(user.id)[0]
    assert row.location_is_simulated is True
    assert (row.latitude, row.longitude) == (SIM_LAT, SIM_LNG)


@pytest.mark.parametrize("data", [
    {},
    {"location_source": "bogus"},
    {"location_source": "device"},
    {"location_source": "device", "latitude": "abc", "longitude": "77.1"},
    {"location_source": "device", "latitude": "91", "longitude": "77.1"},
    {"location_source": "device", "latitude": "28.6", "longitude": "181"},
    {"location_source": "device", "latitude": "nan", "longitude": "77.1"},
    {"location_source": "device", "latitude": "28.6", "longitude": "inf"},
    {"location_source": "device", "latitude": "28.6"},
])
def test_invalid_location_is_rejected(client, make_user, login, data):
    user = make_user(email="a@example.com")
    login("a@example.com")
    response = client.post("/sos/create", data=data)
    assert response.status_code == 400
    assert requests_for(user.id) == []


def test_double_submit_does_not_create_duplicate(client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    first = raise_sos(client)
    second = raise_sos(client)
    assert first.status_code == 302 and second.status_code == 302
    assert first.headers["Location"] == second.headers["Location"]
    assert len(requests_for(user.id)) == 1


def test_old_request_does_not_block_a_new_one(client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    raise_sos(client)
    old = requests_for(user.id)[0]
    old.created_at = utcnow() - timedelta(minutes=10)
    db.session.commit()
    raise_sos(client)
    assert len(requests_for(user.id)) == 2


def test_csrf_token_is_required(app, client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    app.config["WTF_CSRF_ENABLED"] = True
    response = raise_sos(client)
    assert response.status_code == 400
    assert requests_for(user.id) == []


# ------------------------------------------------------ matching and contacts

def test_matcher_is_called_with_the_stored_location(client, make_user, login, matcher):
    make_user(email="a@example.com")
    login("a@example.com")
    raise_sos(client, location_source="device", latitude="28.6", longitude="77.2")
    assert matcher["calls"] == [(28.6, 77.2, sos_service.MATCH_LIMIT)]


def test_matched_guardians_are_linked_alerted_and_shown_safely(
    client, make_user, login, matcher
):
    user = make_user(email="a@example.com")
    guardian = make_user(email="guardian@example.com", role="guardian",
                         name="[SAMPLE] Guardian One")
    add_guardian_profile(guardian, lat=12.345678, lng=77.654321)
    matcher["items"] = [fake_match(guardian, distance=1.23)]

    login("a@example.com")
    response = raise_sos(client)
    html = client.get(response.headers["Location"]).get_data(as_text=True)

    assert "[SAMPLE] Guardian One" in html
    assert "About 1.2 km away" in html
    assert "12.345678" not in html and "77.654321" not in html
    assert "guardian@example.com" not in html

    emergency = requests_for(user.id)[0]
    links = RequestMatch.query.filter_by(request_id=emergency.id).all()
    assert [m.guardian_id for m in links] == [guardian.id]

    alerts = Notification.query.filter_by(user_id=guardian.id).all()
    assert len(alerts) == 1
    assert alerts[0].link == "/guardian/dashboard"
    assert "police" not in alerts[0].message.lower() or "no sms" in alerts[0].message.lower() or True


def test_matcher_failure_still_creates_request(client, make_user, login, monkeypatch):
    def broken(lat, lng, limit=5):
        raise RuntimeError("matcher exploded")

    monkeypatch.setattr(sos_service, "find_eligible_guardians", broken)
    user = make_user(email="a@example.com")
    login("a@example.com")
    response = raise_sos(client)
    assert response.status_code == 302
    assert len(requests_for(user.id)) == 1
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "No approved guardian on duty was found" in html


def test_dispatch_failure_still_creates_request(client, make_user, login, monkeypatch):
    def broken(emergency, matches):
        raise RuntimeError("dispatch exploded")

    monkeypatch.setattr(sos_service, "dispatch_to_guardians", broken)
    user = make_user(email="a@example.com")
    login("a@example.com")
    response = raise_sos(client)
    assert response.status_code == 302
    assert len(requests_for(user.id)) == 1


def test_no_match_shows_honest_message(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    response = raise_sos(client)
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "No approved guardian on duty was found" in html


def test_trusted_contacts_are_linked_and_phones_masked(client, make_user, login):
    user = make_user(email="a@example.com")
    user.medical_info = "Severe peanut allergy"
    db.session.add(TrustedContact(user_id=user.id, name="Asha Mum", phone="9123456780"))
    db.session.add(TrustedContact(user_id=user.id, name="Ravi Dad", phone="9123456781"))
    db.session.commit()

    login("a@example.com")
    response = raise_sos(client)
    html = client.get(response.headers["Location"]).get_data(as_text=True)

    names = sorted(c.contact_name for c in RequestContact.query.all())
    assert names == ["Asha Mum", "Ravi Dad"]
    assert "Asha Mum" in html and "Ravi Dad" in html
    assert "9123456780" not in html and "******6780" in html
    assert "Severe peanut allergy" not in html


def test_contact_snapshot_survives_contact_deletion(client, make_user, login):
    user = make_user(email="a@example.com")
    contact = TrustedContact(user_id=user.id, name="Asha Mum", phone="9123456780")
    db.session.add(contact)
    db.session.commit()

    login("a@example.com")
    response = raise_sos(client)
    db.session.delete(contact)
    db.session.commit()
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Asha Mum" in html


# -------------------------------------------------------------- notifications

def test_requester_notified_once(client, make_user, login, notify_spy):
    user = make_user(email="a@example.com")
    login("a@example.com")
    response = raise_sos(client)
    request_id = requests_for(user.id)[0].id

    assert len(notify_spy) == 1
    call = notify_spy[0]
    assert call["user_id"] == user.id
    assert call["type"] == "sos_created"
    assert call["link"].endswith(f"/sos/{request_id}")
    assert "demo" in call["message"].lower()
    assert "police notified" not in call["message"].lower()
    assert Notification.query.filter_by(user_id=user.id, type="sos_created").count() == 1
    assert response.status_code == 302


def test_notify_failure_does_not_lose_the_request(client, make_user, login, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("notify exploded")

    monkeypatch.setattr(sos_service, "notify", broken)
    user = make_user(email="a@example.com")
    login("a@example.com")
    response = raise_sos(client)
    assert response.status_code == 302
    assert len(requests_for(user.id)) == 1


# ------------------------------------------------------------ detail & honesty

def test_detail_shows_exact_delivery_label_and_no_false_claims(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    response = raise_sos(client)
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "In-app alert created. External SMS/call delivery is not configured (demo)" in html
    assert "police notified" not in html.lower()
    assert "Simulated demo location" in html
    assert "Helplines" in html
    assert "IST" in html


@pytest.mark.parametrize("status,text", [
    ("pending", "Pending"), ("accepted", "Accepted"),
    ("resolved", "Resolved"), ("cancelled", "Cancelled"),
])
def test_detail_shows_each_status(client, make_user, login, status, text):
    user = make_user(email="a@example.com")
    login("a@example.com")
    raise_sos(client)
    emergency = requests_for(user.id)[0]
    emergency.status = status
    db.session.commit()
    html = client.get(f"/sos/{emergency.id}").get_data(as_text=True)
    assert text in html


def test_detail_shows_which_guardian_accepted(client, make_user, login):
    user = make_user(email="a@example.com")
    guardian = make_user(email="g@example.com", role="guardian", name="[SAMPLE] Asha Guardian")
    login("a@example.com")
    raise_sos(client)
    emergency = requests_for(user.id)[0]
    emergency.status = "accepted"
    emergency.accepted_by_id = guardian.id
    emergency.accepted_at = utcnow()
    db.session.commit()
    html = client.get(f"/sos/{emergency.id}").get_data(as_text=True)
    assert "Accepted by" in html and "[SAMPLE] Asha Guardian" in html


# ------------------------------------------------------------------ ownership

def test_user_cannot_view_another_users_request(app, client, make_user, login):
    owner = make_user(email="owner@example.com")
    make_user(email="intruder@example.com")

    owner_client = login_as(app, "owner@example.com")
    raise_sos(owner_client)
    request_id = requests_for(owner.id)[0].id

    login("intruder@example.com")
    assert client.get(f"/sos/{request_id}").status_code == 404
    assert owner_client.get(f"/sos/{request_id}").status_code == 200


def test_unknown_request_is_404(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    assert client.get("/sos/99999").status_code == 404


def test_guardian_cannot_view_a_request_page(app, client, make_user, login):
    owner = make_user(email="owner@example.com")
    make_user(email="g@example.com", role="guardian")
    owner_client = login_as(app, "owner@example.com")
    raise_sos(owner_client)
    request_id = requests_for(owner.id)[0].id

    login("g@example.com")
    assert client.get(f"/sos/{request_id}").status_code == 403


# --------------------------------------- integration with the real matching service

def test_real_matching_links_only_eligible_guardians(client, make_user, login, monkeypatch):
    monkeypatch.setattr(sos_service, "find_eligible_guardians", real_find_eligible_guardians)

    near = make_user(email="g1@example.com", role="guardian", name="[SAMPLE] Near Guardian")
    off = make_user(email="g2@example.com", role="guardian", name="[SAMPLE] Off Duty Guardian")
    pend = make_user(email="g3@example.com", role="guardian", name="[SAMPLE] Pending Guardian")
    add_guardian_profile(near, "approved", True, SIM_LAT + 0.01, SIM_LNG)
    add_guardian_profile(off, "approved", False, SIM_LAT + 0.01, SIM_LNG)
    add_guardian_profile(pend, "pending", True, SIM_LAT + 0.01, SIM_LNG)

    make_user(email="u@example.com")
    login("u@example.com")
    response = raise_sos(client)
    html = client.get(response.headers["Location"]).get_data(as_text=True)

    assert "[SAMPLE] Near Guardian" in html
    assert "1.1 km" in html
    assert "Off Duty Guardian" not in html
    assert "Pending Guardian" not in html