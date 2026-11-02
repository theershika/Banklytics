import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


class Config:
    ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = env_bool("FLASK_DEBUG", False)
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'banklytics.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    UNUSUAL_TRANSACTION_LIMIT = float(os.getenv("UNUSUAL_TRANSACTION_LIMIT", "50000"))
    AUTO_SEED_DEMO_DATA = env_bool("AUTO_SEED_DEMO_DATA", ENV != "production")
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", ENV == "production")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = int(os.getenv("SESSION_LIFETIME_SECONDS", "28800"))
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    WTF_CSRF_TIME_LIMIT = 3600
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
