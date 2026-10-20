from flask import Blueprint, redirect, render_template
from flask_login import current_user, login_required

from extensions import db
from models import EmergencyRequest, Notification
from services.auth import home_for, role_required
from services.guardian_service import PRESET_LOCATIONS

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/dashboard")
@role_required("user")
def dashboard():
    my_requests = (
        EmergencyRequest.query.filter_by(user_id=current_user.id)
        .order_by(EmergencyRequest.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template("user/dashboard.html", my_requests=my_requests, presets=PRESET_LOCATIONS)


@bp.post("/notifications/read-all")
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(home_for(current_user))
