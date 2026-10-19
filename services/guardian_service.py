from extensions import db
from models import GuardianProfile, User

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


def toggle_duty(profile):
    """Flip on_duty. Going on duty needs a saved location. Returns (ok, message)."""
    if profile.status != "approved":
        return False, "Only approved guardians can go on duty."
    if not profile.on_duty and (profile.latitude is None or profile.longitude is None):
        return False, "Set your location first, then go on duty."
    profile.on_duty = not profile.on_duty
    db.session.commit()
    return True, "You are now ON duty. Nearby requests can be matched to you." if profile.on_duty else "You are now OFF duty."
