import pytest
from api.errors import ApiError, register_error_handlers
from config import urls as config_urls
from django.urls import path
from ninja import NinjaAPI, Schema

# Test-only routes live on a separate API instance served by a test URLconf, so
# nothing here is registered on the production `api`.
test_api = NinjaAPI(urls_namespace="test", docs_url=None, openapi_url=None)
register_error_handlers(test_api)


class Named(Schema):
    name: str


@test_api.get("/_test/api-error")
def raise_api_error(request):
    raise ApiError(409, "x", "msg", {"a": 1})


@test_api.post("/_test/validated")
def validated(request, payload: Named):
    return {"name": payload.name}


@test_api.get("/_test/http-error")
def raise_http_error(request):
    from ninja.errors import HttpError

    raise HttpError(418, "teapot")


@test_api.get("/_test/boom")
def boom(request):
    raise RuntimeError("secret detail")


@test_api.get("/_test/denied", auth=lambda request: None)
def denied(request):
    return {}


# The real URLconf with the test API mounted ahead of it.
urlpatterns = [path("api/v1/", test_api.urls), *config_urls.urlpatterns]


def test_health(api_client):
    assert api_client.get("/health").json() == {"status": "ok"}


def test_unknown_api_route_is_json_404(api_client):
    r = api_client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


@pytest.mark.urls(__name__)
def test_api_error_shape(api_client):
    r = api_client.get("/_test/api-error")
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "x", "message": "msg", "details": {"a": 1}}}


@pytest.mark.urls(__name__)
def test_validation_error_shape(api_client):
    r = api_client.post("/_test/validated", json={})
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation"
    assert "name" in r.json()["error"]["details"]


def test_security_headers(api_client):
    r = api_client.get("/health")
    assert r["X-Frame-Options"] == "DENY" and r["Referrer-Policy"] == "no-referrer"
    assert "default-src 'self'" in r["Content-Security-Policy"]


def test_post_to_unknown_api_route_is_json_404_even_with_csrf_checks():
    from django.test import Client

    r = Client(enforce_csrf_checks=True).post("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_wrong_method_is_json_405(api_client):
    r = api_client.post("/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in r["Allow"]
    assert "Content-Security-Policy" in r
    assert r["Referrer-Policy"] == "no-referrer"
    assert r["X-Frame-Options"] == "DENY"


@pytest.mark.urls(__name__)
def test_ninja_http_error_is_shaped(api_client):
    r = api_client.get("/_test/http-error")
    assert r.status_code == 418
    assert r.json() == {"error": {"code": "error", "message": "teapot", "details": {}}}


@pytest.mark.urls(__name__)
def test_ninja_authentication_error_is_shaped(api_client):
    r = api_client.get("/_test/denied")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "auth_required"


@pytest.mark.urls(__name__)
def test_unhandled_exception_is_500_internal_without_detail(api_client):
    r = api_client.get("/_test/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal"
    assert "secret detail" not in r.content.decode()
