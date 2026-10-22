"""SOS workflow business logic (Step 2.3).

Routes stay thin. Validation, matching, persistence and notification live here.
This service never contacts anyone outside the app: it creates an in-app
request only, and the UI says so.

Matching and guardian alerts reuse teammate 1's services.matching:
find_eligible_guardians() and dispatch_to_guardians().
"""

import math
import re
from datetime import timedelta

from flask import current_app, url_for

from extensions import db
from models import EmergencyRequest, TrustedContact, utcnow
from models.sos_links import RequestContact
from services.matching import dispatch_to_guardians, find_eligible_guardians
from services.notifications import notify

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
ACTIVE_STATUSES = (STATUS_PENDING, STATUS_ACCEPTED)

LOCATION_DEVICE = "device"
LOCATION_SIMULATED = "simulated"

MATCH_LIMIT = 5
DUPLICATE_WINDOW_SECONDS = 120

# Used only when the app config has no SOS_SIMULATED_LATITUDE/LONGITUDE.
DEFAULT_SIMULATED_LATITUDE = 28.6139
DEFAULT_SIMULATED_LONGITUDE = 77.2090

DELIVERY_LABEL = (
    "In-app alert created. External SMS/call delivery is not configured (demo)"
)

# Static list. The team must verify these numbers against an official source.
HELPLINES = [
    {"number": "112", "name": "National emergency number (India)"},
    {"number": "1091", "name": "Women's helpline"},
    {"number": "181", "name": "Women's helpline"},
]

STATUS_DESCRIPTIONS = {
    "pending": "Waiting for a matched guardian to respond in the app.",
    "accepted": "A matched guardian accepted this request in the app (demo).",
    "resolved": "This request has been marked resolved.",
    "cancelled": "This request was cancelled.",
}
STATUS_BADGES = {
    "pending": "warning",
    "accepted": "success",
    "resolved": "secondary",
    "cancelled": "dark",
}

# Plain decimal numbers only: no exponents, no "nan"/"inf", no underscores.
_COORDINATE = re.compile(r"[+-]?[0-9]{1,3}(?:\.[0-9]{1,10})?")


# ------------------------------------------------------------ validation

def parse_coordinate(raw, low, high):
    """Return a float within [low, high], or None if the text is not valid."""
    text = str(raw).strip() if raw is not None else ""
    if not _COORDINATE.fullmatch(text):
        return None
    value = float(text)
    if not (low <= value <= high):
        return None
    return value


def _config_coordinate(value, low, high, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(number) or not (low <= number <= high):
        return fallback
    return number


def get_simulated_location():
    """Return the (lat, lng) used when the browser location is not shared."""
    config = current_app.config
    lat = _config_coordinate(
        config.get("SOS_SIMULATED_LATITUDE"), -90, 90, DEFAULT_SIMULATED_LATITUDE
    )
    lng = _config_coordinate(
        config.get("SOS_SIMULATED_LONGITUDE"), -180, 180, DEFAULT_SIMULATED_LONGITUDE
    )
    return lat, lng


def resolve_location(form):
    """Return (lat, lng, is_simulated, error).

    "simulated": client coordinates are ignored and the configured demo
    location is used. "device": coordinates must be valid and in range.
    """
    source = (form.get("location_source") or "").strip()

    if source == LOCATION_SIMULATED:
        lat, lng = get_simulated_location()
        return lat, lng, True, None

    if source == LOCATION_DEVICE:
        lat = parse_coordinate(form.get("latitude"), -90, 90)
        lng = parse_coordinate(form.get("longitude"), -180, 180)
        if lat is None or lng is None:
            return None, None, False, (
                "Your device sent a location that could not be read. Please try again."
            )
        return round(lat, 6), round(lng, 6), False, None

    return None, None, False, (
        "The location choice was missing. Please use the SOS button on this page "
        "with JavaScript enabled."
    )


# ------------------------------------------------------------ duplicates

def _recent_active_request(user_id):
    """Return this user's active request created within the duplicate window."""
    cutoff = utcnow() - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
    return (
        EmergencyRequest.query.filter(
            EmergencyRequest.user_id == user_id,
            EmergencyRequest.status.in_(ACTIVE_STATUSES),
            EmergencyRequest.created_at >= cutoff,
        )
        .order_by(EmergencyRequest.id.desc())
        .first()
    )


# --------------------------------------------------------------- creation

def _notify_requester(user_id, request_id, matched_count):
    if matched_count:
        message = (
            f"SOS request #{request_id}: an in-app alert was created and "
            f"{matched_count} approved guardian(s) on duty were matched by distance (demo). "
            "No SMS, call or police alert was sent."
        )
    else:
        message = (
            f"SOS request #{request_id}: an in-app alert was created, but no approved "
            "guardian on duty was found nearby (demo). No SMS, call or police alert was "
            "sent. If you are in danger, call your local emergency number."
        )
    try:
        notify(
            user_id,
            "sos_created",
            message,
            url_for("sos.detail", request_id=request_id),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "notify() failed for SOS request %s; the request itself was saved",
            request_id,
        )


def create_sos_request(user_id, form):
    """Validate the location, create the request, link trusted contacts,
    match guardians and notify the user.

    Returns (emergency_request_or_None, created, error_message_or_None).
    `created` is False when a recent active request is returned instead of
    a duplicate.
    """
    lat, lng, simulated, error = resolve_location(form)
    if error:
        return None, False, error

    existing = _recent_active_request(user_id)
    if existing is not None:
        return existing, False, None

    emergency = EmergencyRequest(
        user_id=user_id,
        latitude=lat,
        longitude=lng,
        status=STATUS_PENDING,
        location_is_simulated=simulated,
    )
    db.session.add(emergency)
    db.session.flush()  # assigns emergency.id

    contacts = (
        TrustedContact.query.filter_by(user_id=user_id)
        .order_by(TrustedContact.id)
        .all()
    )
    for contact in contacts:
        db.session.add(
            RequestContact(
                request_id=emergency.id,
                contact_name=contact.name,
                contact_phone=contact.phone,
            )
        )

    # Commit the request and contacts first: a matching or notification
    # failure below must never lose the SOS request.
    db.session.commit()
    request_id = emergency.id

    matched_count = 0
    try:
        matches = find_eligible_guardians(lat, lng, limit=MATCH_LIMIT)
        matched_count = dispatch_to_guardians(emergency, matches)
    except Exception:
        db.session.rollback()
        matched_count = 0
        current_app.logger.exception(
            "Guardian matching failed; SOS request %s was kept without matches",
            request_id,
        )

    _notify_requester(user_id, request_id, matched_count)
    return db.session.get(EmergencyRequest, request_id), True, None


# ---------------------------------------------------------------- reading

def get_owned_request(user_id, request_id):
    """Return the request only if it belongs to this user, else None."""
    return EmergencyRequest.query.filter_by(id=request_id, user_id=user_id).first()


def list_user_requests(user_id, limit=5):
    return (
        EmergencyRequest.query.filter_by(user_id=user_id)
        .order_by(EmergencyRequest.id.desc())
        .limit(limit)
        .all()
    )


def mask_phone(phone):
    phone = phone or ""
    if len(phone) <= 4:
        return "*" * len(phone)
    return "*" * (len(phone) - 4) + phone[-4:]


def build_request_view(emergency):
    """Everything the detail page needs.

    Matched guardians expose name and approximate distance only. No guardian
    coordinates, email or phone are returned, and trusted contact phone numbers
    are masked.
    """
    matches = sorted(emergency.matches, key=lambda m: (m.distance_km, m.id))
    guardians = [
        {"name": m.guardian.name, "distance_km": m.distance_km} for m in matches
    ]

    contact_rows = (
        RequestContact.query.filter_by(request_id=emergency.id)
        .order_by(RequestContact.id)
        .all()
    )
    contacts = [
        {"name": c.contact_name, "phone_masked": mask_phone(c.contact_phone)}
        for c in contact_rows
    ]

    status = emergency.status or ""
    accepted_by = emergency.accepted_by
    return {
        "guardians": guardians,
        "contacts": contacts,
        "status_text": status.capitalize() or "Unknown",
        "status_description": STATUS_DESCRIPTIONS.get(status, ""),
        "status_badge": STATUS_BADGES.get(status, "secondary"),
        "accepted_by_name": accepted_by.name if accepted_by else None,
        "location_label": (
            "Simulated demo location (not your real location)"
            if emergency.location_is_simulated
            else "Location shared from your device"
        ),
        "delivery_label": DELIVERY_LABEL,
    }