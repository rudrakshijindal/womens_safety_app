from flask import Blueprint, flash, redirect, render_template, request, url_for

from services import admin_service
from services.auth import role_required
from services.guardian_service import PRESET_LOCATIONS

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/")
@role_required("admin")
def dashboard():
    return render_template("admin/dashboard.html", stats=admin_service.stats())


@bp.get("/applications")
@role_required("admin")
def applications():
    return render_template(
        "admin/applications.html",
        pending=admin_service.pending_applications(),
        decided=admin_service.recent_decisions(),
    )


@bp.post("/applications/<int:profile_id>/<decision>")
@role_required("admin")
def decide(profile_id, decision):
    profile = admin_service.decide_application(profile_id, decision)
    if profile is None:
        flash("That application could not be updated. It may already be decided.", "warning")
    else:
        flash(f"{profile.user.name}'s application was {profile.status}.", "success")
    return redirect(url_for("admin.applications"))


@bp.get("/guardians")
@role_required("admin")
def guardians():
    return render_template("admin/guardians.html", profiles=admin_service.all_guardians())


@bp.get("/users")
@role_required("admin")
def users():
    return render_template("admin/users.html", users=admin_service.all_users())


@bp.get("/requests")
@role_required("admin")
def requests():
    return render_template(
        "admin/requests.html",
        requests=admin_service.all_requests(),
        users=[u for u in admin_service.all_users() if u.role == "user"],
        presets=PRESET_LOCATIONS,
    )


@bp.post("/demo-emergency")
@role_required("admin")
def demo_emergency():
    try:
        user_id = int(request.form.get("user_id", ""))
    except ValueError:
        user_id = 0
    req, matches = admin_service.create_demo_request(user_id, request.form.get("preset", ""))
    if req is None:
        flash("Choose a user and a location to create the demo emergency.", "danger")
    elif matches:
        names = ", ".join(f"{m['name']} ({m['distance_km']} km)" for m in matches)
        flash(f"Demo emergency #{req.id} created. Matched nearest first: {names}.", "success")
    else:
        flash(f"Demo emergency #{req.id} created, but no guardian is on duty nearby.", "warning")
    return redirect(url_for("admin.requests"))
