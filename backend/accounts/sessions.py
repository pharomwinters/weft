"""The three session states: anonymous, partial and verified.

A partial session (password accepted, second factor or password change still
due) lives under one key of the Django session. Django's own login() runs only
in promote_if_ready, so a partial session never authenticates request.user.
"""

from datetime import timedelta
from typing import Any, Literal

from django.contrib.auth import login
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.base import SessionBase
from django.http import HttpRequest
from django.utils import timezone

from .models import User

PARTIAL_LIFETIME = timedelta(minutes=10)
_KEY = "partial"


class SessionRequest(HttpRequest):
    """A request after SessionMiddleware and AuthenticationMiddleware (for typing)."""

    session: SessionBase
    user: User | AnonymousUser
    auth: Any  # set by Ninja to the auth callable's result


NextStep = Literal["login", "verify", "enrol", "change_password"]


def start_partial(request: SessionRequest, user: User) -> None:
    request.session.flush()  # new key: no session fixation, no leftover state
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
    if not request.session[_KEY]["second_factor_ok"]:
        return "enrol"  # Task 6 returns "verify" for users with a device
    return "change_password" if user.must_change_password else None


def promote_if_ready(request: SessionRequest) -> bool:
    user = partial_user(request)
    if user is None:
        return False
    if not request.session[_KEY]["second_factor_ok"] or user.must_change_password:
        return False
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.pop(_KEY, None)
    return True
