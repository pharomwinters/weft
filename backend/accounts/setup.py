"""First-run setup: the two routes that create the first instance admin."""

import secrets
from typing import Literal, Protocol

from api.errors import ApiError
from audit import events
from audit.service import record
from config.env import Config, ConfigError
from django.db import IntegrityError, transaction

from .emails import clean_email
from .models import SetupToken, User
from .passwords import validate_new_password
from .tokens import hash_token, new_token


class _Writer(Protocol):
    """A text stream, or a management command's stdout wrapper."""

    def write(self, text: str, /) -> object: ...


def admin_exists() -> bool:
    """True once any instance admin exists, active or not."""
    return User.objects.filter(is_instance_admin=True).exists()


def _env_admin(config: Config) -> User:
    assert config.initial_admin_email and config.initial_admin_password
    try:
        email = clean_email(config.initial_admin_email)
    except ApiError:
        raise ConfigError("INITIAL_ADMIN_EMAIL is not a valid email address") from None
    try:
        validate_new_password(config.initial_admin_password, User(email=email))
    except ApiError as exc:
        reasons = " ".join(exc.details["password"])
        raise ConfigError(f"INITIAL_ADMIN_PASSWORD is too weak: {reasons}") from None
    return User.objects.create_user(
        email,
        config.initial_admin_password,
        is_instance_admin=True,
        must_change_password=True,
    )


def bootstrap(config: Config, out: _Writer) -> Literal["exists", "env_admin", "token"]:
    """Run at every start. Exactly one route applies while no admin exists."""
    if admin_exists():
        SetupToken.objects.all().delete()
        return "exists"
    if config.initial_admin_email and config.initial_admin_password:
        with transaction.atomic():
            user = _env_admin(config)
            SetupToken.objects.all().delete()
            record(events.SETUP_COMPLETED, target=user, details={"route": "env"})
        return "env_admin"
    token, token_hash = new_token()
    with transaction.atomic():
        SetupToken.objects.all().delete()
        SetupToken.objects.create(token_hash=token_hash)
    out.write(f"Setup token: {token}\n")
    return "token"


def create_admin(token: str, email: str, password: str) -> User | None:
    """Create the first admin from the setup token; None if the token is wrong.

    The token row is locked and deleted with the admin's creation, so of two
    simultaneous attempts the second finds setup already closed.
    """
    with transaction.atomic():
        row = SetupToken.objects.select_for_update().first()
        if admin_exists():
            raise ApiError(404, "not_found", "Not found.")
        if row is None or not secrets.compare_digest(row.token_hash, hash_token(token)):
            return None
        email = clean_email(email)
        validate_new_password(password, User(email=email))
        try:
            with transaction.atomic():
                user = User.objects.create_user(email, password, is_instance_admin=True)
        except IntegrityError:
            raise ApiError(
                409, "email_taken", "That email address is already in use."
            ) from None
        row.delete()
    return user
