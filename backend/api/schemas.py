from datetime import datetime
from typing import Literal

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
