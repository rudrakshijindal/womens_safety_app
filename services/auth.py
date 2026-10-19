from functools import wraps

from flask import abort, flash, redirect, url_for
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


def approved_guardian_required(fn):
    """Guardian role AND approved by an admin.

    A pending or rejected guardian is sent to their status page instead.
    """

    @role_required("guardian")
    @wraps(fn)
    def wrapper(*args, **kwargs):
        profile = current_user.guardian_profile
        if profile is None or profile.status != "approved":
            flash("Your guardian account is not approved yet, so that page is locked.", "warning")
            return redirect(url_for("guardian.status"))
        return fn(*args, **kwargs)

    return wrapper


def home_for(user):
    """Where each role lands after login."""
    if user.role == "admin":
        return url_for("admin.dashboard")
    if user.role == "guardian":
        profile = user.guardian_profile
        if profile is not None and profile.status == "approved":
            return url_for("guardian.dashboard")
        return url_for("guardian.status")
    return url_for("main.dashboard")
