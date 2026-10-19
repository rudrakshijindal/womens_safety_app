from math import asin, cos, radians, sin, sqrt

from extensions import db
from models import GuardianProfile, RequestMatch
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
