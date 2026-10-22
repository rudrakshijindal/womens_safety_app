import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
SOS_SIMULATED_LATITUDE = float(os.environ.get("SOS_SIMULATED_LATITUDE", "28.6139"))
SOS_SIMULATED_LONGITUDE = float(os.environ.get("SOS_SIMULATED_LONGITUDE", "77.2090"))


class Config:
    # Read from the environment (.env). The fallback is for local demo only.
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-change-me"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or "sqlite:///womens_safety.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_TIME_LIMIT = None
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False