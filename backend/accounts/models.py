from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower

from .passwords import MAX_EMAIL_LENGTH


def normalize_email(raw: str) -> str:
    return raw.strip().lower()


class UserManager(BaseUserManager["User"]):
    def create_user(self, email: str, password: str, **extra) -> "User":
        email = normalize_email(email)
        if not email:
            raise ValueError("An email address is required.")
        if len(email) > MAX_EMAIL_LENGTH:
            raise ValueError(
                f"The email address is too long (maximum {MAX_EMAIL_LENGTH} characters)."
            )
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    email = models.EmailField(max_length=MAX_EMAIL_LENGTH, unique=True)
    is_instance_admin = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Raised whenever the user's sessions are ended. A half-finished login
    # started under an older value is dead, though it has no UserSession row.
    session_epoch = models.PositiveIntegerField(default=0)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_uniq")
        ]


class IpFailure(models.Model):
    """One failed attempt from one client address, for per-address blocking."""

    ip = models.CharField(max_length=45)
    created = models.DateTimeField()

    objects = models.Manager["IpFailure"]()

    class Meta:
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["ip", "created"], name="accounts_ipfailure_ip_created")
        ]


class IpBlock(models.Model):
    """An address blocked until a fixed time, set when it crosses the limit."""

    ip = models.CharField(max_length=45, unique=True)
    blocked_until = models.DateTimeField()

    objects = models.Manager["IpBlock"]()


class TotpDevice(models.Model):
    """A TOTP secret, encrypted at rest. Pending until a code confirms it."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    secret_encrypted = models.TextField()
    confirmed = models.BooleanField(default=False)
    # The last accepted time step; a code for it or an earlier one is a replay.
    last_step = models.BigIntegerField(null=True)

    objects = models.Manager["TotpDevice"]()

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            # At most one confirmed and one unconfirmed device per user.
            models.UniqueConstraint(
                fields=["user", "confirmed"], name="accounts_totpdevice_user_confirmed"
            )
        ]


class RecoveryCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True)

    objects = models.Manager["RecoveryCode"]()

    class Meta:
        indexes: ClassVar[list[models.Index]] = [
            models.Index(
                fields=["user", "code_hash"], name="accounts_recovery_user_hash"
            )
        ]


USER_AGENT_LENGTH = 512


class UserSession(models.Model):
    """One verified session, so its owner can list and revoke it."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    session_key = models.CharField(max_length=40, unique=True)
    ip = models.GenericIPAddressField(null=True)
    user_agent = models.CharField(max_length=USER_AGENT_LENGTH, blank=True)
    created = models.DateTimeField()
    last_seen = models.DateTimeField()

    objects = models.Manager["UserSession"]()


class SetupToken(models.Model):
    """The hash of the current first-run setup token. At most one row."""

    token_hash = models.CharField(max_length=64)
    created = models.DateTimeField(auto_now_add=True)

    objects = models.Manager["SetupToken"]()


class Invitation(models.Model):
    """A single-use link that lets a new user join, optionally into a workspace."""

    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace", null=True, on_delete=models.CASCADE, related_name="+"
    )
    role = models.CharField(max_length=16, null=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)
    used_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    revoked_at = models.DateTimeField(null=True)

    objects = models.Manager["Invitation"]()


class ResetLink(models.Model):
    """A single-use link that lets a user set a new password."""

    token_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    # Null when the link was made by the management command.
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)

    objects = models.Manager["ResetLink"]()
