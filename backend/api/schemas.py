from typing import Literal

from accounts.passwords import MAX_EMAIL_LENGTH, MAX_PASSWORD_LENGTH
from ninja import Field, Schema


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
