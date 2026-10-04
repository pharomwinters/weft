from accounts.sessions import SessionRequest
from audit.models import AuditEvent
from ninja import Router
from permissions import actions
from permissions.core import INSTANCE, require

from ..schemas import AuditPageOut

router = Router()

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@router.get("", response=AuditPageOut)
def list_events(
    request: SessionRequest,
    event: str | None = None,
    actor_id: int | None = None,
    before: int | None = None,
    limit: int = DEFAULT_LIMIT,
):
    """Audit events, newest first. Pass next_before as `before` for the next page."""
    require(request.auth, actions.INSTANCE_VIEW_AUDIT_LOG, INSTANCE)
    limit = max(1, min(limit, MAX_LIMIT))
    found = AuditEvent.objects.select_related("actor").order_by("-pk")
    if event:
        found = found.filter(event=event)
    if actor_id is not None:
        found = found.filter(actor_id=actor_id)
    if before is not None:
        found = found.filter(pk__lt=before)
    rows = list(found[: limit + 1])
    page = rows[:limit]
    return {
        "items": [
            {
                "id": row.pk,
                "time": row.time,
                "event": row.event,
                "actor_email": row.actor.email if row.actor else None,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "ip": row.ip,
                "details": row.details,
            }
            for row in page
        ],
        "next_before": page[-1].pk if len(rows) > limit else None,
    }
