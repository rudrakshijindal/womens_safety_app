import click
from flask import Flask

from config import Config
from extensions import csrf, db, login_manager


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # created in Phase 2
    login_manager.login_message_category = "warning"

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.cli.command("init-db")
    def init_db():
        """Create all database tables."""
        db.create_all()
        click.echo("Database tables created.")

    @app.get("/")
    def index():
        # Temporary page so you can see the server running. Replaced in Phase 2.
        return "Women's Safety & Emergency Response System - academic prototype (Phase 1 OK)"

    return app


if __name__ == "__main__":
    create_app().run(debug=True)