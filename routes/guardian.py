from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user

from models import User
from services import guardian_service
from services.auth import approved_guardian_required, home_for, role_required
from services.validators import validate_guardian_form

bp = Blueprint("guardian", __name__, url_prefix="/guardian")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))

    if request.method == "POST":
        form = request.form
        errors = validate_guardian_form(form)
        email = (form.get("email") or "").strip().lower()
        if not errors and User.query.filter_by(email=email).first():
            errors.append("An account with this email already exists. Try logging in instead.")
        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template("guardian/register.html", form=form), 400

        # Role and status are fixed on the server. Nothing in the form can change them.
        user = guardian_service.create_guardian_application(form)
        login_user(user)
        flash("Application submitted. An admin will review it.", "success")
        return redirect(url_for("guardian.status"))

    return render_template("guardian/register.html", form={})


@bp.get("/status")
@role_required("guardian")
def status():
    return render_template("guardian/status.html", profile=current_user.guardian_profile)


@bp.get("/dashboard")
@approved_guardian_required
def dashboard():
    return render_template(
        "guardian/dashboard.html",
        profile=current_user.guardian_profile,
        presets=guardian_service.PRESET_LOCATIONS,
    )


@bp.post("/location")
@approved_guardian_required
def location():
    profile = current_user.guardian_profile
    preset = (request.form.get("preset") or "").strip()

    if preset:
        if preset not in guardian_service.PRESET_LOCATIONS:
            flash("Please choose a location from the list.", "danger")
            return redirect(url_for("guardian.dashboard"))
        label, lat, lng = guardian_service.PRESET_LOCATIONS[preset]
        guardian_service.set_location(profile, lat, lng, simulated=True)
        flash(f"Location set to {label} (simulated).", "success")
    else:
        try:
            lat, lng = guardian_service.parse_coordinates(
                request.form.get("latitude"), request.form.get("longitude")
            )
        except ValueError as error:
            flash(str(error), "danger")
            return redirect(url_for("guardian.dashboard"))
        simulated = request.form.get("source") != "device"
        guardian_service.set_location(profile, lat, lng, simulated=simulated)
        flash("Location saved.", "success")
    return redirect(url_for("guardian.dashboard"))


@bp.post("/duty")
@approved_guardian_required
def duty():
    ok, message = guardian_service.toggle_duty(current_user.guardian_profile)
    flash(message, "success" if ok else "warning")
    return redirect(url_for("guardian.dashboard"))
