"""Application configuration.

Everything is overridable through environment variables so the same code runs
on SQLite (development, single file) and PostgreSQL (production, millions of
rows) without code changes.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
BACKUP_DIR = Path(os.getenv("SMARTCAMPUS_BACKUP_DIR", ROOT_DIR / "backups"))
STATIC_DIR = Path(os.getenv("SMARTCAMPUS_STATIC_DIR", BASE_DIR / "static"))

APP_NAME = "Smart Campus"
APP_VERSION = "1.0.0"
API_PREFIX = "/api/v1"

# sqlite:///C:/Users/Ashish Pandey/AppData/Local/SmartCampus/... for local development, postgresql+psycopg://user:pass@host/db
# for production.
_DB_DIR = os.path.join(os.environ.get("LOCALAPPDATA", str(ROOT_DIR)), "SmartCampus")
os.makedirs(_DB_DIR, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///" + os.path.join(_DB_DIR, "smartcampus.db").replace("\\", "/"))

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "dev-only-secret-change-me-2f8f1c1a9b7e4d4fa1c2b7d0e3a55c61",
)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Brute-force protection
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))

# A single export can never pull an unbounded result set into memory.
EXPORT_ROW_LIMIT = int(os.getenv("EXPORT_ROW_LIMIT", "50000"))
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 25

# First-run administrator. The password must be changed after the first login.
DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@smartcampus.local")
DEFAULT_ADMIN_USERNAME = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "")
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

# When the app is embedded in a preview iframe (service preview cards), framing
# must be allowed. Keep it off for a real deployment.
ALLOW_EMBED = os.getenv("ALLOW_EMBED", "0") == "1"

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]
