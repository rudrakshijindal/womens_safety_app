from extensions import db
from models import EmergencyRequest, GuardianProfile, User, utcnow
from services.notifications import notify


def stats():
    """Real counts straight from the database. No fake numbers."""
    return {
        "users": User.query.filter_by(role="user").count(),
        "approved_guardians": GuardianProfile.query.filter_by(status="approved").count(),
        "pending_guardians": GuardianProfile.query.filter_by(status="pending").count(),
        "on_duty_guardians": GuardianProfile.query.filter_by(status="approved", on_duty=True).count(),
        "requests": EmergencyRequest.query.count(),
    }


def pending_applications():
    return (
        GuardianProfile.query.filter_by(status="pending")
        .order_by(GuardianProfile.created_at.asc())
        .all()
    )


def recent_decisions(limit=10):
    return (
        GuardianProfile.query.filter(GuardianProfile.status.in_(("approved", "rejected")))
        .order_by(GuardianProfile.created_at.desc())
        .limit(limit)
        .all()
    )


def all_guardians():
    return GuardianProfile.query.order_by(GuardianProfile.created_at.desc()).all()


def decide_application(profile_id, decision):
    """Approve or reject a pending guardian application.

    Returns the profile, or None if it does not exist, is not pending, or the
    decision is not 'approve' / 'reject'.
    """
    profile = db.session.get(GuardianProfile, profile_id)
    if profile is None or decision not in ("approve", "reject") or profile.status != "pending":
        return None

    if decision == "approve":
        profile.status = "approved"
        profile.approved_at = utcnow()
        message = "Approved by admin. You can now set your location and go on duty."
    else:
        profile.status = "rejected"
        profile.on_duty = False
        message = "Your guardian application was not approved by the admin."

    notify(profile.user_id, f"guardian_{profile.status}", message, "/guardian/status", commit=False)
    db.session.commit()
    return profile
