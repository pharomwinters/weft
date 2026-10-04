"""Validated configuration read from environment variables."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

# The values shipped in .env.example. The server refuses to start while a
# required setting still holds one of them.
EXAMPLE_VALUES: dict[str, str] = {
    "DATABASE_URL": "postgres://app:change-me@postgres:5432/app",
    "SECRET_KEY": "change-me",
    "TOTP_ENCRYPTION_KEY": "change-me",
    "PUBLIC_URL": "https://change-me.example.com",
}

MIN_SECRET_KEY_LENGTH = 32


class ConfigError(Exception):
    """A configuration value is missing or invalid; the message names it."""


@dataclass(frozen=True)
class Config:
    database_url: str
    secret_key: str
    totp_encryption_key: str
    public_url: str
    trusted_proxy_count: int
    initial_admin_email: str | None
    initial_admin_password: str | None


def _required(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key, "").strip()
    if not value:
        raise ConfigError(f"{key} is required")
    if value == EXAMPLE_VALUES[key]:
        raise ConfigError(f"{key} still has the value from the example env file")
    return value


def _optional(environ: Mapping[str, str], key: str) -> str | None:
    return environ.get(key, "").strip() or None


def load_config(environ: Mapping[str, str]) -> Config:
    database_url = _required(environ, "DATABASE_URL")
    if not re.match(r"^postgres(ql)?://", database_url):
        raise ConfigError("DATABASE_URL must be a postgres:// URL")

    secret_key = _required(environ, "SECRET_KEY")
    if len(secret_key) < MIN_SECRET_KEY_LENGTH:
        raise ConfigError(
            f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters"
        )

    totp_key = _required(environ, "TOTP_ENCRYPTION_KEY")
    try:
        Fernet(totp_key)
    except ValueError:
        raise ConfigError(
            "TOTP_ENCRYPTION_KEY must be a Fernet key (32 url-safe base64 bytes)"
        ) from None

    public_url = _required(environ, "PUBLIC_URL")
    parts = urlsplit(public_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError("PUBLIC_URL must be an http:// or https:// URL")

    raw_count = environ.get("TRUSTED_PROXY_COUNT", "").strip() or "0"
    try:
        proxy_count = int(raw_count)
    except ValueError:
        raise ConfigError("TRUSTED_PROXY_COUNT must be a whole number") from None
    if proxy_count < 0:
        raise ConfigError("TRUSTED_PROXY_COUNT must not be negative")

    return Config(
        database_url=database_url,
        secret_key=secret_key,
        totp_encryption_key=totp_key,
        public_url=public_url,
        trusted_proxy_count=proxy_count,
        initial_admin_email=_optional(environ, "INITIAL_ADMIN_EMAIL"),
        initial_admin_password=_optional(environ, "INITIAL_ADMIN_PASSWORD"),
    )
