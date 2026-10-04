from accounts import recovery, sessions, throttle, totp
from accounts.models import User, normalize_email
from accounts.passwords import validate_changed_password
from accounts.sessions import SessionRequest
from audit import events
from audit.service import record
from django.contrib.auth.hashers import check_password, make_password
from django.middleware.csrf import get_token
from ninja import Router, Status

from ..auth import anonymous, partial, session_state
from ..errors import ApiError
from ..schemas import (
    CodeIn,
    EnrolConfirmOut,
    EnrolStartOut,
    ForcedPasswordIn,
    LoginIn,
    LoginOut,
    SecondFactorOut,
    SessionOut,
)

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
    sessions.end_current(request)
    return Status(204, None)


def _second_factor_user(request: SessionRequest, *, enrolled: bool) -> User:
    """The partial session's user, at the step the endpoint belongs to.

    Refuses a verified session, a user on the other side of enrolment, and a
    locked account or blocked address.
    """
    if sessions.is_verified(request):
        raise ApiError(409, "already_verified", "This session is already verified.")
    user = request.auth
    if totp.has_confirmed_device(user) != enrolled:
        if enrolled:
            raise ApiError(
                401,
                "auth_required",
                "Authentication is required.",
                {"session": "partial", "next": sessions.next_step(request)},
            )
        raise ApiError(409, "already_enrolled", "Two-factor is already set up.")
    if throttle.is_blocked(request, user.email):
        raise ApiError(429, "locked", "Too many attempts. Try again later.")
    return user


def _bad_code(request: SessionRequest, user: User) -> ApiError:
    throttle.record_failure(request, user.email)
    return ApiError(401, "invalid_code", "That code is not valid.")


def _second_factor_done(request: SessionRequest, user: User) -> dict:
    sessions.mark_second_factor_ok(request)
    if sessions.promote_if_ready(request):
        throttle.record_success(request, user.email)
    return {"next": sessions.next_step(request)}


@router.post("/enrol/start", auth=partial, response=EnrolStartOut)
def enrol_start(request: SessionRequest):
    user = _second_factor_user(request, enrolled=False)
    secret, uri = totp.begin_enrolment(user)
    return {"secret": secret, "otpauth_uri": uri}


@router.post("/enrol/confirm", auth=partial, response=EnrolConfirmOut)
def enrol_confirm(request: SessionRequest, payload: CodeIn):
    user = _second_factor_user(request, enrolled=False)
    if not totp.confirm_enrolment(user, payload.code):
        raise _bad_code(request, user)
    codes = recovery.generate(user)
    record(events.TOTP_ENROLLED, request=request, actor=user, target=user)
    return {"recovery_codes": codes, **_second_factor_done(request, user)}


@router.post("/verify", auth=partial, response=SecondFactorOut)
def verify(request: SessionRequest, payload: CodeIn):
    user = _second_factor_user(request, enrolled=True)
    if not totp.verify(user, payload.code):
        raise _bad_code(request, user)
    return _second_factor_done(request, user)


@router.post("/recovery", auth=partial, response=SecondFactorOut)
def use_recovery_code(request: SessionRequest, payload: CodeIn):
    user = _second_factor_user(request, enrolled=True)
    if not recovery.redeem(user, payload.code):
        raise _bad_code(request, user)
    record(events.RECOVERY_CODE_USED, request=request, actor=user, target=user)
    return _second_factor_done(request, user)


@router.post("/password/forced", auth=partial, response=SecondFactorOut)
def forced_password_change(request: SessionRequest, payload: ForcedPasswordIn):
    user = request.auth
    if sessions.is_verified(request) or not user.must_change_password:
        raise ApiError(409, "not_required", "No password change is required.")
    if not sessions.second_factor_ok(request):
        raise ApiError(
            401,
            "auth_required",
            "Authentication is required.",
            {"session": "partial", "next": sessions.next_step(request)},
        )
    validate_changed_password(payload.new_password, user)
    user.set_password(payload.new_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password"])
    record(events.PASSWORD_CHANGED, request=request, actor=user, target=user)
    sessions.end_sessions(user)
    if sessions.promote_if_ready(request):
        throttle.record_success(request, user.email)
    return {"next": sessions.next_step(request)}
