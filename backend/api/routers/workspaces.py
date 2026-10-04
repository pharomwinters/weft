from accounts.models import User, normalize_email
from accounts.sessions import SessionRequest
from ninja import Router, Status
from permissions import actions
from permissions.core import INSTANCE, require, workspaces_for
from workspaces import services
from workspaces.models import Membership, Workspace

from ..errors import ApiError
from ..schemas import (
    MemberAddIn,
    MemberOut,
    MemberRoleIn,
    WorkspaceIn,
    WorkspaceOut,
)

router = Router()


def _workspace(request: SessionRequest, workspace_id: int, action: str) -> Workspace:
    """The workspace, if the caller may perform the action on it."""
    workspace = Workspace.objects.filter(pk=workspace_id).first()
    if workspace is None:
        raise ApiError(404, "not_found", "Not found.")
    require(request.auth, action, workspace)
    return workspace


def _member(workspace: Workspace, user_id: int) -> User:
    membership = (
        Membership.objects.filter(workspace=workspace, user_id=user_id)
        .select_related("user")
        .first()
    )
    if membership is None:
        raise ApiError(404, "not_found", "Not found.")
    return membership.user


def _workspace_out(user: User, workspace: Workspace) -> dict:
    """The workspace as JSON; `role` is the caller's own, None for a non-member."""
    membership = Membership.objects.filter(user=user, workspace=workspace).first()
    return {
        "id": workspace.pk,
        "name": workspace.name,
        "role": membership.role if membership else None,
        "deleted_at": workspace.deleted_at,
    }


def _member_out(membership: Membership) -> dict:
    return {
        "user_id": membership.user.pk,
        "email": membership.user.email,
        "role": membership.role,
    }


@router.get("", response=list[WorkspaceOut])
def list_workspaces(request: SessionRequest, deleted: bool = False):
    user = request.auth
    if deleted:
        found = workspaces_for(user, actions.WORKSPACE_RESTORE).filter(
            deleted_at__gte=services.restorable_since()
        )
    else:
        found = workspaces_for(user, actions.WORKSPACE_VIEW)
    return [_workspace_out(user, w) for w in found.order_by("name", "pk")]


@router.post("", response={201: WorkspaceOut})
def create_workspace(request: SessionRequest, payload: WorkspaceIn):
    user = request.auth
    require(user, actions.WORKSPACE_CREATE, INSTANCE)
    workspace = services.create(user, payload.name, request=request)
    return Status(201, _workspace_out(user, workspace))


@router.get("/{workspace_id}", response=WorkspaceOut)
def get_workspace(request: SessionRequest, workspace_id: int):
    workspace = _workspace(request, workspace_id, actions.WORKSPACE_VIEW)
    return _workspace_out(request.auth, workspace)


@router.patch("/{workspace_id}", response=WorkspaceOut)
def rename_workspace(request: SessionRequest, workspace_id: int, payload: WorkspaceIn):
    workspace = _workspace(request, workspace_id, actions.WORKSPACE_RENAME)
    services.rename(workspace, payload.name, actor=request.auth, request=request)
    return _workspace_out(request.auth, workspace)


@router.delete("/{workspace_id}", response={204: None})
def delete_workspace(request: SessionRequest, workspace_id: int):
    workspace = _workspace(request, workspace_id, actions.WORKSPACE_DELETE)
    services.soft_delete(workspace, actor=request.auth, request=request)
    return Status(204, None)


@router.post("/{workspace_id}/restore", response=WorkspaceOut)
def restore_workspace(request: SessionRequest, workspace_id: int):
    workspace = _workspace(request, workspace_id, actions.WORKSPACE_RESTORE)
    services.restore(workspace, actor=request.auth, request=request)
    return _workspace_out(request.auth, workspace)


@router.get("/{workspace_id}/members", response=list[MemberOut])
def list_members(request: SessionRequest, workspace_id: int):
    workspace = _workspace(request, workspace_id, actions.WORKSPACE_VIEW)
    memberships = (
        Membership.objects.filter(workspace=workspace)
        .select_related("user")
        .order_by("user__email")
    )
    return [_member_out(m) for m in memberships]


@router.post("/{workspace_id}/members", response={201: MemberOut})
def add_member(request: SessionRequest, workspace_id: int, payload: MemberAddIn):
    workspace = _workspace(request, workspace_id, actions.WORKSPACE_MANAGE_MEMBERS)
    user = User.objects.filter(email=normalize_email(payload.email)).first()
    if user is None:
        raise ApiError(404, "user_not_found", "No user has that email address.")
    membership = services.add_member(
        workspace, user, payload.role, actor=request.auth, request=request
    )
    return Status(201, _member_out(membership))


@router.patch("/{workspace_id}/members/{user_id}", response=MemberOut)
def change_member_role(
    request: SessionRequest, workspace_id: int, user_id: int, payload: MemberRoleIn
):
    workspace = _workspace(request, workspace_id, actions.WORKSPACE_MANAGE_MEMBERS)
    membership = services.change_role(
        workspace,
        _member(workspace, user_id),
        payload.role,
        actor=request.auth,
        request=request,
    )
    return _member_out(membership)


@router.delete("/{workspace_id}/members/{user_id}", response={204: None})
def remove_member(request: SessionRequest, workspace_id: int, user_id: int):
    workspace = _workspace(request, workspace_id, actions.WORKSPACE_MANAGE_MEMBERS)
    services.remove_member(
        workspace, _member(workspace, user_id), actor=request.auth, request=request
    )
    return Status(204, None)
