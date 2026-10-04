from typing import Any, NoReturn

from django.conf import settings
from django.db import models


class AppendOnlyQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise RuntimeError("Audit events are append-only and cannot be updated.")

    def delete(self) -> NoReturn:
        raise RuntimeError("Audit events are append-only and cannot be deleted.")


class AuditEvent(models.Model):
    time = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    event = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    ip = models.GenericIPAddressField(null=True)
    details = models.JSONField(default=dict)

    objects = AppendOnlyQuerySet.as_manager()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise RuntimeError("Audit events are append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise RuntimeError("Audit events are append-only and cannot be deleted.")
