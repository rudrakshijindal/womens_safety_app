"""Tests for Step 2.4: Safe Journey.

Uses the fixtures in tests/conftest.py (app, client, make_user, login).
Leaflet and the map tiles load in the browser, so these tests check the page
markup and data attributes, not the map itself.
"""

from datetime import timedelta

import pytest

from extensions import db
from models import Notification, SafeJourney, utcnow
from models.journey_links import JourneyStartInfo
from services import journey_service

SIM_LAT, SIM_LNG = 28.5, 77.1
PASSWORD = "Secret@123"  # the default used by the make_user fixture
NOTE = (
    "Location updates only while this page is open; "
    "background tracking is not supported by browsers."
)


# ---------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def sim_config(app):
    app.config["SOS_SIMULATED_LATITUDE"] = SIM_LAT
    app.config["SOS_SIMULATED_LONGITUDE"] = SIM_LNG


@pytest.fixture
def notify_spy(monkeypatch):
    """Record notify() calls but still run the real function."""
    calls = []
    real = journey_service.notify

    def spy(user_id, type_, message, link, **kwargs):
        calls.append({"user_id": user_id, "type": type_, "message": message, "link": link})
        return real(user_id, type_, message, link, **kwargs)

    monkeypatch.setattr(journey_service, "notify", spy)
    return calls


# ----------------------------------------------------------------- helpers

def start(client, **data):
    payload = {"destination": "Karnal Bus Stand", "location_source": "simulated"}
    payload.update(data)
    return client.post("/journey/start", data=payload)


def login_as(app, email):
    """A second, independent browser session."""
    other = app.test_client()
    other.post("/login", data={"email": email, "password": PASSWORD})
    return other


def journeys_for(user_id):
    return (
        SafeJourney.query.filter_by(user_id=user_id)
        .order_by(SafeJourney.id)
        .all()
    )


def make_journey(user, destination="Karnal Bus Stand", status="active",
                 lat=SIM_LAT, lng=SIM_LNG, simulated=True, with_info=True,
                 minutes_ago=30):
    started = utcnow() - timedelta(minutes=minutes_ago)
    journey = SafeJourney(
        user_id=user.id, destination=destination, start_lat=lat, start_lng=lng,
        status=status, started_at=started,
    )
    if status == "completed":
        journey.ended_at = started + timedelta(minutes=20)
    db.session.add(journey)
    db.session.flush()
    if with_info:
        db.session.add(JourneyStartInfo(journey_id=journey.id, location_is_simulated=simulated))
    db.session.commit()
    return journey


# --------------------------------------------------------- pure validation

@pytest.mark.parametrize("raw,expected", [
    ("Karnal Bus Stand", "Karnal Bus Stand"),
    ("  Sector   14,  Karnal ", "Sector 14, Karnal"),
    ("Gate #2 (north)", "Gate #2 (north)"),
    ("मेरा घर", "मेरा घर"),
])
def test_validate_destination_accepts_reasonable_input(raw, expected):
    text, error = journey_service.validate_destination(raw)
    assert error is None and text == expected


@pytest.mark.parametrize("raw", ["", None, "   ", "a", "x" * 201, "\x00bad", "!!!", ".."])
def test_validate_destination_rejects_bad_input(raw):
    _, error = journey_service.validate_destination(raw)
    assert error is not None


@pytest.mark.parametrize("raw", ["", None, "Meeting a friend", "Line one\nLine two"])
def test_validate_description_accepts(raw):
    _, error = journey_service.validate_description(raw)
    assert error is None


@pytest.mark.parametrize("raw", ["x" * 501, "bad\x00text"])
def test_validate_description_rejects(raw):
    _, error = journey_service.validate_description(raw)
    assert error is not None


@pytest.mark.parametrize("delta,expected", [
    (timedelta(seconds=20), "less than a minute"),
    (timedelta(minutes=5), "5 min"),
    (timedelta(minutes=60), "1 h"),
    (timedelta(minutes=65), "1 h 5 min"),
    (timedelta(hours=26), "1 d 2 h"),
    (timedelta(seconds=-30), "less than a minute"),
])
def test_format_duration(delta, expected):
    assert journey_service.format_duration(delta) == expected


# ------------------------------------------------------------ access control

def test_journey_pages_require_login(client):
    response = client.get("/journey/")
    assert response.status_code == 302
    assert "login" in response.headers["Location"].lower()


def test_anonymous_cannot_start_a_journey(client):
    response = start(client)
    assert response.status_code == 302
    assert SafeJourney.query.count() == 0


def test_guardian_cannot_use_journeys(client, make_user, login):
    guardian = make_user(email="g@example.com", role="guardian")
    login("g@example.com")
    assert client.get("/journey/").status_code == 403
    assert client.get("/journey/history").status_code == 403
    assert start(client).status_code == 403
    assert journeys_for(guardian.id) == []


def test_start_and_end_reject_get(client, make_user, login):
    user = make_user(email="a@example.com")
    journey = make_journey(user)
    login("a@example.com")
    assert client.get("/journey/start").status_code == 405
    assert client.get(f"/journey/{journey.id}/end").status_code == 405


# ---------------------------------------------------------------- index page

def test_index_has_labelled_form_note_and_honest_status(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    response = client.get("/journey/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="journey-form"' in html
    assert 'for="destination"' in html and 'for="description"' in html
    assert 'name="csrf_token"' in html
    assert NOTE in html
    assert "no SMS or call is sent" in html
    assert "police notified" not in html.lower()
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_index_shows_active_journey_instead_of_the_form(client, make_user, login):
    user = make_user(email="a@example.com")
    journey = make_journey(user, destination="Active Trip Two")
    login("a@example.com")
    html = client.get("/journey/").get_data(as_text=True)
    assert "Journey in progress" in html and "Active Trip Two" in html
    assert f"/journey/{journey.id}" in html
    assert 'id="journey-form"' not in html


# ------------------------------------------------------------ starting a journey

def test_device_location_creates_active_journey(client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    response = start(client, location_source="device", latitude="28.613900",
                     longitude="77.209000", description="Going to a friend")
    rows = journeys_for(user.id)
    assert response.status_code == 302 and len(rows) == 1
    journey = rows[0]
    assert journey.status == "active"
    assert journey.destination == "Karnal Bus Stand"
    assert journey.description == "Going to a friend"
    assert journey.start_lat == pytest.approx(28.6139)
    assert journey.start_lng == pytest.approx(77.209)
    assert journey.started_at is not None and journey.ended_at is None
    assert journey.start_info.location_is_simulated is False
    assert response.headers["Location"].endswith(f"/journey/{journey.id}")


def test_simulated_location_ignores_client_coordinates(client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    start(client, location_source="simulated", latitude="1.0", longitude="1.0")
    journey = journeys_for(user.id)[0]
    assert (journey.start_lat, journey.start_lng) == (SIM_LAT, SIM_LNG)
    assert journey.start_info.location_is_simulated is True


def test_description_is_optional(client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    assert start(client).status_code == 302
    assert journeys_for(user.id)[0].description is None


@pytest.mark.parametrize("destination", ["", "   ", "a", "x" * 201, "\x00bad", "!!!"])
def test_invalid_destination_is_rejected(client, make_user, login, destination):
    user = make_user(email="a@example.com")
    login("a@example.com")
    response = start(client, destination=destination)
    assert response.status_code == 400
    assert journeys_for(user.id) == []


def test_overlong_description_is_rejected(client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    assert start(client, description="x" * 501).status_code == 400
    assert journeys_for(user.id) == []


@pytest.mark.parametrize("data", [
    {"location_source": ""},
    {"location_source": "bogus"},
    {"location_source": "device"},
    {"location_source": "device", "latitude": "abc", "longitude": "77.1"},
    {"location_source": "device", "latitude": "91", "longitude": "77.1"},
    {"location_source": "device", "latitude": "28.6", "longitude": "181"},
    {"location_source": "device", "latitude": "nan", "longitude": "77.1"},
    {"location_source": "device", "latitude": "28.6"},
])
def test_invalid_location_is_rejected(client, make_user, login, data):
    user = make_user(email="a@example.com")
    login("a@example.com")
    response = start(client, **data)
    assert response.status_code == 400
    assert journeys_for(user.id) == []
    assert Notification.query.filter_by(user_id=user.id).count() == 0


def test_second_start_returns_the_active_journey(client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    first = start(client)
    second = start(client, destination="Somewhere Else")
    assert first.headers["Location"] == second.headers["Location"]
    assert len(journeys_for(user.id)) == 1


def test_completed_journey_does_not_block_a_new_one(client, make_user, login):
    user = make_user(email="a@example.com")
    make_journey(user, status="completed")
    login("a@example.com")
    assert start(client).status_code == 302
    assert len(journeys_for(user.id)) == 2


def test_csrf_token_is_required(app, client, make_user, login):
    user = make_user(email="a@example.com")
    login("a@example.com")
    app.config["WTF_CSRF_ENABLED"] = True
    assert start(client).status_code == 400
    assert journeys_for(user.id) == []


def test_user_text_is_escaped_on_the_page(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    response = start(client, destination="<script>alert(1)</script>",
                     description="<b>bold</b> text")
    html = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>bold</b>" not in html


# -------------------------------------------------------------- notifications

def test_start_notifies_the_user_honestly(client, make_user, login, notify_spy):
    user = make_user(email="a@example.com")
    login("a@example.com")
    start(client)
    journey = journeys_for(user.id)[0]

    assert len(notify_spy) == 1
    call = notify_spy[0]
    assert call["user_id"] == user.id and call["type"] == "journey_started"
    assert call["link"].endswith(f"/journey/{journey.id}")
    message = call["message"].lower()
    assert "demo" in message and "no sms or call is sent" in message
    assert "police notified" not in message
    assert Notification.query.filter_by(user_id=user.id, type="journey_started").count() == 1


def test_notify_failure_does_not_lose_the_journey(client, make_user, login, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("notify exploded")

    monkeypatch.setattr(journey_service, "notify", broken)
    user = make_user(email="a@example.com")
    login("a@example.com")
    assert start(client).status_code == 302
    assert len(journeys_for(user.id)) == 1


# ------------------------------------------------------------- ending a journey

def test_end_completes_the_journey_and_notifies(client, make_user, login, notify_spy):
    user = make_user(email="a@example.com")
    journey = make_journey(user)
    login("a@example.com")
    response = client.post(f"/journey/{journey.id}/end")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/journey/{journey.id}")
    journey = db.session.get(SafeJourney, journey.id)
    assert journey.status == "completed"
    assert journey.ended_at is not None and journey.ended_at >= journey.started_at

    assert len(notify_spy) == 1
    assert notify_spy[0]["type"] == "journey_completed"
    assert "demo" in notify_spy[0]["message"].lower()
    assert Notification.query.filter_by(user_id=user.id, type="journey_completed").count() == 1


def test_ending_twice_changes_nothing(client, make_user, login):
    user = make_user(email="a@example.com")
    journey = make_journey(user)
    login("a@example.com")
    client.post(f"/journey/{journey.id}/end")
    first_end = db.session.get(SafeJourney, journey.id).ended_at

    response = client.post(f"/journey/{journey.id}/end")
    assert response.status_code == 302
    assert db.session.get(SafeJourney, journey.id).ended_at == first_end
    assert Notification.query.filter_by(user_id=user.id, type="journey_completed").count() == 1


def test_end_requires_csrf_token(app, client, make_user, login):
    user = make_user(email="a@example.com")
    journey = make_journey(user)
    login("a@example.com")
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post(f"/journey/{journey.id}/end").status_code == 400
    assert db.session.get(SafeJourney, journey.id).status == "active"


# ------------------------------------------------------------------ ownership

def test_user_cannot_view_or_end_another_users_journey(app, client, make_user, login):
    owner = make_user(email="owner@example.com")
    make_user(email="intruder@example.com")
    journey = make_journey(owner)

    login("intruder@example.com")
    assert client.get(f"/journey/{journey.id}").status_code == 404
    assert client.post(f"/journey/{journey.id}/end").status_code == 404
    assert db.session.get(SafeJourney, journey.id).status == "active"

    owner_client = login_as(app, "owner@example.com")
    assert owner_client.get(f"/journey/{journey.id}").status_code == 200
    assert owner_client.post(f"/journey/{journey.id}/end").status_code == 302
    assert db.session.get(SafeJourney, journey.id).status == "completed"


def test_unknown_journey_is_404(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    assert client.get("/journey/99999").status_code == 404
    assert client.post("/journey/99999/end").status_code == 404


def test_guardian_cannot_view_or_end_a_journey(app, client, make_user, login):
    owner = make_user(email="owner@example.com")
    make_user(email="g@example.com", role="guardian")
    journey = make_journey(owner)
    login("g@example.com")
    assert client.get(f"/journey/{journey.id}").status_code == 403
    assert client.post(f"/journey/{journey.id}/end").status_code == 403


# ---------------------------------------------------------------- detail page

def test_active_detail_page_has_map_note_and_controls(client, make_user, login):
    user = make_user(email="a@example.com")
    journey = make_journey(user, simulated=True)
    login("a@example.com")
    response = client.get(f"/journey/{journey.id}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="journey-map"' in html
    assert "OpenStreetMap" in html
    assert NOTE in html
    assert "Simulated demo location" in html
    assert 'id="live-start"' in html
    assert "End journey" in html and 'name="csrf_token"' in html
    assert "no SMS or call is sent" in html
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_device_location_label(client, make_user, login):
    user = make_user(email="a@example.com")
    journey = make_journey(user, simulated=False)
    login("a@example.com")
    html = client.get(f"/journey/{journey.id}").get_data(as_text=True)
    assert "Location shared from your device" in html
    assert "Simulated demo location" not in html


def test_completed_detail_has_no_end_form_or_live_controls(client, make_user, login):
    user = make_user(email="a@example.com")
    journey = make_journey(user, status="completed")
    login("a@example.com")
    html = client.get(f"/journey/{journey.id}").get_data(as_text=True)
    assert "Completed" in html
    assert "End journey" not in html
    assert 'id="live-start"' not in html


def test_journey_without_start_info_or_coordinates_still_renders(client, make_user, login):
    user = make_user(email="a@example.com")
    journey = make_journey(user, lat=None, lng=None, with_info=False)
    login("a@example.com")
    response = client.get(f"/journey/{journey.id}")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "No start location was recorded" in html
    assert "Start location source was not recorded" in html


# --------------------------------------------------------------- history page

def test_history_lists_only_own_completed_journeys(app, client, make_user, login):
    owner = make_user(email="owner@example.com")
    other = make_user(email="other@example.com")
    make_journey(owner, destination="Completed Trip One", status="completed")
    make_journey(owner, destination="Active Trip Two", status="active")
    make_journey(other, destination="Other Persons Trip", status="completed")

    login("owner@example.com")
    response = client.get("/journey/history")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Completed Trip One" in html
    assert "Active Trip Two" not in html
    assert "Other Persons Trip" not in html


def test_history_empty_state(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    html = client.get("/journey/history").get_data(as_text=True)
    assert "You have no completed journeys yet." in html