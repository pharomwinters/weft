from accounts import sessions, setup, throttle
from accounts.sessions import SessionRequest
from audit import events
from audit.service import record
from ninja import Router, Status

from ..auth import anonymous
from ..errors import ApiError
from ..schemas import LoginOut, SetupIn, SetupStatusOut

router = Router()


def _refuse_once_admin_exists() -> None:
    if setup.admin_exists():
        raise ApiError(404, "not_found", "Not found.")


@router.get("/status", auth=anonymous, response=SetupStatusOut)
def status(request: SessionRequest):
    _refuse_once_admin_exists()
    return {"needs_setup": True}


@router.post("/admin", auth=anonymous, response={201: LoginOut})
def create_admin(request: SessionRequest, payload: SetupIn):
    _refuse_once_admin_exists()
    if throttle.is_blocked(request, None):
        raise ApiError(429, "locked", "Too many attempts. Try again later.")
    user = setup.create_admin(payload.token, payload.email, payload.password)
    if user is None:
        throttle.record_failure(request, None)
        raise ApiError(401, "invalid_token", "The setup token is not valid.")
    sessions.start_partial(request, user)
    record(
        events.SETUP_COMPLETED,
        request=request,
        actor=user,
        target=user,
        details={"route": "token"},
    )
    return Status(201, {"next": sessions.next_step(request)})
