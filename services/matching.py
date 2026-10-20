from math import asin, cos, radians, sin, sqrt

from extensions import db
from models import EmergencyRequest, GuardianProfile, RequestMatch
from services.notifications import notify


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres between two latitude/longitude points."""
    r = 6371.0088  # mean Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def find_eligible_guardians(lat, lng, limit=5):
    """Approved guardians who are on duty and have a location, nearest first.

    Returns a list of dicts with an approximate distance only. A guardian's exact
    coordinates are never included in the result.
    """
    profiles = GuardianProfile.query.filter(
        GuardianProfile.status == "approved",
        GuardianProfile.on_duty.is_(True),
        GuardianProfile.latitude.isnot(None),
        GuardianProfile.longitude.isnot(None),
    ).all()

    ranked = []
    for profile in profiles:
        distance = haversine_km(lat, lng, profile.latitude, profile.longitude)
        ranked.append((distance, profile))
    ranked.sort(key=lambda pair: pair[0])

    results = []
    for distance, profile in ranked[: max(0, int(limit))]:
        results.append(
            {
                "guardian_id": profile.user_id,
                "name": profile.user.name,
                "organisation": profile.organisation,
                "distance_km": round(distance, 1),
                "location_is_simulated": profile.location_is_simulated,
            }
        )
    return results


def dispatch_to_guardians(emergency_request, matches):
    """Link matched guardians to a request and send each an in-app notification.

    The SOS feature (Teammate 2) calls this right after creating an EmergencyRequest:

        matches = find_eligible_guardians(req.latitude, req.longitude, limit=5)
        dispatch_to_guardians(req, matches)

    Returns how many guardians were matched. In-app notification only; nothing is sent by SMS.
    """
    for m in matches:
        db.session.add(
            RequestMatch(
                request_id=emergency_request.id,
                guardian_id=m["guardian_id"],
                distance_km=m["distance_km"],
            )
        )
        notify(
            m["guardian_id"],
            "emergency_request",
            f"New emergency request about {m['distance_km']} km from you (in-app demo alert).",
            "/guardian/dashboard",
            commit=False,
        )
    db.session.commit()
    return len(matches)


def match_open_requests(profile, limit=5):
    """Match a guardian who has just become available to requests that are still pending.

    A request is matched once, when it is created, so a guardian who goes on duty (or moves)
    afterwards would miss it. Called when a guardian goes on duty or changes location.
    A request keeps at most `limit` matched guardians. Returns how many requests were added.
    """
    if profile.status != "approved" or not profile.on_duty or profile.latitude is None:
        return 0

    added = 0
    for req in EmergencyRequest.query.filter_by(status="pending").all():
        if req.user_id == profile.user_id:
            continue
        already = {m.guardian_id for m in req.matches}
        if profile.user_id in already or len(already) >= limit:
            continue
        km = round(haversine_km(profile.latitude, profile.longitude, req.latitude, req.longitude), 1)
        db.session.add(RequestMatch(request_id=req.id, guardian_id=profile.user_id, distance_km=km))
        notify(
            profile.user_id,
            "emergency_request",
            f"Open emergency request about {km} km from you (in-app demo alert).",
            "/guardian/dashboard",
            commit=False,
        )
        added += 1
    db.session.commit()
    return added
