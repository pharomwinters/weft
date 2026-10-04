from typing import Any

from accounts.models import User
from accounts.net import client_ip
from django.db.models import Model
from django.http import HttpRequest

from .models import AuditEvent

FORBIDDEN_DETAIL_KEYS = {"password", "new_password", "code", "token", "secret"}


def _check_details(value: Any) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            if str(key).lower() in FORBIDDEN_DETAIL_KEYS:
                raise ValueError(f"Audit details must not contain the key {key!r}.")
            _check_details(inner)
    elif isinstance(value, list | tuple):
        for inner in value:
            _check_details(inner)


def record(
    event: str,
    *,
    request: HttpRequest | None = None,
    actor: User | None = None,
    target: Model | None = None,
    details: dict | None = None,
) -> AuditEvent:
    details = details or {}
    _check_details(details)
    return AuditEvent.objects.create(
        event=event,
        actor=actor,
        target_type=type(target).__name__.lower() if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        ip=client_ip(request) if request is not None else None,
        details=details,
    )
