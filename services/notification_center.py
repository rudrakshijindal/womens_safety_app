

import math

from extensions import db
from models import Notification

PER_PAGE = 20

TYPE_LABELS = {
    "sos_created": "SOS request",
    "emergency_request": "Emergency request",
    "journey_started": "Journey started",
    "journey_completed": "Journey completed",
}


def _own(user_id):
    return Notification.query.filter_by(user_id=user_id)


def type_label(type_):
    """A readable label for a notification type."""
    if not type_:
        return "Notification"
    if type_ in TYPE_LABELS:
        return TYPE_LABELS[type_]
    text = str(type_).replace("_", " ").strip()
    return text.capitalize() if text else "Notification"


def safe_link(link):
    """Return the link only if it is an internal path, else None.

    Allows "/guardian/dashboard". Rejects "javascript:...", "//host",
    "https://...", backslashes and control characters.
    """
    if not link:
        return None
    text = str(link).strip()
    if not text.startswith("/") or text.startswith("//"):
        return None
    if "\\" in text or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        return None
    return text


def unread_count(user_id):
    return _own(user_id).filter_by(is_read=False).count()


def build_item(notification):
    return {
        "id": notification.id,
        "message": notification.message,
        "type_label": type_label(notification.type),
        "is_read": bool(notification.is_read),
        "created_at": notification.created_at,
        "link": safe_link(notification.link),
    }


def list_page(user_id, page, per_page=PER_PAGE):
    """Return one page of the user's notifications, newest first.

    The page number is clamped to the valid range.
    """
    total = _own(user_id).count()
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page or 1), pages)

    rows = (
        _own(user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
        .all()
    )
    return {
        "items": [build_item(n) for n in rows],
        "page": page,
        "pages": pages,
        "total": total,
        "unread": unread_count(user_id),
    }


def mark_read(user_id, notification_id):
    """Mark one of the user's own notifications as read.

    Returns "ok", "already_read" or "not_found". "not_found" covers both a
    missing notification and someone else's, so the route answers 404 for both.
    """
    notification = _own(user_id).filter_by(id=notification_id).first()
    if notification is None:
        return "not_found"
    if notification.is_read:
        return "already_read"
    notification.is_read = True
    db.session.commit()
    return "ok"


def mark_all_read(user_id):
    """Mark all of the user's unread notifications as read. Returns how many."""
    updated = _own(user_id).filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return updated