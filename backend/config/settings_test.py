import os
from pathlib import Path

from cryptography.fernet import Fernet

_FALLBACK_DATABASE_URL = "postgres://app:app@localhost:55433/app"
_ENV_DEV = Path(__file__).resolve().parents[2] / ".env.dev"


def _database_url_from_env_dev() -> str | None:
    if not _ENV_DEV.exists():
        return None
    for line in _ENV_DEV.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key == "DATABASE_URL":
            return value.strip().strip("'\"") or None
    return None


if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = _database_url_from_env_dev() or _FALLBACK_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "test-secret-key-" + "x" * 32)
os.environ.setdefault("TOTP_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("PUBLIC_URL", "http://localhost:8000")

from .settings import *  # noqa: E402, F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
