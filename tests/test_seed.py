from models import GuardianProfile, User
from scripts.seed_demo import ADMIN, DEMO_PASSWORD, seed
from services.matching import find_eligible_guardians


def test_seed_creates_expected_accounts(app):
    created = seed()
    assert created == {"admin": 1, "users": 2, "guardians": 5}
    assert User.query.filter_by(role="admin").count() == 1
    assert User.query.filter_by(role="user").count() == 2
    assert GuardianProfile.query.filter_by(status="approved").count() == 4
    assert GuardianProfile.query.filter_by(status="pending").count() == 1
    assert GuardianProfile.query.filter_by(status="approved", on_duty=True).count() == 3


def test_seed_can_run_twice_without_duplicates(app):
    seed()
    again = seed()
    assert again == {"admin": 0, "users": 0, "guardians": 0}
    assert User.query.count() == 8


def test_seed_accounts_can_log_in_and_locations_are_simulated(app):
    seed()
    client = app.test_client()
    response = client.post("/login", data={"email": ADMIN[1], "password": DEMO_PASSWORD})
    assert response.headers["Location"].endswith("/admin/")
    assert all(p.location_is_simulated for p in GuardianProfile.query.all())


def test_seeded_guardians_are_matched_nearest_first(app):
    seed()
    results = find_eligible_guardians(28.6700, 77.4450)  # Raj Nagar
    names = [r["name"] for r in results]
    assert names[0] == "Priya Verma [SAMPLE]"
    assert len(names) == 3  # off-duty Kaushambi guardian is skipped, pending one has no location
    assert [r["distance_km"] for r in results] == sorted(r["distance_km"] for r in results)


def test_seed_reset_wipes_old_data(app, make_user):
    make_user("old@example.com")
    seed(reset=True)
    assert User.query.filter_by(email="old@example.com").count() == 0
    assert User.query.count() == 8
