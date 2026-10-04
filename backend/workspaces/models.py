from typing import ClassVar

from django.conf import settings
from django.db import models

NAME_MAX_LENGTH = 100


class Role(models.TextChoices):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class Workspace(models.Model):
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Set when the workspace is deleted; it can be restored for a while after.
    deleted_at = models.DateTimeField(null=True)

    objects = models.Manager["Workspace"]()


class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    role = models.CharField(max_length=16, choices=Role.choices)

    objects = models.Manager["Membership"]()

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["user", "workspace"], name="workspaces_membership_user_ws"
            )
        ]
