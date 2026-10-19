from flask import Blueprint, flash, redirect, render_template, url_for

from services import admin_service
from services.auth import role_required

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
