import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import (
    EmergencyRequest,
    GuardianProfile,
    GuardianResponse,
    Notification,
    RequestMatch,
    SafeJourney,
    TrustedContact,
    User,
)
from services.notifications import notify


def make_user(email="riya@example.com", role="user", name="Riya"):
    user = User(name=name, email=email, role=role)
    user.set_password("Secret@123")
    db.session.add(user)
    db.session.commit()
    return user


def test_all_tables_are_created(app):
    tables = set(inspect(db.engine).get_table_names())
    expected = {
        "users", "trusted_contacts", "guardian_profiles", "emergency_requests",
        "request_matches", "guardian_responses", "safe_journeys", "notifications",
    }
    assert expected <= tables


def test_password_is_hashed_not_plaintext(app):
    user = make_user()
    assert user.password_hash != "Secret@123"
    assert "Secret@123" not in user.password_hash
    assert user.check_password("Secret@123")
    assert not user.check_password("wrong-password")


def test_email_must_be_unique(app):
    make_user("same@example.com")
    with pytest.raises(IntegrityError):
        make_user("same@example.com", name="Other")
    db.session.rollback()


def test_default_role_and_timestamp(app):
    user = User(name="Test", email="t@example.com")
    user.set_password("Secret@123")
    db.session.add(user)
    db.session.commit()
    assert user.role == "user"
    assert user.created_at is not None


def test_guardian_profile_defaults(app):
    guardian = make_user("g@example.com", role="guardian", name="Guardian")
    profile = GuardianProfile(user_id=guardian.id, organisation="Test NGO")
    db.session.add(profile)
    db.session.commit()
    assert profile.status == "pending"
    assert profile.on_duty is False
    assert profile.latitude is None
    assert guardian.guardian_profile.organisation == "Test NGO"


def test_trusted_contact_relationship(app):
    user = make_user()
    db.session.add(TrustedContact(user_id=user.id, name="Mom", phone="9876543210"))
    db.session.commit()
    assert [c.name for c in user.trusted_contacts] == ["Mom"]


def test_emergency_request_relationships(app):
    user = make_user()
    guardian = make_user("g@example.com", role="guardian", name="Guardian")
    req = EmergencyRequest(user_id=user.id, latitude=28.67, longitude=77.45)
    db.session.add(req)
    db.session.commit()
    assert req.status == "pending"

    db.session.add(RequestMatch(request_id=req.id, guardian_id=guardian.id, distance_km=1.5))
    db.session.add(GuardianResponse(request_id=req.id, guardian_id=guardian.id, action="accepted"))
    req.accepted_by_id = guardian.id
    db.session.commit()

    assert req.user.id == user.id
    assert req.accepted_by.id == guardian.id
    assert len(req.matches) == 1
    assert req.responses[0].action == "accepted"
    assert user.emergency_requests[0].id == req.id


def test_safe_journey_defaults(app):
    user = make_user()
    journey = SafeJourney(user_id=user.id, destination="College")
    db.session.add(journey)
    db.session.commit()
    assert journey.status == "active"
    assert journey.started_at is not None


def test_notify_stores_notification(app):
    user = make_user()
    notify(user.id, "test", "Hello there", "/somewhere")
    note = Notification.query.filter_by(user_id=user.id).one()
    assert note.message == "Hello there"
    assert note.link == "/somewhere"
    assert note.is_read is False
    assert note.created_at is not None