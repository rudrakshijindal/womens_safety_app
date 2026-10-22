"""Side table for Safe Journey (Step 2.4).

Stores whether a journey's start location came from the device or was the
labelled simulated fallback. It lives in its own table so the existing
safe_journeys table (and your current database) does not need to change.
"""

from extensions import db


class JourneyStartInfo(db.Model):
    __tablename__ = "journey_start_info"

    id = db.Column(db.Integer, primary_key=True)
    journey_id = db.Column(
        db.Integer, db.ForeignKey("safe_journeys.id"), unique=True, nullable=False
    )
    location_is_simulated = db.Column(db.Boolean, nullable=False, default=True)

    journey = db.relationship(
        "SafeJourney",
        backref=db.backref(
            "start_info", uselist=False, cascade="all, delete-orphan"
        ),
    )