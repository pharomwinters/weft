"""Serves the single-page app's index.html for every non-API path.

The built assets themselves are served by WhiteNoise from FRONTEND_DIST; a
path it does not recognise falls through to here, and the SPA's own router
decides what to show.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponse

_NOT_BUILT = (
    "The frontend has not been built: index.html is missing from FRONTEND_DIST. "
    "Run `pnpm build` in frontend/, or use the container image."
)


def index(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    if request.path.startswith("/assets/"):
        # A built file WhiteNoise does not have (an old hash after a deploy):
        # a script must not be answered with a page of HTML.
        return HttpResponse("Not found.", status=404, content_type="text/plain")
    try:
        html = (settings.FRONTEND_DIST / "index.html").read_bytes()
    except OSError:
        return HttpResponse(_NOT_BUILT, status=503, content_type="text/plain")
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    # index.html names the current hashed assets, so it must always be fresh.
    response["Cache-Control"] = "no-cache"
    return response
