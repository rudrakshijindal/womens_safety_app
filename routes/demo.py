"""Demo stand-ins so the guardian network can be shown without the SOS module.

Teammate 2's SOS feature replaces `emergency` (it should call find_eligible_guardians and
dispatch_to_guardians directly). Kept in its own file so it never touches their routes.
"""
from flask import Blueprint, abort, flash, redirect, request, url_for
from flask_login import current_user

from extensions import db
from models import EmergencyRequest, RequestMatch
from services import admin_service
from services.auth import role_required
from services.guardian_service import PRESET_LOCATIONS
from services.notifications import notify

bp = Blueprint("demo", __name__, url_prefix="/demo")

ACTIVE = ("pending", "accepted")


@bp.post("/emergency")
@role_required("user")
def emergency():
    preset = request.form.get("preset", "")
    if preset not in PRESET_LOCATIONS:
        flash("Please choose one of the simulated locations.", "warning")
        return redirect(url_for("main.dashboard"))

    open_request = EmergencyRequest.query.filter(
        EmergencyRequest.user_id == current_user.id, EmergencyRequest.status.in_(ACTIVE)
    ).first()
    if open_request:
        flash("You already have an open request. Wait for it to finish or cancel it first.", "info")
        return redirect(url_for("main.dashboard"))

    req, matches = admin_service.create_demo_request(current_user.id, preset)
    if req is None:
        abort(400)
    if matches:
        flash(f"Demo alert created. {len(matches)} nearby guardian(s) were notified in-app.", "success")
    else:
        flash("Demo alert created, but no approved guardian is on duty nearby right now.", "warning")
    return redirect(url_for("main.dashboard"))


@bp.post("/requests/<int:request_id>/cancel")
@role_required("user")
def cancel(request_id):
    req = db.session.get(EmergencyRequest, request_id)
    if req is None or req.user_id != current_user.id:
        abort(404)
    if req.status != "pending":
        flash("Only a request that nobody has accepted yet can be cancelled.", "warning")
        return redirect(url_for("main.dashboard"))

    req.status = "cancelled"
    for m in RequestMatch.query.filter_by(request_id=req.id).all():
        notify(m.guardian_id, "request_cancelled", f"Request #{req.id} was cancelled by the requester.",
               "/guardian/dashboard", commit=False)
    db.session.commit()
    flash("Request cancelled.", "success")
    return redirect(url_for("main.dashboard"))
