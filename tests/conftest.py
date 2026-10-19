import pytest
from flask import g

from app import create_app
from config import TestConfig
from extensions import db
from models import User


@pytest.fixture
def app():
    app = create_app(TestConfig)

    @app.before_request
    def forget_cached_login():
        # The test keeps one app context open, so Flask-Login would otherwise
        # remember the previous request's user. This makes each request independent,
        # like a real browser, so several test clients can be used in one test.
        g.pop("_login_user", None)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    """Factory: make_user(email=..., role=...) creates and saves a user."""

    def _make(email="user@example.com", password="Secret@123", role="user", name="Test User"):
        user = User(name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    return _make


@pytest.fixture
def login(client):
    """login(email) logs the test client in through the real login form."""

    def _login(email, password="Secret@123"):
        return client.post("/login", data={"email": email, "password": password})

    return _login
