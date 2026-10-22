from datetime import timedelta

import click
from flask import Flask, current_app, render_template
from flask_login import current_user

from config import Config
from extensions import csrf, db, login_manager

APP_NAME = "SafeCircle"  # rename the whole site here

ERROR_TEXT = {
    400: ("Something went wrong with that request",
          "Your form may have expired. Go back, refresh the page and try again."),
    403: ("Access denied", "Your account does not have permission to open this page."),
    404: ("Page not found", "We could not find the page you were looking for."),
}


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "warning"

    from models import Notification, User, utcnow

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ---- blueprints ----
    from routes.admin import bp as admin_bp
    from routes.auth import bp as auth_bp
    from routes.demo import bp as demo_bp
    from routes.guardian import bp as guardian_bp
    from routes.journey import bp as journey_bp                  # Step 2.4
    from routes.main import bp as main_bp
    from routes.notifications import bp as notifications_bp    # Step 2.5
    from routes.sos import bp as sos_bp                          # Step 2.3

    for blueprint in (
        main_bp, auth_bp, guardian_bp, admin_bp, demo_bp,
        sos_bp, journey_bp, notifications_bp,
    ):
        app.register_blueprint(blueprint)

    # ---- template helpers ----
    @app.context_processor
    def inject_globals():
        data = {
            "app_name": APP_NAME,
            "endpoint_exists": lambda name: name in current_app.view_functions,
            "unread_count": 0,
            "recent_notifications": [],
        }
        if current_user.is_authenticated:
            query = Notification.query.filter_by(user_id=current_user.id)
            data["unread_count"] = query.filter_by(is_read=False).count()
            data["recent_notifications"] = (
                query.order_by(Notification.created_at.desc()).limit(6).all()
            )
        return data

    @app.template_filter("ist")
    def ist(dt):
        """Show a UTC timestamp in Indian Standard Time."""
        if not dt:
            return "-"
        return (dt + timedelta(hours=5, minutes=30)).strftime("%d %b %Y, %I:%M %p")

    @app.template_filter("ago")
    def ago(dt):
        if not dt:
            return ""
        secs = int((utcnow() - dt).total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{secs // 60} min ago"
        if secs < 86400:
            return f"{secs // 3600} h ago"
        return f"{secs // 86400} d ago"

    # ---- error pages ----
    def show_error(err):
        code = getattr(err, "code", 500) or 500
        title, message = ERROR_TEXT.get(code, ("Something went wrong", "Please try again."))
        return render_template("error.html", code=code, title=title, message=message), code

    for code in ERROR_TEXT:
        app.register_error_handler(code, show_error)

    # ---- CLI ----
    @app.cli.command("init-db")
    def init_db():
        """Create all database tables."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Admin name")
    @click.option("--email", prompt="Admin email")
    @click.password_option(prompt="Password")
    def create_admin(name, email, password):
        """Create an admin account. Admins can only be created here (or by the seed script)."""
        from services.validators import EMAIL_RE

        email = email.strip().lower()
        if not EMAIL_RE.match(email):
            raise click.ClickException("That email address is not valid.")
        if len(password) < 8:
            raise click.ClickException("Password must be at least 8 characters.")
        if User.query.filter_by(email=email).first():
            raise click.ClickException("An account with that email already exists.")
        admin = User(name=name.strip(), email=email, role="admin")
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"Admin account created for {email}.")

    return app


if __name__ == "__main__":
    create_app().run(debug=True)