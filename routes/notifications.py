from flask import Blueprint, abort, flash, redirect, request, render_template, url_for
from flask_login import current_user, login_required

from services import notification_center

bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@bp.after_request
def no_store(response):
    """Notifications are personal: ask browsers not to cache them."""
    response.headers["Cache-Control"] = "no-store"
    return response


def _page_from_form():
    """The page number sent by the form, so the user returns to the same page."""
    try:
        return max(1, int(request.form.get("page", "1")))
    except (TypeError, ValueError):
        return 1


@bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    data = notification_center.list_page(current_user.id, page)
    return render_template("notifications.html", **data)


@bp.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    # 404 for both "does not exist" and "belongs to someone else".
    result = notification_center.mark_read(current_user.id, notification_id)
    if result == "not_found":
        abort(404)
    if result == "ok":
        flash("Notification marked as read.", "success")
    return redirect(url_for("notifications.index", page=_page_from_form()))


@bp.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    count = notification_center.mark_all_read(current_user.id)
    if count:
        flash(f"Marked {count} notification{'' if count == 1 else 's'} as read.", "success")
    else:
        flash("You had no unread notifications.", "info")
    return redirect(url_for("notifications.index", page=_page_from_form()))