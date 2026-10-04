import logging
from typing import Any

from django.http import Http404, HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError, ValidationError

logger = logging.getLogger(__name__)

_HTTP_ERROR_CODES = {
    400: "validation",
    401: "auth_required",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    429: "rate_limited",
}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def _error_response(
    api: NinjaAPI,
    request: HttpRequest,
    status: int,
    code: str,
    message: str,
    details: dict[str, Any],
) -> HttpResponse:
    body = {"error": {"code": code, "message": message, "details": details}}
    return api.create_response(request, body, status=status)


def _validation_details(errors: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Group Ninja's error list by field name (the last path element)."""
    details: dict[str, list[str]] = {}
    for error in errors:
        field = str(error["loc"][-1])
        details.setdefault(field, []).append(error["msg"])
    return details


def register_error_handlers(api: NinjaAPI) -> None:
    @api.exception_handler(ApiError)
    def handle_api_error(request: HttpRequest, exc: ApiError) -> HttpResponse:
        return _error_response(
            api, request, exc.status, exc.code, exc.message, exc.details
        )

    @api.exception_handler(ValidationError)
    def handle_validation_error(
        request: HttpRequest, exc: ValidationError
    ) -> HttpResponse:
        return _error_response(
            api,
            request,
            400,
            "validation",
            "The request was not valid.",
            _validation_details(exc.errors),
        )

    @api.exception_handler(Http404)
    def handle_not_found(request: HttpRequest, exc: Http404) -> HttpResponse:
        return _error_response(api, request, 404, "not_found", "Not found.", {})

    @api.exception_handler(HttpError)
    def handle_http_error(request: HttpRequest, exc: HttpError) -> HttpResponse:
        code = _HTTP_ERROR_CODES.get(exc.status_code, "error")
        return _error_response(api, request, exc.status_code, code, str(exc), {})

    @api.exception_handler(AuthenticationError)
    def handle_authentication_error(
        request: HttpRequest, exc: AuthenticationError
    ) -> HttpResponse:
        return _error_response(
            api,
            request,
            401,
            "auth_required",
            "Authentication is required.",
            {"session": "anonymous", "next": "login"},
        )

    @api.exception_handler(Exception)
    def handle_unexpected(request: HttpRequest, exc: Exception) -> HttpResponse:
        logger.exception("Unhandled error in the API", exc_info=exc)
        return _error_response(
            api, request, 500, "internal", "Something went wrong.", {}
        )
