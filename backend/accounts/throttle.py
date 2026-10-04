from datetime import timedelta

from audit import events
from audit.service import record
from axes.handlers.proxy import AxesProxyHandler
from axes.helpers import get_credentials
from django.contrib.auth.signals import user_login_failed
from django.http import HttpRequest
from django.utils import timezone

from .models import IpBlock, IpFailure, normalize_email
from .net import client_ip
from .passwords import MAX_EMAIL_LENGTH

ACCOUNT_LIMIT = 5
IP_LIMIT = 20
WINDOW = timedelta(minutes=15)
_PRUNE_AFTER = timedelta(days=1)

# The per-account limit and window are configured in settings
# (AXES_FAILURE_LIMIT, AXES_COOLOFF_TIME); these must agree with them.


def _axes_request(request: HttpRequest) -> HttpRequest:
    """A throwaway request for axes.

    axes caches the attempt time on the request it sees, and keeps one row per
    (username, address, user agent), each aging out on its own. A constant
    address and no user agent make every failure of an account share one row,
    so a lock always lasts the full window from the latest failure. The real
    address is counted by IpFailure and written to the audit log.
    """
    fresh = HttpRequest()
    fresh.META = {"REMOTE_ADDR": "127.0.0.1"}
    fresh.path = fresh.path_info = request.path
    fresh.method = request.method
    return fresh


def _usable_email(email: str | None) -> str | None:
    """The normalised email, or None when absent or too long to be one.

    axes stores the username in a 255-character column.
    """
    if email is None:
        return None
    email = normalize_email(email)
    return email if len(email) <= MAX_EMAIL_LENGTH else None


def _credentials(email: str) -> dict:
    return get_credentials(email)


def _account_locked(request: HttpRequest, email: str) -> bool:
    return AxesProxyHandler.is_locked(_axes_request(request), _credentials(email))


def _ip_blocked(ip: str) -> bool:
    return IpBlock.objects.filter(ip=ip, blocked_until__gt=timezone.now()).exists()


def is_blocked(request: HttpRequest, email: str | None) -> bool:
    if _ip_blocked(client_ip(request)):
        return True
    email = _usable_email(email)
    return email is not None and _account_locked(request, email)


def record_failure(request: HttpRequest, email: str | None) -> None:
    email = _usable_email(email)
    details: dict = {} if email is None else {"email": email}
    record(events.LOGIN_FAILURE, request=request, details=details)

    if email is not None and not _account_locked(request, email):
        user_login_failed.send(
            sender=__name__,
            credentials=_credentials(email),
            request=_axes_request(request),
        )
        if _account_locked(request, email):
            record(events.LOCKOUT, request=request, details={"scope": "account"})

    ip = client_ip(request)
    if _ip_blocked(ip):
        return  # failures during a block neither count nor extend it
    now = timezone.now()
    IpFailure.objects.create(ip=ip, created=now)
    IpFailure.objects.filter(created__lt=now - _PRUNE_AFTER).delete()
    IpBlock.objects.filter(blocked_until__lt=now - _PRUNE_AFTER).delete()
    if IpFailure.objects.filter(ip=ip, created__gte=now - WINDOW).count() >= IP_LIMIT:
        IpBlock.objects.update_or_create(
            ip=ip, defaults={"blocked_until": now + WINDOW}
        )
        record(events.LOCKOUT, request=request, details={"scope": "ip"})


def record_success(request: HttpRequest, email: str) -> None:
    reset_account(email)


def reset_account(email: str) -> None:
    usable = _usable_email(email)
    if usable:  # axes treats an empty username as "every account"
        AxesProxyHandler.reset_attempts(username=usable)
