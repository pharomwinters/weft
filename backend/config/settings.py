"""Production settings. Debug mode cannot be switched on from here."""

import logging
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .env import load_config

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

_config = load_config(os.environ)

SECRET_KEY = _config.secret_key
DEBUG = False

_public = urlsplit(_config.public_url)
_public_https = _public.scheme == "https"
ALLOWED_HOSTS = [_public.hostname]
CSRF_TRUSTED_ORIGINS = [f"{_public.scheme}://{_public.netloc}"]
SESSION_COOKIE_SECURE = _public_https
CSRF_COOKIE_SECURE = _public_https
if _public_https:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

if not _public_https and _public.hostname not in ("localhost", "127.0.0.1"):
    logger.warning(
        "PUBLIC_URL is plain http and not a localhost address: "
        "sessions and passwords will cross the network unencrypted"
    )

TRUSTED_PROXY_COUNT = _config.trusted_proxy_count
TOTP_ENCRYPTION_KEY = _config.totp_encryption_key
INITIAL_ADMIN_EMAIL = _config.initial_admin_email
INITIAL_ADMIN_PASSWORD = _config.initial_admin_password

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "config.apps.ConfigConfig",
    "accounts.apps.AccountsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
X_FRAME_OPTIONS = "DENY"


def _database(url: str) -> dict:
    parts = urlsplit(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parts.path.lstrip("/"),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "",
        "PORT": str(parts.port or ""),
        # All Django tables live in the `platform` schema, leaving other
        # schemas free for bases.
        "OPTIONS": {"options": "-c search_path=platform"},
    }


DATABASES = {"default": _database(_config.database_url)}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email",)},
    },
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
