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
