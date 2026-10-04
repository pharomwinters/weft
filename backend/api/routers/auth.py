from accounts import sessions, throttle
from accounts.models import User, normalize_email
from accounts.sessions import SessionRequest
from audit import events
from audit.service import record
from django.contrib.auth.hashers import check_password, make_password
from django.middleware.csrf import get_token
from ninja import Router, Status

from ..auth import anonymous, partial, session_state
from ..errors import ApiError
from ..schemas import LoginIn, LoginOut, SessionOut

router = Router()

# Checked when the email is unknown or inactive, so every failure costs one hash.
_DUMMY_HASH = make_password("not-a-real-password")


@router.get("/session", auth=anonymous, response=SessionOut)
def get_session(request: SessionRequest):
    get_token(request)  # sets the CSRF cookie for the SPA's unsafe requests
    state = session_state(request)
    user = request.user if state == "verified" else sessions.partial_user(request)
    return {"state": state, "next": sessions.next_step(request), "user": user}


@router.post("/login", auth=anonymous, response=LoginOut)
def login(request: SessionRequest, payload: LoginIn):
    email = normalize_email(payload.email)
    if throttle.is_blocked(request, email):
        raise ApiError(429, "locked", "Too many attempts. Try again later.")
    user = User.objects.filter(email=email).first()
    if user is not None and user.is_active:
        valid = user.check_password(payload.password)
    else:
        check_password(payload.password, _DUMMY_HASH)
        valid = False
    if not valid:
        throttle.record_failure(request, email)
        raise ApiError(401, "invalid_credentials", "Incorrect email or password.")
    assert user is not None
    sessions.start_partial(request, user)
    record(events.LOGIN_SUCCESS, request=request, actor=user, target=user)
    return {"next": sessions.next_step(request)}


@router.post("/logout", auth=partial, response={204: None})
def logout(request: SessionRequest):
    user = request.auth
    record(events.LOGOUT, request=request, actor=user, target=user)
    request.session.flush()
    return Status(204, None)
