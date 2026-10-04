"""Ninja auth callables for the three session states.

All three enforce CSRF on unsafe methods. A failed check is a 401
`auth_required` whose details tell the SPA which screen to show.
"""

from accounts import sessions
from accounts.sessions import SessionRequest
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware

from .errors import ApiError

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _unused_view(request) -> HttpResponse:
    """Stands in for the view; the CSRF middleware only needs one to exist."""
    return HttpResponse()


def _check_csrf(request: SessionRequest) -> None:
    if request.method in _SAFE_METHODS:
        return
    # Ninja views are csrf_exempt, so the middleware's own check is skipped.
    middleware = CsrfViewMiddleware(_unused_view)
    reason = middleware.process_view(request, _unused_view, (), {})
    if reason is not None:
        raise ApiError(403, "csrf_failed", "The request could not be verified.")


def session_state(request: SessionRequest) -> str:
    if sessions.is_verified(request):
        return "verified"
    return "partial" if sessions.partial_user(request) else "anonymous"


def _refuse(request: SessionRequest) -> ApiError:
    return ApiError(
        401,
        "auth_required",
        "Authentication is required.",
        {"session": session_state(request), "next": sessions.next_step(request)},
    )


def anonymous(request: SessionRequest) -> bool:
    _check_csrf(request)
    return True


def partial(request: SessionRequest) -> object:
    """A password-verified session, partial or fully verified."""
    _check_csrf(request)
    user = request.user if sessions.is_verified(request) else None
    user = user or sessions.partial_user(request)
    if user is None:
        raise _refuse(request)
    return user


def verified(request: SessionRequest) -> object:
    _check_csrf(request)
    if not sessions.is_verified(request):
        raise _refuse(request)
    return request.user
