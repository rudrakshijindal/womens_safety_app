"""Link table for the SOS workflow (Step 2.3).

RequestContact is a snapshot of the requester's trusted contacts at the time of
an SOS request, so the request history stays correct if a contact is deleted
later. Which guardians were matched is stored in teammate 1's RequestMatch.
"""

from extensions import db

from .models import utcnow


class RequestContact(db.Model):
    __tablename__ = "request_contacts"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer, db.ForeignKey("emergency_requests.id"), nullable=False, index=True
    )
    contact_name = db.Column(db.String(100), nullable=False)
    contact_phone = db.Column(db.String(15), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    request = db.relationship(
        "EmergencyRequest",
        backref=db.backref("contact_snapshots", cascade="all, delete-orphan"),
    )