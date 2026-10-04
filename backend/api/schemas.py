from datetime import datetime
from typing import Any, Literal

from accounts.passwords import MAX_EMAIL_LENGTH, MAX_PASSWORD_LENGTH
from ninja import Field, Schema

# Tokens are 43 characters; anything much longer is not one.
MAX_TOKEN_LENGTH = 128


class LoginIn(Schema):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class LoginOut(Schema):
    next: Literal["verify", "enrol"]


class UserOut(Schema):
    id: int
    email: str
    is_instance_admin: bool


class SessionOut(Schema):
    state: Literal["anonymous", "partial", "verified"]
    next: str | None
    user: UserOut | None


class CodeIn(Schema):
    # Longer than any TOTP or recovery code with separators; the rest is noise.
    code: str = Field(max_length=64)


class EnrolStartOut(Schema):
    secret: str
    otpauth_uri: str


class SecondFactorOut(Schema):
    next: Literal["change_password"] | None


class EnrolConfirmOut(SecondFactorOut):
    recovery_codes: list[str]


class ForcedPasswordIn(Schema):
    new_password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class PasswordChangeIn(Schema):
    current_password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class SessionItemOut(Schema):
    id: int
    ip: str | None
    user_agent: str
    created: datetime
    last_seen: datetime
    current: bool


class RecoveryCodesOut(Schema):
    recovery_codes: list[str]


class SetupStatusOut(Schema):
    needs_setup: bool


class SetupIn(Schema):
    token: str = Field(max_length=MAX_TOKEN_LENGTH)
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


RoleName = Literal["owner", "editor", "viewer"]


class WorkspaceIn(Schema):
    # Generous here; the service trims and applies the real 1-100 rule.
    name: str = Field(max_length=1000)


class WorkspaceOut(Schema):
    id: int
    name: str
    role: RoleName | None
    deleted_at: datetime | None


class MemberAddIn(Schema):
    email: str = Field(max_length=MAX_EMAIL_LENGTH + 32)
    role: RoleName


class MemberRoleIn(Schema):
    role: RoleName


class MemberOut(Schema):
    user_id: int
    email: str
    role: RoleName


class InvitationIn(Schema):
    workspace_id: int | None = None
    role: RoleName | None = None


class InvitationCreatedOut(Schema):
    id: int
    url: str
    expires_at: datetime


class InvitationOut(Schema):
    id: int
    workspace_id: int | None
    workspace_name: str | None
    role: RoleName | None
    created_by_email: str | None
    expires_at: datetime


class InvitationInfoOut(Schema):
    workspace_name: str | None
    role: RoleName | None


class InvitationAcceptIn(Schema):
    email: str = Field(max_length=MAX_EMAIL_LENGTH)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class AdminUserOut(Schema):
    id: int
    email: str
    is_instance_admin: bool
    is_active: bool
    has_2fa: bool
    created_at: datetime


class AdminFlagIn(Schema):
    is_instance_admin: bool


class ResetLinkOut(Schema):
    url: str
    expires_at: datetime


class ResetPasswordIn(Schema):
    new_password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class AuditEventOut(Schema):
    id: int
    time: datetime
    event: str
    actor_email: str | None
    target_type: str
    target_id: str
    ip: str | None
    details: dict[str, Any]


class AuditPageOut(Schema):
    items: list[AuditEventOut]
    next_before: int | None
