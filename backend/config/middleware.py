import json

from accounts import sessions

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response["Referrer-Policy"] = "no-referrer"
        return response


class ApiMethodNotAllowedMiddleware:
    """Gives Ninja's bare 405 the API error shape.

    Ninja answers a wrong method from the path view, outside its exception
    handlers, so the shape is applied to the response instead.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code != 405 or not request.path.startswith("/api/"):
            return response
        body = {
            "error": {
                "code": "method_not_allowed",
                "message": "Method not allowed.",
                "details": {},
            }
        }
        # Rewritten in place so headers set by other middleware survive.
        response.content = json.dumps(body).encode()
        response["Content-Type"] = "application/json"
        return response


class LastSeenMiddleware:
    """Keeps UserSession.last_seen current for the account's session list."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        sessions.touch(request)
        return self.get_response(request)
