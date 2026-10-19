from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db
from models import User
from services.auth import home_for
from services.validators import validate_account_form

bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Only allow redirects to paths on this site (blocks open-redirect tricks)."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))

    if request.method == "POST":
        form = request.form
        errors = validate_account_form(form)
        email = (form.get("email") or "").strip().lower()
        if not errors and User.query.filter_by(email=email).first():
            errors.append("An account with this email already exists. Try logging in instead.")
        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template("auth/register.html", form=form), 400

        # The role is fixed here on the server. Any "role" field in the form is ignored.
        user = User(
            name=form["name"].strip(),
            email=email,
            phone=(form.get("phone") or "").strip() or None,
            role="user",
        )
        user.set_password(form["password"])
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Welcome! Your account has been created.", "success")
        return redirect(home_for(user))

    return render_template("auth/register.html", form={})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(password):
            flash("Incorrect email or password.", "danger")
            return render_template("auth/login.html", form=request.form), 401
        login_user(user)
        flash(f"Welcome back, {user.name.split()[0]}!", "success")
        return redirect(_safe_next(request.args.get("next")) or home_for(user))

    return render_template("auth/login.html", form={})


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))
