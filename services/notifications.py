from extensions import db
from models import Notification


def notify(user_id, type, message, link=None, commit=True):
    """Store an in-app notification for a user.

    This is an in-app record only. No SMS, call or push message is sent.
    """
    note = Notification(user_id=user_id, type=type, message=message[:300], link=link)
    db.session.add(note)
    if commit:
        db.session.commit()
    return note