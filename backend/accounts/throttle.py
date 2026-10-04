from datetime import timedelta

from audit import events
from audit.service import record
from axes.handlers.proxy import AxesProxyHandler
from axes.helpers import get_credentials
from django.contrib.auth.signals import user_login_failed
from django.http import HttpRequest
from django.utils import timezone

from .models import IpFailure, normalize_email
from .net import client_ip

ACCOUNT_LIMIT = 5
IP_LIMIT = 20
WINDOW = timedelta(minutes=15)
_PRUNE_AFTER = timedelta(days=1)

# The per-account limit and window are configured in settings
# (AXES_FAILURE_LIMIT, AXES_COOLOFF_TIME); these must agree with them.


def _axes_request(request: HttpRequest) -> HttpRequest:
    """A throwaway request for axes, so its per-request caches never go stale.

    axes stamps the attempt time and address onto the request the first time
    it sees it; a long-lived request would keep an old time.
    """
    fresh = HttpRequest()
    fresh.META = dict(request.META)
    fresh.path = fresh.path_info = request.path
    fresh.method = request.method
    return fresh


def _credentials(email: str) -> dict:
    return get_credentials(email)


def _account_locked(request: HttpRequest, email: str) -> bool:
    return AxesProxyHandler.is_locked(_axes_request(request), _credentials(email))


def _ip_failures(ip: str) -> int:
    return IpFailure.objects.filter(ip=ip, created__gte=timezone.now() - WINDOW).count()


def is_blocked(request: HttpRequest, email: str | None) -> bool:
    if _ip_failures(client_ip(request)) >= IP_LIMIT:
        return True
    return email is not None and _account_locked(request, normalize_email(email))


def record_failure(request: HttpRequest, email: str | None) -> None:
    details: dict = {}
    if email is not None:
        email = normalize_email(email)
        details["email"] = email
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
    before = _ip_failures(ip)
    now = timezone.now()
    IpFailure.objects.create(ip=ip, created=now)
    IpFailure.objects.filter(created__lt=now - _PRUNE_AFTER).delete()
    if before < IP_LIMIT <= before + 1:
        record(events.LOCKOUT, request=request, details={"scope": "ip"})


def record_success(request: HttpRequest, email: str) -> None:
    reset_account(email)


def reset_account(email: str) -> None:
    email = normalize_email(email)
    if email:  # axes treats an empty username as "every account"
        AxesProxyHandler.reset_attempts(username=email)
