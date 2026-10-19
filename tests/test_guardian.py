from extensions import db
from models import GuardianProfile, Notification, User


def guardian_form(**overrides):
    data = {
        "name": "Meera Singh",
        "email": "meera@example.com",
        "phone": "9876543210",
        "organisation": "Helping Hands NGO",
        "id_proof_note": "Aadhaar, last 4 digits 1234",
        "reason": "I want to help",
        "password": "Secret@123",
        "confirm_password": "Secret@123",
        "agree": "on",
    }
    data.update(overrides)
    return data


def apply(client, **overrides):
    return client.post("/guardian/register", data=guardian_form(**overrides))


def admin_client(app, make_user):
    make_user("admin@example.com", role="admin", name="Admin")
    admin = app.test_client()
    admin.post("/login", data={"email": "admin@example.com", "password": "Secret@123"})
    return admin


def approved_guardian(app, client):
    """Sign a guardian up, approve them with a separate admin client, return the profile."""
    apply(client)
    profile = GuardianProfile.query.one()
    profile.status = "approved"
    db.session.commit()
    return profile


# ---------- signup ----------

def test_signup_creates_pending_guardian(client):
    response = apply(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/guardian/status")
    user = User.query.filter_by(email="meera@example.com").one()
    assert user.role == "guardian"
    assert user.guardian_profile.status == "pending"
    assert user.guardian_profile.on_duty is False
    assert user.guardian_profile.organisation == "Helping Hands NGO"


def test_form_cannot_choose_role_or_status(client):
    apply(client, role="admin", status="approved")
    user = User.query.filter_by(email="meera@example.com").one()
    assert user.role == "guardian"
    assert user.guardian_profile.status == "pending"


def test_full_id_number_is_rejected(client):
    response = apply(client, id_proof_note="Aadhaar 123456789012")
    assert response.status_code == 400
    assert b"last 4 digits only" in response.data
    assert User.query.count() == 0


def test_signup_validation(client):
    assert b"organisation" in apply(client, organisation="").data
    assert b"10-digit" in apply(client, email="a@b.com", phone="").data
    assert b"tick the box" in apply(client, email="c@d.com", agree="").data
    assert User.query.count() == 0


def test_duplicate_email_rejected(client):
    apply(client)
    client.post("/logout")
    response = apply(client)
    assert response.status_code == 400
    assert User.query.count() == 1


# ---------- access control ----------

def test_pending_guardian_is_blocked_from_dashboard(client):
    apply(client)
    response = client.get("/guardian/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/guardian/status")


def test_pending_guardian_cannot_change_duty_or_location(client):
    apply(client)
    client.post("/guardian/duty")
    client.post("/guardian/location", data={"preset": "raj_nagar"})
    profile = GuardianProfile.query.one()
    assert profile.on_duty is False
    assert profile.latitude is None


def test_normal_user_gets_403_on_guardian_pages(client, make_user, login):
    make_user("plain@example.com")
    login("plain@example.com")
    assert client.get("/guardian/status").status_code == 403
    assert client.get("/guardian/dashboard").status_code == 403


def test_anonymous_is_sent_to_login(client):
    response = client.get("/guardian/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ---------- admin decisions ----------

def test_admin_approves_guardian_and_notifies(app, client, make_user):
    apply(client)
    admin = admin_client(app, make_user)
    profile = GuardianProfile.query.one()

    response = admin.post(f"/admin/applications/{profile.id}/approve")
    assert response.status_code == 302

    db.session.refresh(profile)
    assert profile.status == "approved"
    assert profile.approved_at is not None
    note = Notification.query.filter_by(user_id=profile.user_id).one()
    assert "Approved by admin" in note.message
    assert client.get("/guardian/dashboard").status_code == 200


def test_admin_rejects_guardian(app, client, make_user):
    apply(client)
    admin = admin_client(app, make_user)
    profile = GuardianProfile.query.one()
    admin.post(f"/admin/applications/{profile.id}/reject")

    db.session.refresh(profile)
    assert profile.status == "rejected"
    assert profile.on_duty is False
    assert client.get("/guardian/dashboard").status_code == 302


def test_non_admin_cannot_approve(app, client, make_user):
    apply(client)
    profile = GuardianProfile.query.one()
    # the logged-in pending guardian tries to approve themselves
    assert client.post(f"/admin/applications/{profile.id}/approve").status_code == 403
    db.session.refresh(profile)
    assert profile.status == "pending"


def test_anonymous_cannot_approve(client, make_user):
    make_user("g@example.com", role="guardian")
    profile = GuardianProfile(user_id=1, organisation="X", id_proof_note="Aadhaar 1234")
    db.session.add(profile)
    db.session.commit()
    response = client.post(f"/admin/applications/{profile.id}/approve")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_invalid_or_repeated_decision_changes_nothing(app, client, make_user):
    apply(client)
    admin = admin_client(app, make_user)
    profile = GuardianProfile.query.one()

    admin.post(f"/admin/applications/{profile.id}/delete")
    db.session.refresh(profile)
    assert profile.status == "pending"

    admin.post(f"/admin/applications/{profile.id}/approve")
    admin.post(f"/admin/applications/{profile.id}/reject")  # already decided
    db.session.refresh(profile)
    assert profile.status == "approved"
    assert Notification.query.filter_by(user_id=profile.user_id).count() == 1


def test_admin_pages_open(app, make_user, client):
    apply(client)
    admin = admin_client(app, make_user)
    for url in ("/admin/", "/admin/applications", "/admin/guardians"):
        assert admin.get(url).status_code == 200
    assert b"Meera Singh" in admin.get("/admin/applications").data


# ---------- duty and location ----------

def test_going_on_duty_needs_a_location(app, client):
    approved_guardian(app, client)
    profile = GuardianProfile.query.one()

    client.post("/guardian/duty")
    db.session.refresh(profile)
    assert profile.on_duty is False

    client.post("/guardian/location", data={"preset": "raj_nagar"})
    db.session.refresh(profile)
    assert profile.latitude == 28.67
    assert profile.location_is_simulated is True

    client.post("/guardian/duty")
    db.session.refresh(profile)
    assert profile.on_duty is True
    client.post("/guardian/duty")
    db.session.refresh(profile)
    assert profile.on_duty is False


def test_manual_and_device_coordinates(app, client):
    approved_guardian(app, client)
    profile = GuardianProfile.query.one()

    client.post("/guardian/location", data={"latitude": "28.61", "longitude": "77.21"})
    db.session.refresh(profile)
    assert (profile.latitude, profile.longitude) == (28.61, 77.21)
    assert profile.location_is_simulated is True

    client.post("/guardian/location", data={"latitude": "28.62", "longitude": "77.22", "source": "device"})
    db.session.refresh(profile)
    assert profile.location_is_simulated is False


def test_bad_coordinates_are_rejected(app, client):
    approved_guardian(app, client)
    profile = GuardianProfile.query.one()
    for lat, lng in (("abc", "77"), ("95", "77"), ("28", "200"), ("", "")):
        client.post("/guardian/location", data={"latitude": lat, "longitude": lng})
    client.post("/guardian/location", data={"preset": "not_a_place"})
    db.session.refresh(profile)
    assert profile.latitude is None


def test_guardian_dashboard_renders(app, client):
    approved_guardian(app, client)
    html = client.get("/guardian/dashboard").get_data(as_text=True)
    assert "Duty status" in html
    assert "Raj Nagar" in html


# ---------- admin account creation ----------

def test_create_admin_command(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["create-admin", "--name", "Boss", "--email", "Boss@Example.com"],
        input="Secret@123\nSecret@123\n",
    )
    assert result.exit_code == 0, result.output
    boss = User.query.filter_by(email="boss@example.com").one()
    assert boss.role == "admin"
    assert boss.check_password("Secret@123")


def test_create_admin_rejects_short_password_and_duplicates(app, make_user):
    make_user("taken@example.com")
    runner = app.test_cli_runner()
    short = runner.invoke(args=["create-admin", "--name", "B", "--email", "b@example.com"], input="short\nshort\n")
    assert short.exit_code != 0
    dup = runner.invoke(args=["create-admin", "--name", "B", "--email", "taken@example.com"], input="Secret@123\nSecret@123\n")
    assert dup.exit_code != 0
