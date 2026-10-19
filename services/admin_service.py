from extensions import db
from models import EmergencyRequest, GuardianProfile, User, utcnow
from services.guardian_service import PRESET_LOCATIONS
from services.matching import dispatch_to_guardians, find_eligible_guardians
from services.notifications import notify


def _avg_minutes(pairs):
    values = [(end - start).total_seconds() / 60 for start, end in pairs if start and end]
    return round(sum(values) / len(values), 1) if values else None


def stats():
    """Real counts and timings straight from the database. No fake numbers."""
    requests = EmergencyRequest.query.all()
    by_status = {"pending": 0, "accepted": 0, "resolved": 0, "cancelled": 0}
    for r in requests:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    return {
        "users": User.query.filter_by(role="user").count(),
        "approved_guardians": GuardianProfile.query.filter_by(status="approved").count(),
        "pending_guardians": GuardianProfile.query.filter_by(status="pending").count(),
        "on_duty_guardians": GuardianProfile.query.filter_by(status="approved", on_duty=True).count(),
        "requests": len(requests),
        "by_status": by_status,
        "avg_accept_min": _avg_minutes([(r.created_at, r.accepted_at) for r in requests]),
        "avg_resolve_min": _avg_minutes([(r.accepted_at, r.resolved_at) for r in requests]),
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


def all_users():
    return User.query.order_by(User.created_at.desc()).all()


def all_requests(limit=50):
    return EmergencyRequest.query.order_by(EmergencyRequest.created_at.desc()).limit(limit).all()


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


def create_demo_request(user_id, preset_key):
    """Demo tool that stands in for the SOS button (built by Teammate 2).

    Creates an EmergencyRequest at a simulated location, matches nearby guardians,
    and notifies them and the requester in-app. Returns (request, matches) or (None, []).
    """
    user = db.session.get(User, user_id)
    if user is None or user.role != "user" or preset_key not in PRESET_LOCATIONS:
        return None, []

    label, lat, lng = PRESET_LOCATIONS[preset_key]
    req = EmergencyRequest(
        user_id=user.id,
        latitude=lat,
        longitude=lng,
        status="pending",
        location_is_simulated=True,
    )
    db.session.add(req)
    db.session.commit()

    matches = find_eligible_guardians(req.latitude, req.longitude, limit=5)
    dispatch_to_guardians(req, matches)
    notify(
        user.id,
        "request_created",
        f"Demo alert created near {label}. {len(matches)} guardian(s) matched. "
        "External SMS or call delivery is not configured.",
        "/dashboard",
    )
    return req, matches
