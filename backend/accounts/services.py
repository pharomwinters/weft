"""Instance-admin operations on users, and the recovery paths without email."""

from datetime import timedelta

from api.errors import ApiError
from audit import events
from audit.service import record
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from . import sessions, throttle, totp
from .models import ResetLink, User
from .passwords import validate_new_password
from .tokens import hash_token, new_token

RESET_LIFETIME = timedelta(hours=24)


def _locked(user: User) -> tuple[User, int]:
    """The user re-read under lock, and the number of active admins.

    Every change that could remove an active admin locks all of them first, so
    two such changes cannot each count the other's admin as still there.
    """
    # Ordered, so two concurrent changes take the locks in the same order.
    admins = (
        User.objects.select_for_update()
        .filter(is_instance_admin=True, is_active=True)
        .order_by("pk")
    )
    active_admins = len(admins)
    return User.objects.select_for_update().get(pk=user.pk), active_admins


def _refuse_if_last_admin(user: User, active_admins: int) -> None:
    if user.is_instance_admin and user.is_active and active_admins <= 1:
        raise ApiError(
            409, "last_admin", "The instance must keep at least one active admin."
        )


def deactivate(
    user: User, *, actor: User | None = None, request: HttpRequest | None = None
) -> None:
    with transaction.atomic():
        user, active_admins = _locked(user)
        if not user.is_active:
            return
        _refuse_if_last_admin(user, active_admins)
        user.is_active = False
        user.save(update_fields=["is_active"])
        sessions.end_sessions(user)
        record(events.USER_DEACTIVATED, request=request, actor=actor, target=user)


def reactivate(
    user: User, *, actor: User | None = None, request: HttpRequest | None = None
) -> None:
    if user.is_active:
        return
    user.is_active = True
    user.save(update_fields=["is_active"])
    record(events.USER_REACTIVATED, request=request, actor=actor, target=user)


def set_admin(
    user: User,
    value: bool,
    *,
    actor: User | None = None,
    request: HttpRequest | None = None,
) -> None:
    with transaction.atomic():
        user, active_admins = _locked(user)
        if user.is_instance_admin == value:
            return
        if not value:
            _refuse_if_last_admin(user, active_admins)
        user.is_instance_admin = value
        user.save(update_fields=["is_instance_admin"])
        record(
            events.ADMIN_FLAG_CHANGED,
            request=request,
            actor=actor,
            target=user,
            details={"is_instance_admin": value},
        )


def create_reset_link(
    user: User, *, actor: User | None = None, request: HttpRequest | None = None
) -> tuple[str, ResetLink]:
    """A password-reset URL for the user; any earlier unused link stops working."""
    token, token_hash = new_token()
    with transaction.atomic():
        ResetLink.objects.filter(user=user, used_at__isnull=True).delete()
        link = ResetLink.objects.create(
            token_hash=token_hash,
            user=user,
            created_by=actor,
            expires_at=timezone.now() + RESET_LIFETIME,
        )
        record(events.RESET_LINK_CREATED, request=request, actor=actor, target=user)
    return f"{settings.PUBLIC_URL}/reset/{token}", link


def _live_links():
    return ResetLink.objects.filter(
        used_at__isnull=True, expires_at__gt=timezone.now(), user__is_active=True
    )


def reset_link_is_live(token: str) -> bool:
    return _live_links().filter(token_hash=hash_token(token)).exists()


def redeem_reset_link(
    token: str, new_password: str, *, request: HttpRequest | None = None
) -> User | None:
    """Set a new password from a reset link; None if the token is dead.

    The second factor is untouched: the user still needs it at the next login.
    """
    with transaction.atomic():
        link = (
            _live_links()
            .select_for_update(of=("self",))
            .filter(token_hash=hash_token(token))
            .select_related("user")
            .first()
        )
        if link is None:
            return None
        user = link.user
        validate_new_password(new_password, user)
        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        link.used_at = timezone.now()
        link.save(update_fields=["used_at"])
        sessions.end_sessions(user)
        record(events.RESET_LINK_USED, request=request, actor=user, target=user)
        record(events.PASSWORD_CHANGED, request=request, actor=user, target=user)
    throttle.reset_account(user.email)
    return user


def reset_second_factor(
    user: User, *, actor: User | None = None, request: HttpRequest | None = None
) -> None:
    """Remove the user's device and recovery codes; they enrol at next login."""
    with transaction.atomic():
        totp.clear(user)
        sessions.end_sessions(user)
        record(events.TWOFA_RESET, request=request, actor=actor, target=user)
