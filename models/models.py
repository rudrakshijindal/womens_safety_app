from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

ROLES = ("user", "guardian", "admin")
REQUEST_STATUSES = ("pending", "accepted", "resolved", "cancelled")
GUARDIAN_STATUSES = ("pending", "approved", "rejected")


def utcnow():
    """Naive UTC timestamp (SQLite stores naive datetimes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False, default="user", index=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(15))
    password_hash = db.Column(db.String(255), nullable=False)
    blood_group = db.Column(db.String(5))
    medical_info = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    trusted_contacts = db.relationship(
        "TrustedContact", back_populates="user", cascade="all, delete-orphan"
    )
    guardian_profile = db.relationship(
        "GuardianProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    emergency_requests = db.relationship(
        "EmergencyRequest",
        back_populates="user",
        foreign_keys="EmergencyRequest.user_id",
        cascade="all, delete-orphan",
    )
    journeys = db.relationship("SafeJourney", back_populates="user", cascade="all, delete-orphan")
    notifications = db.relationship(
        "Notification", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class TrustedContact(db.Model):
    __tablename__ = "trusted_contacts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    relation = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="trusted_contacts")


class GuardianProfile(db.Model):
    __tablename__ = "guardian_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    organisation = db.Column(db.String(150))
    id_proof_note = db.Column(db.String(255))
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    on_duty = db.Column(db.Boolean, nullable=False, default=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    location_is_simulated = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    approved_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="guardian_profile")


class EmergencyRequest(db.Model):
    __tablename__ = "emergency_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    location_is_simulated = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    accepted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    accepted_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="emergency_requests", foreign_keys=[user_id])
    accepted_by = db.relationship("User", foreign_keys=[accepted_by_id])
    matches = db.relationship(
        "RequestMatch", back_populates="request", cascade="all, delete-orphan"
    )
    responses = db.relationship(
        "GuardianResponse", back_populates="request", cascade="all, delete-orphan"
    )


class RequestMatch(db.Model):
    """Which guardians were matched to an emergency request (and how far away)."""

    __tablename__ = "request_matches"
    __table_args__ = (db.UniqueConstraint("request_id", "guardian_id"),)

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("emergency_requests.id"), nullable=False)
    guardian_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    distance_km = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    request = db.relationship("EmergencyRequest", back_populates="matches")
    guardian = db.relationship("User")


class GuardianResponse(db.Model):
    __tablename__ = "guardian_responses"
    __table_args__ = (db.UniqueConstraint("request_id", "guardian_id"),)

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("emergency_requests.id"), nullable=False)
    guardian_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    action = db.Column(db.String(20), nullable=False)  # accepted | rejected
    responded_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    request = db.relationship("EmergencyRequest", back_populates="responses")
    guardian = db.relationship("User")


class SafeJourney(db.Model):
    __tablename__ = "safe_journeys"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    destination = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_lat = db.Column(db.Float)
    start_lng = db.Column(db.Float)
    status = db.Column(db.String(20), nullable=False, default="active")
    started_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    ended_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="journeys")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(300))
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="notifications")