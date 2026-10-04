"""The three session states: anonymous, partial and verified.

A partial session (password accepted, second factor or password change still
due) lives under one key of the Django session. Django's own login() runs only
in promote_if_ready, so a partial session never authenticates request.user.
"""

from datetime import timedelta
from typing import Any, Literal

from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.base import SessionBase
from django.contrib.sessions.models import Session
from django.http import HttpRequest
from django.utils import timezone

from . import totp
from .models import USER_AGENT_LENGTH, User, UserSession
from .net import client_ip

PARTIAL_LIFETIME = timedelta(minutes=10)
TOUCH_INTERVAL = timedelta(minutes=1)
_KEY = "partial"


class SessionRequest(HttpRequest):
    """A request after SessionMiddleware and AuthenticationMiddleware (for typing)."""

    session: SessionBase
    user: User | AnonymousUser
    auth: Any  # set by Ninja to the auth callable's result


NextStep = Literal["login", "verify", "enrol", "change_password"]


def _forget(session_key: str | None) -> None:
    if session_key:
        UserSession.objects.filter(session_key=session_key).delete()


def start_partial(request: SessionRequest, user: User) -> None:
    _forget(request.session.session_key)
    request.session.flush()  # new key: no session fixation, no leftover state
    # A verified session that logs in again is partial from here on.
    request.user = AnonymousUser()
    request.session[_KEY] = {
        "user_id": user.pk,
        "started": timezone.now().timestamp(),
        "second_factor_ok": False,
    }


def partial_user(request: SessionRequest) -> User | None:
    state = request.session.get(_KEY)
    if not state:
        return None
    age = timezone.now().timestamp() - state["started"]
    if age > PARTIAL_LIFETIME.total_seconds():
        return None
    return User.objects.filter(pk=state["user_id"], is_active=True).first()


def mark_second_factor_ok(request: SessionRequest) -> None:
    state = request.session[_KEY]
    state["second_factor_ok"] = True
    request.session[_KEY] = state  # reassign so the session is saved


def second_factor_ok(request: SessionRequest) -> bool:
    state = request.session.get(_KEY)
    return bool(state and state["second_factor_ok"])


def is_verified(request: SessionRequest) -> bool:
    user = request.user
    return bool(user.is_authenticated and user.is_active)


def next_step(request: SessionRequest) -> NextStep | None:
    """What a session must still do; None means it is verified."""
    if is_verified(request):
        return None
    user = partial_user(request)
    if user is None:
        return "login"
    if not second_factor_ok(request):
        return "verify" if totp.has_confirmed_device(user) else "enrol"
    return "change_password" if user.must_change_password else None


def promote_if_ready(request: SessionRequest) -> bool:
    user = partial_user(request)
    if user is None:
        return False
    if not second_factor_ok(request) or user.must_change_password:
        return False
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.pop(_KEY, None)
    now = timezone.now()
    UserSession.objects.create(
        user=user,
        session_key=request.session.session_key,
        ip=client_ip(request) or None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:USER_AGENT_LENGTH],
        created=now,
        last_seen=now,
    )
    return True


def end_current(request: SessionRequest) -> None:
    """Log out: drop the session and its UserSession row."""
    _forget(request.session.session_key)
    request.session.flush()


def end_sessions(user: User, *, except_key: str | None = None) -> None:
    """End the user's verified sessions, optionally sparing one."""
    rows = UserSession.objects.filter(user=user)
    if except_key is not None:
        rows = rows.exclude(session_key=except_key)
    keys = list(rows.values_list("session_key", flat=True))
    Session.objects.filter(session_key__in=keys).delete()
    rows.filter(session_key__in=keys).delete()


def keep_after_password_change(request: SessionRequest, user: User) -> None:
    """Keep this verified session alive across the user's password change.

    Django ties a session to the password hash and rotates the key when the
    tie is renewed, so the UserSession row follows the new key. Every other
    session of the user is ended.
    """
    old_key = request.session.session_key
    update_session_auth_hash(request, user)
    new_key = request.session.session_key
    UserSession.objects.filter(session_key=old_key).update(session_key=new_key)
    end_sessions(user, except_key=new_key)


def end_session(row: UserSession) -> None:
    Session.objects.filter(session_key=row.session_key).delete()
    row.delete()


def touch(request: SessionRequest) -> None:
    """Note that a verified session was just used, at most once a minute."""
    if not is_verified(request):
        return
    now = timezone.now()
    UserSession.objects.filter(
        session_key=request.session.session_key,
        last_seen__lt=now - TOUCH_INTERVAL,
    ).update(last_seen=now)
