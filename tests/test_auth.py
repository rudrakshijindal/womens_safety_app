from config import TestConfig
from extensions import db
from app import create_app
from models import User


def register(client, **overrides):
    data = {
        "name": "Riya Sharma",
        "email": "riya@example.com",
        "phone": "9876543210",
        "password": "Secret@123",
        "confirm_password": "Secret@123",
    }
    data.update(overrides)
    return client.post("/register", data=data)


def test_register_creates_user_role(client):
    response = register(client)
    assert response.status_code == 302
    user = User.query.filter_by(email="riya@example.com").one()
    assert user.role == "user"


def test_password_is_not_stored_in_plaintext(client):
    register(client)
    user = User.query.filter_by(email="riya@example.com").one()
    assert user.password_hash != "Secret@123"
    assert "Secret@123" not in user.password_hash
    assert user.check_password("Secret@123")


def test_user_cannot_self_assign_admin_by_editing_the_form(client):
    response = register(client, role="admin")
    assert response.status_code == 302
    user = User.query.filter_by(email="riya@example.com").one()
    assert user.role == "user"
    assert client.get("/admin/").status_code == 403


def test_register_page_has_no_role_field(client):
    html = client.get("/register").get_data(as_text=True)
    assert 'name="role"' not in html


def test_duplicate_email_is_rejected(client):
    register(client)
    client.post("/logout")
    response = register(client)
    assert response.status_code == 400
    assert b"already exists" in response.data
    assert User.query.filter_by(email="riya@example.com").count() == 1


def test_validation_messages(client):
    assert b"valid email" in register(client, email="not-an-email").data
    assert b"at least 8 characters" in register(client, email="a@b.com", password="short", confirm_password="short").data
    assert b"do not match" in register(client, email="c@d.com", confirm_password="Different@1").data
    assert b"10-digit" in register(client, email="e@f.com", phone="12345").data


def test_login_success_and_wrong_password(client, make_user, login):
    make_user("login@example.com")
    bad = login("login@example.com", "wrong-password")
    assert bad.status_code == 401
    assert b"Incorrect email or password" in bad.data
    good = login("login@example.com")
    assert good.status_code == 302
    assert good.headers["Location"].endswith("/dashboard")


def test_login_next_cannot_redirect_to_other_sites(client, make_user):
    make_user("next@example.com")
    response = client.post(
        "/login?next=https://evil.example.com",
        data={"email": "next@example.com", "password": "Secret@123"},
    )
    assert response.headers["Location"].endswith("/dashboard")


def test_anonymous_user_is_sent_to_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_normal_user_gets_403_on_admin_url(client, make_user, login):
    make_user("plain@example.com")
    login("plain@example.com")
    assert client.get("/admin/").status_code == 403


def test_admin_can_open_admin_dashboard(client, make_user, login):
    make_user("boss@example.com", role="admin", name="Admin")
    login("boss@example.com")
    assert client.get("/admin/").status_code == 200


def test_logout_requires_post(client, make_user, login):
    make_user("out@example.com")
    login("out@example.com")
    assert client.get("/logout").status_code == 405
    assert client.post("/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_csrf_blocks_forms_without_token():
    class CsrfConfig(TestConfig):
        WTF_CSRF_ENABLED = True

    app = create_app(CsrfConfig)
    with app.app_context():
        db.create_all()
        client = app.test_client()
        response = client.post("/login", data={"email": "a@b.com", "password": "x"})
        assert response.status_code == 400
        db.session.remove()
        db.drop_all()
