import os
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'mysql+pymysql://accountpulse:configure-password@127.0.0.1:3306/banking_analysis?charset=utf8mb4')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True, 'pool_recycle': 1800}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    MAX_CONTENT_LENGTH = 64 * 1024
    WTF_CSRF_TIME_LIMIT = 7200
    RATELIMIT_STORAGE_URI = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')
    FLAG_LARGE_THRESHOLD = os.getenv('FLAG_LARGE_THRESHOLD', '100000.00')
    FLAG_WITHDRAWAL_COUNT = 3
    FLAG_WINDOW_MINUTES = 10
    FLAG_HISTORY_MIN = 5
    FLAG_HISTORY_MULTIPLIER = 3
