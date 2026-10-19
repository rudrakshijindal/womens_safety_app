"""Create demo data for the live demonstration.

Run from the project folder (virtual environment active):

    python -m scripts.seed_demo            adds the demo accounts that are missing
    python -m scripts.seed_demo --reset    wipes ALL data first, then adds the demo accounts

The guardians below are SAMPLE accounts with SIMULATED locations (Ghaziabad areas).
They are not real people. Every demo account uses the same password, printed at the end.
"""
import sys

from app import create_app
from extensions import db
from models import GuardianProfile, User, utcnow
from services.guardian_service import PRESET_LOCATIONS

DEMO_PASSWORD = "Demo@1234"

ADMIN = ("Demo Admin", "admin@safecircle.demo")

USERS = [
    ("Riya Sharma", "riya@safecircle.demo", "9876500001"),
    ("Ananya Gupta", "ananya@safecircle.demo", "9876500002"),
]

# name, email, phone, organisation, preset area, status, on_duty
GUARDIANS = [
    ("Priya Verma [SAMPLE]", "priya@safecircle.demo", "9876500011", "Sample NGO - Raj Nagar", "raj_nagar", "approved", True),
    ("Neha Singh [SAMPLE]", "neha@safecircle.demo", "9876500012", "Sample College Volunteers", "indirapuram", "approved", True),
    ("Pooja Mishra [SAMPLE]", "pooja@safecircle.demo", "9876500013", "Sample Resident Welfare Group", "vaishali", "approved", True),
    ("Sunita Yadav [SAMPLE]", "sunita@safecircle.demo", "9876500014", "Sample NGO - Kaushambi", "kaushambi", "approved", False),
    ("Kavita Rao [SAMPLE]", "kavita@safecircle.demo", "9876500015", "Sample Youth Club", None, "pending", False),
]


def _add_user(name, email, role, phone=None):
    """Create the user if the email is free. Returns (user, created)."""
    existing = User.query.filter_by(email=email).first()
    if existing:
        return existing, False
    user = User(name=name, email=email, role=role, phone=phone)
    user.set_password(DEMO_PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user, True


def seed(reset=False):
    """Insert demo data. Returns a dict of how many accounts of each kind were created."""
    if reset:
        db.drop_all()
    db.create_all()

    created = {"admin": 0, "users": 0, "guardians": 0}

    _, made = _add_user(ADMIN[0], ADMIN[1], "admin")
    created["admin"] += int(made)

    for name, email, phone in USERS:
        _, made = _add_user(name, email, "user", phone)
        created["users"] += int(made)

    for name, email, phone, organisation, area, status, on_duty in GUARDIANS:
        user, made = _add_user(name, email, "guardian", phone)
        if not made:
            continue
        profile = GuardianProfile(
            user_id=user.id,
            organisation=organisation,
            id_proof_note="Sample record, no real ID",
            reason="Sample guardian for the demo",
            status=status,
            on_duty=on_duty,
            location_is_simulated=True,
        )
        if area:
            _, lat, lng = PRESET_LOCATIONS[area]
            profile.latitude, profile.longitude = lat, lng
        if status == "approved":
            profile.approved_at = utcnow()
        db.session.add(profile)
        created["guardians"] += 1

    db.session.commit()
    return created


def main(argv):
    reset = "--reset" in argv
    if reset and "--yes" not in argv:
        answer = input("--reset will DELETE ALL DATA in the database. Type YES to continue: ")
        if answer.strip() != "YES":
            print("Cancelled. Nothing was changed.")
            return 1

    app = create_app()
    with app.app_context():
        created = seed(reset=reset)

    print()
    print(f"Created: {created['admin']} admin, {created['users']} users, {created['guardians']} guardians.")
    print(f"All demo accounts use the password: {DEMO_PASSWORD}")
    print()
    print("Role      Email")
    print(f"admin     {ADMIN[1]}")
    for _, email, _ in USERS:
        print(f"user      {email}")
    for name, email, _, _, _, status, on_duty in GUARDIANS:
        duty = "on duty" if on_duty else "off duty"
        print(f"guardian  {email}  ({status}, {duty if status == 'approved' else 'no location'})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
