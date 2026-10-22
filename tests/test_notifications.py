"""Tests for Step 2.5: notification center.

Uses the fixtures in tests/conftest.py (app, client, make_user, login).
The navbar badge tests rely on base.html showing unread_count.
"""

from datetime import timedelta

import pytest

from extensions import db
from models import Notification, utcnow
from services import notification_center
from services.notifications import notify

PASSWORD = "Secret@123"  # the default used by the make_user fixture


# ----------------------------------------------------------------- helpers

def add_notification(user, message="Test message", type_="test_event", link=None,
                     is_read=False, minutes_ago=0):
    notification = Notification(
        user_id=user.id, type=type_, message=message, link=link, is_read=is_read,
        created_at=utcnow() - timedelta(minutes=minutes_ago),
    )
    db.session.add(notification)
    db.session.commit()
    return notification


def is_read(notification_id):
    return db.session.get(Notification, notification_id).is_read


def login_as(app, email):
    """A second, independent browser session."""
    other = app.test_client()
    other.post("/login", data={"email": email, "password": PASSWORD})
    return other


def count_items(html, state):
    return html.count(f'class="notification" data-state="{state}"')


# ------------------------------------------------------------ pure helpers

@pytest.mark.parametrize("link,expected", [
    ("/guardian/dashboard", "/guardian/dashboard"),
    ("/sos/12", "/sos/12"),
    ("  /journey/3  ", "/journey/3"),
])
def test_safe_link_accepts_internal_paths(link, expected):
    assert notification_center.safe_link(link) == expected


@pytest.mark.parametrize("link", [
    None, "", "   ", "javascript:alert(1)", "//evil.example.com", "/\\evil.example.com",
    "https://example.com/x", "guardian/dashboard", "/a\nb", "data:text/html,hi",
])
def test_safe_link_rejects_everything_else(link):
    assert notification_center.safe_link(link) is None


@pytest.mark.parametrize("type_,expected", [
    ("sos_created", "SOS request"),
    ("journey_started", "Journey started"),
    ("guardian_approved", "Guardian approved"),
    ("", "Notification"),
    (None, "Notification"),
])
def test_type_label(type_, expected):
    assert notification_center.type_label(type_) == expected


# ------------------------------------------------------------ access control

def test_page_requires_login(client):
    response = client.get("/notifications/")
    assert response.status_code == 302
    assert "login" in response.headers["Location"].lower()


def test_anonymous_cannot_mark_anything_read(client, make_user):
    user = make_user(email="a@example.com")
    notification = add_notification(user)
    assert client.post(f"/notifications/{notification.id}/read").status_code == 302
    assert client.post("/notifications/read-all").status_code == 302
    assert is_read(notification.id) is False


@pytest.mark.parametrize("role", ["user", "guardian", "admin"])
def test_every_role_can_open_their_notifications(client, make_user, login, role):
    user = make_user(email="a@example.com", role=role)
    add_notification(user, message="Hello role test")
    login("a@example.com")
    response = client.get("/notifications/")
    assert response.status_code == 200
    assert "Hello role test" in response.get_data(as_text=True)


def test_mark_actions_reject_get(client, make_user, login):
    user = make_user(email="a@example.com")
    notification = add_notification(user)
    login("a@example.com")
    assert client.get(f"/notifications/{notification.id}/read").status_code == 405
    assert client.get("/notifications/read-all").status_code == 405
    assert is_read(notification.id) is False


# ------------------------------------------------------------------- listing

def test_lists_newest_first(client, make_user, login):
    user = make_user(email="a@example.com")
    add_notification(user, message="Oldest message", minutes_ago=30)
    add_notification(user, message="Newest message", minutes_ago=5)
    add_notification(user, message="Middle message", minutes_ago=20)
    login("a@example.com")
    html = client.get("/notifications/").get_data(as_text=True)
    assert html.index("Newest message") < html.index("Middle message") < html.index("Oldest message")


def test_shows_only_own_notifications(client, make_user, login):
    mine = make_user(email="mine@example.com")
    other = make_user(email="other@example.com")
    add_notification(mine, message="My own message")
    add_notification(other, message="Someone elses secret")
    login("mine@example.com")
    html = client.get("/notifications/").get_data(as_text=True)
    assert "My own message" in html
    assert "Someone elses secret" not in html


def test_read_and_unread_are_styled_and_labelled(client, make_user, login):
    user = make_user(email="a@example.com")
    add_notification(user, message="Fresh one", is_read=False)
    add_notification(user, message="Fresh two", is_read=False)
    add_notification(user, message="Old one", is_read=True)
    login("a@example.com")
    response = client.get("/notifications/")
    html = response.get_data(as_text=True)
    assert count_items(html, "unread") == 2
    assert count_items(html, "read") == 1
    assert html.count(">Unread</span>") == 2
    assert "You have 2 unread notifications." in html
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_empty_state(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    html = client.get("/notifications/").get_data(as_text=True)
    assert "You have no notifications yet." in html
    assert "Mark all as read" not in html


def test_page_has_honest_demo_status(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    html = client.get("/notifications/").get_data(as_text=True)
    assert "No SMS, call or" in html
    assert "police notified" not in html.lower()


def test_message_text_is_escaped(client, make_user, login):
    user = make_user(email="a@example.com")
    add_notification(user, message="<script>alert(1)</script>")
    login("a@example.com")
    html = client.get("/notifications/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_only_safe_links_become_open_buttons(client, make_user, login):
    user = make_user(email="a@example.com")
    add_notification(user, message="Good link", link="/guardian/dashboard")
    add_notification(user, message="Script link", link="javascript:alert(1)")
    add_notification(user, message="Protocol relative", link="//evil.example.com")
    login("a@example.com")
    html = client.get("/notifications/").get_data(as_text=True)
    assert 'href="/guardian/dashboard"' in html
    assert 'href="javascript:' not in html
    assert 'href="//evil' not in html


def test_notification_created_by_notify_appears(client, make_user, login):
    user = make_user(email="a@example.com")
    notify(user.id, "demo_event", "Hello via notify", "/dashboard", commit=False)
    db.session.commit()
    login("a@example.com")
    html = client.get("/notifications/").get_data(as_text=True)
    assert "Hello via notify" in html and "Demo event" in html


# ---------------------------------------------------------------- pagination

def test_pagination_splits_and_clamps(client, make_user, login):
    user = make_user(email="a@example.com")
    total = notification_center.PER_PAGE + 5
    for i in range(total):
        add_notification(user, message=f"Item {i:02d}", minutes_ago=i)
    login("a@example.com")

    first = client.get("/notifications/").get_data(as_text=True)
    assert count_items(first, "unread") == notification_center.PER_PAGE
    assert "Item 00" in first and "Item 24" not in first
    assert "Page 1 of 2" in first and "Older" in first and "Newer" not in first

    second = client.get("/notifications/?page=2").get_data(as_text=True)
    assert count_items(second, "unread") == 5
    assert "Item 24" in second and "Item 00" not in second
    assert "Newer" in second and "Older" not in second

    last = client.get("/notifications/?page=999").get_data(as_text=True)
    assert "Page 2 of 2" in last
    assert "Page 1 of 2" in client.get("/notifications/?page=0").get_data(as_text=True)
    assert "Page 1 of 2" in client.get("/notifications/?page=abc").get_data(as_text=True)


# ------------------------------------------------------------- mark as read

def test_mark_one_as_read(client, make_user, login):
    user = make_user(email="a@example.com")
    target = add_notification(user, message="Target")
    untouched = add_notification(user, message="Untouched")
    login("a@example.com")

    response = client.post(f"/notifications/{target.id}/read")
    assert response.status_code == 302
    assert is_read(target.id) is True
    assert is_read(untouched.id) is False


def test_marking_twice_is_harmless(client, make_user, login):
    user = make_user(email="a@example.com")
    target = add_notification(user)
    login("a@example.com")
    assert client.post(f"/notifications/{target.id}/read").status_code == 302
    assert client.post(f"/notifications/{target.id}/read").status_code == 302
    assert is_read(target.id) is True


def test_mark_read_returns_to_the_same_page(client, make_user, login):
    user = make_user(email="a@example.com")
    target = add_notification(user)
    login("a@example.com")
    response = client.post(f"/notifications/{target.id}/read", data={"page": "2"})
    assert response.headers["Location"].endswith("/notifications/?page=2")
    response = client.post(f"/notifications/{target.id}/read", data={"page": "abc"})
    assert response.headers["Location"].endswith("/notifications/?page=1")


def test_user_cannot_mark_another_users_notification(app, client, make_user, login):
    owner = make_user(email="owner@example.com")
    make_user(email="intruder@example.com")
    notification = add_notification(owner, message="Owners private note")

    login("intruder@example.com")
    assert client.post(f"/notifications/{notification.id}/read").status_code == 404
    assert is_read(notification.id) is False

    owner_client = login_as(app, "owner@example.com")
    assert owner_client.post(f"/notifications/{notification.id}/read").status_code == 302
    assert is_read(notification.id) is True


def test_unknown_notification_is_404(client, make_user, login):
    make_user(email="a@example.com")
    login("a@example.com")
    assert client.post("/notifications/99999/read").status_code == 404


# ------------------------------------------------------------ mark all read

def test_mark_all_read_changes_only_own_notifications(client, make_user, login):
    mine = make_user(email="mine@example.com")
    other = make_user(email="other@example.com")
    my_first = add_notification(mine, message="Mine one")
    my_second = add_notification(mine, message="Mine two")
    theirs = add_notification(other, message="Theirs")

    login("mine@example.com")
    response = client.post("/notifications/read-all")
    assert response.status_code == 302
    assert is_read(my_first.id) is True and is_read(my_second.id) is True
    assert is_read(theirs.id) is False


def test_mark_all_read_with_nothing_unread_is_harmless(client, make_user, login):
    user = make_user(email="a@example.com")
    add_notification(user, is_read=True)
    login("a@example.com")
    assert client.post("/notifications/read-all").status_code == 302


# ------------------------------------------------------------------- CSRF

def test_csrf_token_is_required_on_both_actions(app, client, make_user, login):
    user = make_user(email="a@example.com")
    notification = add_notification(user)
    login("a@example.com")
    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post(f"/notifications/{notification.id}/read").status_code == 400
    assert client.post("/notifications/read-all").status_code == 400
    assert is_read(notification.id) is False


def test_forms_carry_a_csrf_token(client, make_user, login):
    user = make_user(email="a@example.com")
    add_notification(user)
    login("a@example.com")
    html = client.get("/notifications/").get_data(as_text=True)
    assert html.count('name="csrf_token"') >= 2   # mark-all form + one item form


# ------------------------------------------------------------ navbar badge

def test_navbar_badge_matches_unread_count_and_clears(client, make_user, login):
    user = make_user(email="a@example.com")
    other = make_user(email="other@example.com")
    for i in range(3):
        add_notification(user, message=f"Unread {i}")
    add_notification(user, message="Already read", is_read=True)
    add_notification(other, message="Not mine")  # must not be counted

    login("a@example.com")
    html = client.get("/notifications/").get_data(as_text=True)
    assert 'notif-badge ms-1">3</span>' in html
    assert 'href="/notifications/"' in html

    client.post("/notifications/read-all")
    html = client.get("/notifications/").get_data(as_text=True)
    assert "notif-badge" not in html


def test_badge_count_helper(make_user):
    user = make_user(email="a@example.com")
    add_notification(user)
    add_notification(user, is_read=True)
    assert notification_center.unread_count(user.id) == 1