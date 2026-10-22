from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from services import sos_service
from services.auth import role_required

bp = Blueprint("sos", __name__, url_prefix="/sos")


@bp.after_request
def no_store(response):
    """SOS pages contain location data: ask browsers not to cache them."""
    response.headers["Cache-Control"] = "no-store"
    return response


def _render_index(status_code=200):
    return (
        render_template(
            "sos/index.html",
            recent=sos_service.list_user_requests(current_user.id),
            helplines=sos_service.HELPLINES,
        ),
        status_code,
    )


@bp.route("/")
@role_required("user")
def index():
    return _render_index()


@bp.route("/create", methods=["POST"])
@role_required("user")
def create():
    emergency, created, error = sos_service.create_sos_request(
        current_user.id, request.form
    )
    if error:
        flash(error, "danger")
        return _render_index(400)

    if created:
        flash(
            "SOS request created in the app (demo). "
            "No SMS, call or police alert was sent.",
            "success",
        )
    else:
        flash(
            "You already raised an SOS request moments ago, so no duplicate was created.",
            "info",
        )
    return redirect(url_for("sos.detail", request_id=emergency.id))


@bp.route("/<int:request_id>")
@role_required("user")
def detail(request_id):
    # 404 for both "does not exist" and "belongs to someone else".
    emergency = sos_service.get_owned_request(current_user.id, request_id)
    if emergency is None:
        abort(404)
    return render_template(
        "sos/detail.html",
        emergency=emergency,
        view=sos_service.build_request_view(emergency),
        helplines=sos_service.HELPLINES,
    )