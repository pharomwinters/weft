from accounts import invitations, sessions, throttle
from accounts.models import Invitation
from accounts.sessions import SessionRequest
from ninja import Router, Status
from permissions import actions
from permissions.core import INSTANCE, require
from workspaces.models import Workspace

from ..auth import anonymous
from ..errors import ApiError
from ..schemas import (
    InvitationAcceptIn,
    InvitationCreatedOut,
    InvitationIn,
    InvitationInfoOut,
    InvitationOut,
    LoginOut,
)

router = Router()


def _workspace_to_invite_to(request: SessionRequest, workspace_id: int) -> Workspace:
    workspace = Workspace.objects.filter(pk=workspace_id).first()
    if workspace is None:
        raise ApiError(404, "not_found", "Not found.")
    require(request.auth, actions.WORKSPACE_INVITE, workspace)
    return workspace


def _require_may_manage(request: SessionRequest, invitation: Invitation) -> None:
    if invitation.workspace is None:
        require(request.auth, actions.INSTANCE_CREATE_INVITATION, INSTANCE)
    else:
        require(request.auth, actions.WORKSPACE_INVITE, invitation.workspace)


def _refuse_if_blocked(request: SessionRequest) -> None:
    if throttle.is_blocked(request, None):
        raise ApiError(429, "locked", "Too many attempts. Try again later.")


def _dead_token(request: SessionRequest) -> ApiError:
    """One answer for unknown, used, expired and revoked tokens alike."""
    throttle.record_failure(request, None)
    return ApiError(404, "invalid_token", "This invitation is no longer valid.")


@router.post("", response={201: InvitationCreatedOut})
def create_invitation(request: SessionRequest, payload: InvitationIn):
    if payload.workspace_id is None:
        require(request.auth, actions.INSTANCE_CREATE_INVITATION, INSTANCE)
        workspace = None
    else:
        workspace = _workspace_to_invite_to(request, payload.workspace_id)
        if payload.role is None:
            raise ApiError(
                400,
                "validation",
                "The request was not valid.",
                {"role": ["A role is required for a workspace invitation."]},
            )
    invitation, url = invitations.create(
        request.auth, workspace, payload.role, request=request
    )
    return Status(
        201, {"id": invitation.pk, "url": url, "expires_at": invitation.expires_at}
    )


@router.get("", response=list[InvitationOut])
def list_invitations(request: SessionRequest, workspace_id: int | None = None):
    found = invitations.pending()
    if workspace_id is None:
        require(request.auth, actions.INSTANCE_CREATE_INVITATION, INSTANCE)
    else:
        found = found.filter(workspace=_workspace_to_invite_to(request, workspace_id))
    return [
        {
            "id": i.pk,
            "workspace_id": i.workspace.pk if i.workspace else None,
            "workspace_name": i.workspace.name if i.workspace else None,
            "role": i.role,
            "created_by_email": i.created_by.email if i.created_by else None,
            "expires_at": i.expires_at,
        }
        for i in found.select_related("workspace", "created_by").order_by("-pk")
    ]


@router.delete("/{invitation_id}", response={204: None})
def revoke_invitation(request: SessionRequest, invitation_id: int):
    invitation = invitations.pending().filter(pk=invitation_id).first()
    if invitation is None:
        raise ApiError(404, "not_found", "Not found.")
    _require_may_manage(request, invitation)
    invitations.revoke(invitation)
    return Status(204, None)


@router.get("/token/{token}", auth=anonymous, response=InvitationInfoOut)
def inspect_invitation(request: SessionRequest, token: str):
    _refuse_if_blocked(request)
    invitation = invitations.find(token)
    if invitation is None:
        raise _dead_token(request)
    workspace = invitation.workspace
    return {
        "workspace_name": workspace.name if workspace else None,
        "role": invitation.role,
    }


@router.post("/token/{token}/accept", auth=anonymous, response={201: LoginOut})
def accept_invitation(request: SessionRequest, token: str, payload: InvitationAcceptIn):
    _refuse_if_blocked(request)
    user = invitations.accept(token, payload.email, payload.password, request=request)
    if user is None:
        raise _dead_token(request)
    sessions.start_partial(request, user)
    return Status(201, {"next": sessions.next_step(request)})
