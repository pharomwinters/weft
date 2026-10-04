"""can(user, action, target): the one place that decides who may do what."""

from accounts.models import User
from api.errors import ApiError
from django.db.models import QuerySet
from workspaces.models import Membership, Role, Workspace

from . import actions


class _Instance:
    def __repr__(self) -> str:
        return "INSTANCE"


INSTANCE = _Instance()

# Instance admins only, on the instance.
ADMIN_ACTIONS = frozenset(
    {
        actions.INSTANCE_MANAGE_USERS,
        actions.INSTANCE_CREATE_INVITATION,
        actions.INSTANCE_VIEW_AUDIT_LOG,
    }
)
# Any active user, on the instance.
USER_ACTIONS = frozenset({actions.WORKSPACE_CREATE})

_OWNER_ACTIONS = frozenset(
    {
        actions.WORKSPACE_VIEW,
        actions.WORKSPACE_RENAME,
        actions.WORKSPACE_MANAGE_MEMBERS,
        actions.WORKSPACE_INVITE,
        actions.WORKSPACE_DELETE,
        actions.WORKSPACE_RESTORE,
    }
)
# What a membership role allows on its workspace. Instance admins may do all
# of it on every workspace. Editor and viewer diverge once bases exist.
ROLE_ACTIONS: dict[Role, frozenset[str]] = {
    Role.OWNER: _OWNER_ACTIONS,
    Role.EDITOR: frozenset({actions.WORKSPACE_VIEW}),
    Role.VIEWER: frozenset({actions.WORKSPACE_VIEW}),
}


def _check_action(action: str, target: object) -> None:
    on_instance = target is INSTANCE
    if not on_instance and not isinstance(target, Workspace):
        raise ValueError(f"Unknown permission target: {target!r}")
    known = ADMIN_ACTIONS | USER_ACTIONS if on_instance else _OWNER_ACTIONS
    if action not in known:
        raise ValueError(f"Unknown action {action!r} for target {target!r}")


def can(user: User, action: str, target: object) -> bool:
    _check_action(action, target)
    if not user.is_active:
        return False
    if not isinstance(target, Workspace):
        return action in USER_ACTIONS or user.is_instance_admin
    # A deleted workspace is invisible to everything except its restoration.
    if target.deleted_at is not None and action != actions.WORKSPACE_RESTORE:
        return False
    if user.is_instance_admin:
        return True
    membership = Membership.objects.filter(user=user, workspace=target).first()
    return membership is not None and action in ROLE_ACTIONS[Role(membership.role)]


def require(user: User, action: str, target: object) -> None:
    """Raise unless allowed: 404 for a workspace the user cannot see, else 403."""
    if can(user, action, target):
        return
    if isinstance(target, Workspace) and not can(user, actions.WORKSPACE_VIEW, target):
        raise ApiError(404, "not_found", "Not found.")
    raise ApiError(403, "forbidden", "You are not allowed to do that.")


def workspaces_for(user: User, action: str) -> QuerySet[Workspace]:
    """The workspaces on which can(user, action, workspace) holds."""
    if action not in _OWNER_ACTIONS:
        raise ValueError(f"Unknown workspace action {action!r}")
    if not user.is_active:
        return Workspace.objects.none()
    found = Workspace.objects.all()
    if action != actions.WORKSPACE_RESTORE:
        found = found.filter(deleted_at__isnull=True)
    if user.is_instance_admin:
        return found
    roles = [role for role, allowed in ROLE_ACTIONS.items() if action in allowed]
    return found.filter(membership__user=user, membership__role__in=roles)
