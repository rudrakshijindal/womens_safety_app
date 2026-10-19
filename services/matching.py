from math import asin, cos, radians, sin, sqrt

from models import GuardianProfile


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
