"""Workspace and membership changes, with their rules and audit records.

Callers check permissions first; these functions enforce the rules that hold
for everyone (a workspace keeps an owner, a member is added once).
"""

from datetime import timedelta

from accounts.models import User
from api.errors import ApiError
from audit import events
from audit.service import record
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from .models import NAME_MAX_LENGTH, Membership, Role, Workspace

RESTORE_WINDOW = timedelta(days=30)


def _clean_name(name: str) -> str:
    name = name.strip()
    if not 1 <= len(name) <= NAME_MAX_LENGTH:
        raise ApiError(
            400,
            "validation",
            "The request was not valid.",
            {"name": [f"A name must be 1 to {NAME_MAX_LENGTH} characters."]},
        )
    return name


def create(
    user: User,
    name: str,
    *,
    actor: User | None = None,
    request: HttpRequest | None = None,
) -> Workspace:
    """Create a workspace owned by `user`."""
    name = _clean_name(name)
    with transaction.atomic():
        workspace = Workspace.objects.create(name=name, created_by=user)
        Membership.objects.create(user=user, workspace=workspace, role=Role.OWNER)
        record(
            events.WORKSPACE_CREATED,
            request=request,
            actor=actor or user,
            target=workspace,
            details={"name": name},
        )
    return workspace


def rename(
    workspace: Workspace,
    name: str,
    *,
    actor: User | None = None,
    request: HttpRequest | None = None,
) -> None:
    workspace.name = _clean_name(name)
    workspace.save(update_fields=["name"])
    # Not an audited event in the spec's list; the name is in the row itself.


def soft_delete(
    workspace: Workspace,
    *,
    actor: User | None = None,
    request: HttpRequest | None = None,
) -> None:
    if workspace.deleted_at is not None:
        return
    workspace.deleted_at = timezone.now()
    workspace.save(update_fields=["deleted_at"])
    record(events.WORKSPACE_DELETED, request=request, actor=actor, target=workspace)


def restorable_since():
    """Workspaces deleted before this moment can no longer be restored."""
    return timezone.now() - RESTORE_WINDOW


def restore(
    workspace: Workspace,
    *,
    actor: User | None = None,
    request: HttpRequest | None = None,
) -> None:
    if workspace.deleted_at is None:
        return
    if workspace.deleted_at < restorable_since():
        raise ApiError(
            409, "restore_expired", "This workspace can no longer be restored."
        )
    workspace.deleted_at = None
    workspace.save(update_fields=["deleted_at"])
    record(events.WORKSPACE_RESTORED, request=request, actor=actor, target=workspace)


def add_member(
    workspace: Workspace,
    user: User,
    role: str,
    *,
    actor: User | None = None,
    request: HttpRequest | None = None,
) -> Membership:
    try:
        with transaction.atomic():
            membership = Membership.objects.create(
                user=user, workspace=workspace, role=Role(role)
            )
    except IntegrityError:
        raise ApiError(
            409, "already_member", "That user is already a member."
        ) from None
    record(
        events.MEMBERSHIP_ADDED,
        request=request,
        actor=actor,
        target=workspace,
        details={"user_id": user.pk, "role": membership.role},
    )
    return membership


def _locked_membership(workspace: Workspace, user: User) -> Membership:
    """The membership, with the workspace row locked for the owner count.

    Every change that could remove an owner takes this lock first, so two of
    them cannot each see the other's owner as still present.
    """
    Workspace.objects.select_for_update().get(pk=workspace.pk)
    membership = Membership.objects.filter(workspace=workspace, user=user).first()
    if membership is None:
        raise ApiError(404, "not_found", "Not found.")
    return membership


def _refuse_if_last_owner(workspace: Workspace, membership: Membership) -> None:
    if membership.role != Role.OWNER:
        return
    owners = Membership.objects.filter(workspace=workspace, role=Role.OWNER)
    if owners.count() <= 1:
        raise ApiError(409, "last_owner", "A workspace must keep at least one owner.")


def change_role(
    workspace: Workspace,
    user: User,
    role: str,
    *,
    actor: User | None = None,
    request: HttpRequest | None = None,
) -> Membership:
    new_role = Role(role)
    with transaction.atomic():
        membership = _locked_membership(workspace, user)
        old_role = membership.role
        if new_role != old_role:
            if new_role != Role.OWNER:
                _refuse_if_last_owner(workspace, membership)
            membership.role = new_role
            membership.save(update_fields=["role"])
            record(
                events.MEMBERSHIP_CHANGED,
                request=request,
                actor=actor,
                target=workspace,
                details={"user_id": user.pk, "from": old_role, "to": new_role.value},
            )
    return membership


def remove_member(
    workspace: Workspace,
    user: User,
    *,
    actor: User | None = None,
    request: HttpRequest | None = None,
) -> None:
    with transaction.atomic():
        membership = _locked_membership(workspace, user)
        _refuse_if_last_owner(workspace, membership)
        membership.delete()
        record(
            events.MEMBERSHIP_REMOVED,
            request=request,
            actor=actor,
            target=workspace,
            details={"user_id": user.pk, "role": membership.role},
        )
