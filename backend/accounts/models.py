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
