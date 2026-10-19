from models import EmergencyRequest, GuardianProfile, User


def stats():
    """Real counts straight from the database. No fake numbers."""
    return {
        "users": User.query.filter_by(role="user").count(),
        "approved_guardians": GuardianProfile.query.filter_by(status="approved").count(),
        "pending_guardians": GuardianProfile.query.filter_by(status="pending").count(),
        "requests": EmergencyRequest.query.count(),
    }
