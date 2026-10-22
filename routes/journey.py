from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from services import journey_service
from services.auth import role_required

bp = Blueprint("journey", __name__, url_prefix="/journey")


@bp.after_request
def no_store(response):
    """Journey pages contain location data: ask browsers not to cache them."""
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/")
@role_required("user")
def index():
    return render_template(
        "journey/index.html",
        active=journey_service.get_active_journey(current_user.id),
        values={},
        errors={},
    )


@bp.route("/start", methods=["POST"])
@role_required("user")
def start():
    journey, created, values, errors = journey_service.start_journey(
        current_user.id, request.form
    )
    if errors:
        flash("The journey was not started. Please fix the problems below.", "danger")
        return (
            render_template(
                "journey/index.html", active=None, values=values, errors=errors
            ),
            400,
        )

    if created:
        flash(
            "Journey started (demo). Your trusted contacts are not notified "
            "and no SMS or call is sent.",
            "success",
        )
    else:
        flash("You already have a journey in progress, so no new one was started.", "info")
    return redirect(url_for("journey.detail", journey_id=journey.id))


@bp.route("/history")
@role_required("user")
def history():
    return render_template(
        "journey/history.html",
        rows=journey_service.list_completed(current_user.id),
        limit=journey_service.HISTORY_LIMIT,
    )


@bp.route("/<int:journey_id>")
@role_required("user")
def detail(journey_id):
    # 404 for both "does not exist" and "belongs to someone else".
    journey = journey_service.get_owned_journey(current_user.id, journey_id)
    if journey is None:
        abort(404)
    return render_template(
        "journey/detail.html",
        journey=journey,
        view=journey_service.build_journey_view(journey),
    )


@bp.route("/<int:journey_id>/end", methods=["POST"])
@role_required("user")
def end(journey_id):
    result, _journey = journey_service.end_journey(current_user.id, journey_id)
    if result == "not_found":
        abort(404)
    if result == "already_ended":
        flash("This journey was already completed.", "info")
    else:
        flash("Journey completed (demo). Nothing was sent to your contacts.", "success")
    return redirect(url_for("journey.detail", journey_id=journey_id))