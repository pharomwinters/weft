"""Invitation links: how a new user joins, with no mail server involved."""

from datetime import timedelta

from api.errors import ApiError
from audit import events
from audit.service import record
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone
from workspaces import services as workspace_services
from workspaces.models import Workspace

from .emails import clean_email
from .models import Invitation, User
from .passwords import validate_new_password
from .tokens import hash_token, new_token

INVITATION_LIFETIME = timedelta(days=7)


def pending() -> QuerySet[Invitation]:
    """Invitations that can still be accepted."""
    return Invitation.objects.filter(
        Q(workspace__isnull=True) | Q(workspace__deleted_at__isnull=True),
        used_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    )


def create(
    creator: User,
    workspace: Workspace | None,
    role: str | None,
    *,
    request: HttpRequest | None = None,
) -> tuple[Invitation, str]:
    """A new invitation and its URL. The URL is the only copy of the token."""
    token, token_hash = new_token()
    invitation = Invitation.objects.create(
        token_hash=token_hash,
        created_by=creator,
        workspace=workspace,
        role=role if workspace is not None else None,
        expires_at=timezone.now() + INVITATION_LIFETIME,
    )
    record(
        events.INVITATION_CREATED,
        request=request,
        actor=creator,
        target=invitation,
        details={
            "workspace_id": workspace.pk if workspace else None,
            "role": invitation.role,
        },
    )
    return invitation, f"{settings.PUBLIC_URL}/invite/{token}"


def find(token: str) -> Invitation | None:
    """The pending invitation for a token; None for any dead or unknown one."""
    return (
        pending()
        .filter(token_hash=hash_token(token))
        .select_related("workspace")
        .first()
    )


def revoke(invitation: Invitation) -> None:
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at"])


def accept(
    token: str, email: str, password: str, *, request: HttpRequest | None = None
) -> User | None:
    """Create the invited user; None if the token is dead or unknown.

    The invitation row is locked until the user exists and the invitation is
    marked used, so a token is consumed exactly once.
    """
    with transaction.atomic():
        invitation = (
            pending()
            .select_for_update(of=("self",))
            .filter(token_hash=hash_token(token))
        ).first()
        if invitation is None:
            return None
        email = clean_email(email)
        validate_new_password(password, User(email=email))
        try:
            with transaction.atomic():
                user = User.objects.create_user(email, password)
        except IntegrityError:
            raise ApiError(
                409, "email_taken", "That email address is already in use."
            ) from None
        invitation.used_at = timezone.now()
        invitation.used_by = user
        invitation.save(update_fields=["used_at", "used_by"])
        if invitation.workspace is not None and invitation.role is not None:
            workspace_services.add_member(
                invitation.workspace, user, invitation.role, actor=user, request=request
            )
        record(
            events.INVITATION_ACCEPTED, request=request, actor=user, target=invitation
        )
    return user
