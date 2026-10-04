from accounts import recovery, sessions, throttle, totp
from accounts.models import User, UserSession
from accounts.passwords import validate_changed_password
from accounts.sessions import SessionRequest
from audit import events
from audit.service import record
from django.shortcuts import get_object_or_404
from ninja import Router, Status

from ..errors import ApiError
from ..schemas import (
    CodeIn,
    EnrolStartOut,
    PasswordChangeIn,
    RecoveryCodesOut,
    SessionItemOut,
    UserOut,
)

router = Router()


def _refuse_if_locked(request: SessionRequest, user: User) -> None:
    if throttle.is_blocked(request, user.email):
        raise ApiError(429, "locked", "Too many attempts. Try again later.")


@router.get("", response=UserOut)
def get_account(request: SessionRequest):
    return request.auth


@router.post("/password", response={204: None})
def change_password(request: SessionRequest, payload: PasswordChangeIn):
    user = request.auth
    _refuse_if_locked(request, user)
    if not user.check_password(payload.current_password):
        throttle.record_failure(request, user.email)
        raise ApiError(401, "invalid_credentials", "The current password is wrong.")
    validate_changed_password(payload.new_password, user)
    user.set_password(payload.new_password)
    user.save(update_fields=["password"])
    record(events.PASSWORD_CHANGED, request=request, actor=user, target=user)
    sessions.keep_after_password_change(request, user)
    return Status(204, None)


@router.get("/sessions", response=list[SessionItemOut])
def list_sessions(request: SessionRequest):
    current = request.session.session_key
    rows = UserSession.objects.filter(user=request.auth).order_by("-last_seen", "-pk")
    return [
        {
            "id": row.pk,
            "ip": row.ip,
            "user_agent": row.user_agent,
            "created": row.created,
            "last_seen": row.last_seen,
            "current": row.session_key == current,
        }
        for row in rows
    ]


@router.delete("/sessions/{session_id}", response={204: None})
def revoke_session(request: SessionRequest, session_id: int):
    row = get_object_or_404(UserSession, pk=session_id, user=request.auth)
    sessions.end_session(row)
    return Status(204, None)


@router.post("/2fa/reenrol/start", response=EnrolStartOut)
def reenrol_start(request: SessionRequest, payload: CodeIn):
    """Begin replacing the device; needs a current TOTP or recovery code."""
    user = request.auth
    _refuse_if_locked(request, user)
    if not totp.verify(user, payload.code):
        if not recovery.redeem(user, payload.code):
            throttle.record_failure(request, user.email)
            raise ApiError(401, "invalid_code", "That code is not valid.")
        record(events.RECOVERY_CODE_USED, request=request, actor=user, target=user)
    secret, uri = totp.begin_enrolment(user)
    return {"secret": secret, "otpauth_uri": uri}


@router.post("/2fa/reenrol/confirm", response=RecoveryCodesOut)
def reenrol_confirm(request: SessionRequest, payload: CodeIn):
    user = request.auth
    _refuse_if_locked(request, user)
    codes = totp.confirm_with_recovery_codes(user, payload.code)
    if codes is None:
        throttle.record_failure(request, user.email)
        raise ApiError(401, "invalid_code", "That code is not valid.")
    record(events.TOTP_ENROLLED, request=request, actor=user, target=user)
    return {"recovery_codes": codes}
