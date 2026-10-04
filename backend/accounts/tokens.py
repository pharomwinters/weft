"""One-time tokens (setup, invitation, reset): random, stored only as a hash."""

import hashlib
import secrets


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    """(token, sha256 hex digest). The token itself is never stored."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)
