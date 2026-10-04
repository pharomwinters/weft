from api.errors import ApiError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

MAX_PASSWORD_LENGTH = 1024
MAX_EMAIL_LENGTH = 254


def validate_new_password(password: str, user=None) -> None:
    """Raise ApiError(400) unless the password meets the rules.

    The length ceiling is checked before anything else so an oversized value
    never reaches a validator or a hasher.
    """
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ApiError(
            400,
            "validation",
            "The password is not acceptable.",
            {
                "password": [
                    f"This password is too long (maximum {MAX_PASSWORD_LENGTH} characters)."
                ]
            },
        )
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ApiError(
            400,
            "validation",
            "The password is not acceptable.",
            {"password": list(exc.messages)},
        ) from exc
