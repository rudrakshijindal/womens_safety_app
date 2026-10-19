import pytest

from extensions import db
from models import GuardianProfile
from services.matching import find_eligible_guardians, haversine_km

# a request point in Ghaziabad
LAT, LNG = 28.6692, 77.4538


@pytest.fixture
def make_guardian(make_user):
    counter = {"n": 0}

    def _make(status="approved", on_duty=True, lat=28.6700, lng=77.4450, name=None):
        counter["n"] += 1
        user = make_user(f"g{counter['n']}@example.com", role="guardian", name=name or f"Guardian {counter['n']}")
        db.session.add(
            GuardianProfile(
                user_id=user.id, organisation="NGO", id_proof_note="Aadhaar 1234",
                status=status, on_duty=on_duty, latitude=lat, longitude=lng,
            )
        )
        db.session.commit()
        return user

    return _make


def test_haversine_known_distance():
    # Delhi to Mumbai is about 1,150 km in a straight line
    assert 1140 < haversine_km(28.6139, 77.2090, 19.0760, 72.8777) < 1160


def test_haversine_same_point_is_zero():
    assert haversine_km(LAT, LNG, LAT, LNG) == pytest.approx(0)


def test_nearest_guardian_comes_first(make_guardian):
    far = make_guardian(name="Far", lat=28.6460, lng=77.3220)
    near = make_guardian(name="Near", lat=28.6700, lng=77.4450)
    mid = make_guardian(name="Mid", lat=28.6460, lng=77.3690)

    results = find_eligible_guardians(LAT, LNG)
    assert [r["name"] for r in results] == ["Near", "Mid", "Far"]
    assert results[0]["distance_km"] < results[1]["distance_km"] < results[2]["distance_km"]
    assert results[0]["guardian_id"] == near.id


def test_only_approved_on_duty_guardians_with_location_are_matched(make_guardian):
    ok = make_guardian(name="Eligible")
    make_guardian(name="Off duty", on_duty=False)
    make_guardian(name="Pending", status="pending")
    make_guardian(name="Rejected", status="rejected")
    make_guardian(name="No location", lat=None, lng=None)

    results = find_eligible_guardians(LAT, LNG)
    assert [r["name"] for r in results] == ["Eligible"]
    assert results[0]["guardian_id"] == ok.id


def test_limit_is_respected(make_guardian):
    for _ in range(4):
        make_guardian()
    assert len(find_eligible_guardians(LAT, LNG, limit=2)) == 2
    assert len(find_eligible_guardians(LAT, LNG, limit=0)) == 0


def test_result_never_exposes_exact_coordinates(make_guardian):
    make_guardian()
    result = find_eligible_guardians(LAT, LNG)[0]
    assert "latitude" not in result and "longitude" not in result
    assert set(result) == {"guardian_id", "name", "organisation", "distance_km", "location_is_simulated"}


def test_no_guardians_gives_empty_list(app):
    assert find_eligible_guardians(LAT, LNG) == []
