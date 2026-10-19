from flask import Blueprint, render_template

from services import admin_service
from services.auth import role_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.get("/")
@role_required("admin")
def dashboard():
    return render_template("admin/dashboard.html", stats=admin_service.stats())
