from extensions import db
from models import (
    EmergencyRequest,
    GuardianProfile,
    GuardianResponse,
    RequestMatch,
    User,
    utcnow,
)
from services.matching import match_open_requests
from services.notifications import notify

# Simulated area presets (Ghaziabad) so a guardian can "move" around during the demo.
PRESET_LOCATIONS = {
    "raj_nagar": ("Raj Nagar", 28.6700, 77.4450),
    "indirapuram": ("Indirapuram", 28.6460, 77.3690),
    "vaishali": ("Vaishali", 28.6500, 77.3400),
    "kaushambi": ("Kaushambi", 28.6460, 77.3220),
    "sahibabad": ("Sahibabad", 28.6750, 77.3600),
}


def create_guardian_application(form):
    """Create the user (role fixed to 'guardian') and a pending GuardianProfile."""
    user = User(
        name=form["name"].strip(),
        email=form["email"].strip().lower(),
        phone=form["phone"].strip(),
        role="guardian",
    )
    user.set_password(form["password"])
    db.session.add(user)
    db.session.flush()  # get user.id before creating the profile

    profile = GuardianProfile(
        user_id=user.id,
        organisation=form["organisation"].strip(),
        id_proof_note=form["id_proof_note"].strip(),
        reason=(form.get("reason") or "").strip() or None,
        status="pending",
        on_duty=False,
    )
    db.session.add(profile)
    db.session.commit()
    return user


def parse_coordinates(lat_raw, lng_raw):
    """Return (lat, lng) or raise ValueError with a friendly message."""
    try:
        lat, lng = float(lat_raw), float(lng_raw)
    except (TypeError, ValueError):
        raise ValueError("Latitude and longitude must be numbers.")
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise ValueError("Latitude must be between -90 and 90, and longitude between -180 and 180.")
    return lat, lng


def set_location(profile, lat, lng, simulated=True):
    profile.latitude = round(float(lat), 6)
    profile.longitude = round(float(lng), 6)
    profile.location_is_simulated = bool(simulated)
    db.session.commit()
    match_open_requests(profile)   # no-op unless the guardian is on duty


def toggle_duty(profile):
    """Flip on_duty. Going on duty needs a saved location. Returns (ok, message)."""
    if profile.status != "approved":
        return False, "Only approved guardians can go on duty."
    if not profile.on_duty and (profile.latitude is None or profile.longitude is None):
        return False, "Set your location first, then go on duty."
    profile.on_duty = not profile.on_duty
    db.session.commit()
    if profile.on_duty:
        added = match_open_requests(profile)
        extra = f" {added} open request(s) were matched to you." if added else ""
        return True, "You are now ON duty. Nearby requests can be matched to you." + extra
    return True, "You are now OFF duty."


# ---------------------------------------------------------------- requests

def respond(request_id, guardian_id, action):
    """A guardian accepts or rejects a request that was matched to them.

    Returns one of: ok, invalid, forbidden, already_responded, closed.
    """
    if action not in ("accept", "reject"):
        return "invalid"

    req = db.session.get(EmergencyRequest, request_id)
    match = RequestMatch.query.filter_by(request_id=request_id, guardian_id=guardian_id).first()
    if req is None or match is None:
        return "forbidden"  # not matched to this guardian
    if GuardianResponse.query.filter_by(request_id=request_id, guardian_id=guardian_id).first():
        return "already_responded"
    if req.status != "pending":
        return "closed"  # someone else already accepted, or it was cancelled

    now = utcnow()
    guardian = db.session.get(User, guardian_id)
    db.session.add(
        GuardianResponse(
            request_id=request_id,
            guardian_id=guardian_id,
            action="accepted" if action == "accept" else "rejected",
            responded_at=now,
        )
    )
    if action == "accept":
        req.status = "accepted"
        req.accepted_by_id = guardian_id
        req.accepted_at = now
        notify(
            req.user_id,
            "request_accepted",
            f"Guardian {guardian.name} accepted your emergency request (demo status).",
            "/dashboard",
            commit=False,
        )
    db.session.commit()
    return "ok"


def resolve(request_id, guardian_id):
    """Only the guardian who accepted a request can mark it resolved. Returns ok / forbidden."""
    req = db.session.get(EmergencyRequest, request_id)
    if req is None or req.accepted_by_id != guardian_id or req.status != "accepted":
        return "forbidden"
    req.status = "resolved"
    req.resolved_at = utcnow()
    notify(req.user_id, "request_resolved", "Your emergency request was marked resolved.", "/dashboard", commit=False)
    db.session.commit()
    return "ok"


def metrics(guardian_id):
    """Real numbers computed from stored response timestamps."""
    responses = GuardianResponse.query.filter_by(guardian_id=guardian_id).all()
    minutes = [(r.responded_at - r.request.created_at).total_seconds() / 60 for r in responses]
    return {
        "accepted": sum(1 for r in responses if r.action == "accepted"),
        "rejected": sum(1 for r in responses if r.action == "rejected"),
        "resolved": EmergencyRequest.query.filter_by(accepted_by_id=guardian_id, status="resolved").count(),
        "avg_response_min": round(sum(minutes) / len(minutes), 1) if minutes else None,
    }


def dashboard_data(guardian_id):
    matches = RequestMatch.query.filter_by(guardian_id=guardian_id).all()
    responded = {r.request_id for r in GuardianResponse.query.filter_by(guardian_id=guardian_id).all()}
    incoming = sorted(
        [m for m in matches if m.request.status == "pending" and m.request_id not in responded],
        key=lambda m: m.request.created_at,
        reverse=True,
    )
    active = (
        EmergencyRequest.query.filter_by(accepted_by_id=guardian_id, status="accepted")
        .order_by(EmergencyRequest.created_at.desc())
        .all()
    )
    history = (
        GuardianResponse.query.filter_by(guardian_id=guardian_id)
        .order_by(GuardianResponse.responded_at.desc())
        .limit(10)
        .all()
    )
    return {"incoming": incoming, "active": active, "history": history, "metrics": metrics(guardian_id)}
