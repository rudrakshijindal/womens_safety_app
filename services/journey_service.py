"""Safe Journey business logic (Step 2.4).

Validation, ownership checks, persistence and notifications live here so
routes/journey.py stays thin. Journeys are in-app records only: nothing is
sent to trusted contacts and no SMS or call is made.
"""

from datetime import timedelta

from flask import current_app, url_for

from extensions import db
from models import SafeJourney, utcnow
from models.journey_links import JourneyStartInfo
from services.notifications import notify
from services.sos_service import (
    LOCATION_DEVICE,
    LOCATION_SIMULATED,
    get_simulated_location,
    parse_coordinate,
)

STATUS_ACTIVE = "active"
STATUS_COMPLETED = "completed"

MIN_DESTINATION_LENGTH = 2
MAX_DESTINATION_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 500
HISTORY_LIMIT = 50

STATUS_BADGES = {STATUS_ACTIVE: "success", STATUS_COMPLETED: "secondary"}


# ------------------------------------------------------------ validation

def _has_control_characters(text, allowed=""):
    return any(
        (ord(ch) < 32 and ch not in allowed) or ord(ch) == 127 for ch in text
    )


def validate_destination(raw):
    """Return (clean_text, error). error is None when the destination is valid."""
    text = " ".join((raw or "").split())  # trims and collapses whitespace
    if len(text) < MIN_DESTINATION_LENGTH:
        return text, (
            f"Enter where you are going (at least {MIN_DESTINATION_LENGTH} characters)."
        )
    if len(text) > MAX_DESTINATION_LENGTH:
        return text, (
            f"The destination must be at most {MAX_DESTINATION_LENGTH} characters."
        )
    if _has_control_characters(text):
        return text, "The destination contains unsupported characters."
    if not any(ch.isalnum() for ch in text):
        return text, "The destination must include at least one letter or number."
    return text, None


def validate_description(raw):
    """Return (clean_text, error). The description is optional."""
    text = (raw or "").replace("\r\n", "\n").strip()
    if len(text) > MAX_DESCRIPTION_LENGTH:
        return text, (
            f"Keep the description under {MAX_DESCRIPTION_LENGTH} characters."
        )
    if _has_control_characters(text, allowed="\n\t"):
        return text, "The description contains unsupported characters."
    return text, None


def resolve_start_location(form):
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
        "The location choice was missing. Please use the Start journey button "
        "on this page with JavaScript enabled."
    )


# ---------------------------------------------------------------- helpers

def format_duration(delta):
    """Return a short human-readable duration such as '1 h 5 min'."""
    total_minutes = max(0, int(delta.total_seconds() // 60))
    if total_minutes < 1:
        return "less than a minute"
    days, remainder = divmod(total_minutes, 1440)
    hours, minutes = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    return " ".join(parts)


def _short(text, limit=60):
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _notify_user(user_id, type_, message, journey_id):
    """Send the in-app notification. A failure is logged and never undoes the
    journey change, which is committed before this runs."""
    try:
        notify(
            user_id,
            type_,
            message,
            url_for("journey.detail", journey_id=journey_id),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "notify() failed for journey %s; the journey itself was saved", journey_id
        )


# ---------------------------------------------------------------- reading

def get_owned_journey(user_id, journey_id):
    """Return the journey only if it belongs to this user, else None."""
    return SafeJourney.query.filter_by(id=journey_id, user_id=user_id).first()


def get_active_journey(user_id):
    return (
        SafeJourney.query.filter_by(user_id=user_id, status=STATUS_ACTIVE)
        .order_by(SafeJourney.id.desc())
        .first()
    )


def build_journey_view(journey):
    """Display data for one journey. Coordinates are shown approximately."""
    info = journey.start_info
    if info is None:
        location_label = "Start location source was not recorded"
    elif info.location_is_simulated:
        location_label = "Simulated demo location (not your real location)"
    else:
        location_label = "Location shared from your device"

    end = journey.ended_at or utcnow()
    has_coordinates = journey.start_lat is not None and journey.start_lng is not None
    status = journey.status or ""
    return {
        "is_active": status == STATUS_ACTIVE,
        "status_text": status.capitalize() or "Unknown",
        "status_badge": STATUS_BADGES.get(status, "secondary"),
        "duration_text": format_duration(end - journey.started_at),
        "location_label": location_label,
        "has_coordinates": has_coordinates,
        "lat": journey.start_lat if has_coordinates else None,
        "lng": journey.start_lng if has_coordinates else None,
    }


def list_completed(user_id, limit=HISTORY_LIMIT):
    journeys = (
        SafeJourney.query.filter_by(user_id=user_id, status=STATUS_COMPLETED)
        .order_by(SafeJourney.ended_at.desc(), SafeJourney.id.desc())
        .limit(limit)
        .all()
    )
    return [{"journey": j, "view": build_journey_view(j)} for j in journeys]


# --------------------------------------------------------------- changing

def start_journey(user_id, form):
    """Validate and start a journey.

    Returns (journey_or_None, created, values, errors).
    * errors non-empty: nothing was created.
    * created False and no errors: the user already had an active journey,
      which is returned instead of creating a duplicate.
    """
    active = get_active_journey(user_id)
    if active is not None:
        return active, False, {}, {}

    destination, destination_error = validate_destination(form.get("destination"))
    description, description_error = validate_description(form.get("description"))
    lat, lng, simulated, location_error = resolve_start_location(form)

    values = {"destination": destination, "description": description}
    errors = {}
    if destination_error:
        errors["destination"] = destination_error
    if description_error:
        errors["description"] = description_error
    if location_error:
        errors["location"] = location_error
    if errors:
        return None, False, values, errors

    journey = SafeJourney(
        user_id=user_id,
        destination=destination,
        description=description or None,
        start_lat=lat,
        start_lng=lng,
        status=STATUS_ACTIVE,
    )
    db.session.add(journey)
    db.session.flush()  # assigns journey.id
    db.session.add(
        JourneyStartInfo(journey_id=journey.id, location_is_simulated=simulated)
    )
    db.session.commit()

    _notify_user(
        user_id,
        "journey_started",
        (
            f"Journey to {_short(destination)} started. In-app record only (demo): "
            "trusted contacts are not notified and no SMS or call is sent."
        ),
        journey.id,
    )
    return journey, True, values, {}


def end_journey(user_id, journey_id):
    """Complete a journey the user owns.

    Returns (result, journey) where result is "ok", "already_ended" or
    "not_found". "not_found" covers both a missing journey and someone
    else's journey, so the route can answer 404 for both.
    """
    journey = get_owned_journey(user_id, journey_id)
    if journey is None:
        return "not_found", None
    if journey.status != STATUS_ACTIVE:
        return "already_ended", journey

    journey.status = STATUS_COMPLETED
    journey.ended_at = utcnow()
    db.session.commit()

    duration = format_duration(journey.ended_at - journey.started_at)
    _notify_user(
        user_id,
        "journey_completed",
        (
            f"Journey to {_short(journey.destination)} completed (duration: {duration}). "
            "In-app record only (demo); nothing was sent to your contacts."
        ),
        journey.id,
    )
    return "ok", journey