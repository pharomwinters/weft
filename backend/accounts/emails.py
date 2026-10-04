from api.errors import ApiError
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import normalize_email
from .passwords import MAX_EMAIL_LENGTH


def clean_email(raw: str) -> str:
    """The normalised address, or ApiError(400) if it is not one."""
    email = normalize_email(raw)
    try:
        if len(email) > MAX_EMAIL_LENGTH:
            raise ValidationError("too long")
        validate_email(email)
    except ValidationError:
        raise ApiError(
            400,
            "validation",
            "The email address is not acceptable.",
            {"email": ["Enter a valid email address."]},
        ) from None
    return email
