import ipaddress

from django.conf import settings
from django.http import HttpRequest


def _parse(text: str) -> str | None:
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        return None


def client_ip(request: HttpRequest) -> str:
    """The client's address, trusting exactly TRUSTED_PROXY_COUNT proxies.

    With n trusted proxies the client is the n-th entry from the right of
    X-Forwarded-For; entries further left are client-supplied and ignored.
    Anything unusable falls back to REMOTE_ADDR.
    """
    remote = request.META.get("REMOTE_ADDR", "")
    count = settings.TRUSTED_PROXY_COUNT
    header = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if count <= 0 or not header:
        return remote
    entries = header.split(",")
    if len(entries) < count:
        return remote
    return _parse(entries[-count]) or remote
