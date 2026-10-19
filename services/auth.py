from functools import wraps

from flask import abort, url_for
from flask_login import current_user

from extensions import login_manager


def role_required(role):
    """Allow only logged-in users with the given role.

    Anonymous visitors are redirected to the login page.
    A logged-in user with the wrong role gets a 403 error.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role != role:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def home_for(user):
    """Where each role lands after login. Guardian is added in Phase 3."""
    if user.role == "admin":
        return url_for("admin.dashboard")
    return url_for("main.dashboard")
