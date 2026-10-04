import re

import pytest
from api.access import ANONYMOUS, PARTIAL
from api.api import api
from api.auth import verified
from api.errors import register_error_handlers
from config import urls as config_urls
from django.urls import path
from ninja import NinjaAPI

# A route that needs a verified session, served from a separate API instance
# ahead of the real one so the real `api` stays untouched.
test_api = NinjaAPI(
    urls_namespace="deny", auth=verified, docs_url=None, openapi_url=None
)
register_error_handlers(test_api)


@test_api.get("/_test/verified-only")
def verified_only(request):
    return {}


urlpatterns = [path("api/v1/", test_api.urls), *config_urls.urlpatterns]
pytestmark = pytest.mark.urls(__name__)


def _routes(a: NinjaAPI):
    schema = a.get_openapi_schema(path_prefix="")
    return [
        (method.upper(), template)
        for template, ops in schema["paths"].items()
        for method in ops
    ]


def all_routes():
    """(METHOD, path template) for every route on the real API and the test one."""
    return _routes(api) + _routes(test_api)


def _concrete(template: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", template)


ROUTES = all_routes()


@pytest.mark.parametrize("method,template", ROUTES)
def test_unlisted_route_refuses_anonymous(api_client, method, template):
    if (method, template) in ANONYMOUS:
        pytest.skip("listed as anonymous")
    r = getattr(api_client, method.lower())(_concrete(template))
    assert r.status_code == 401
    assert r.json()["error"]["details"] == {"session": "anonymous", "next": "login"}


@pytest.mark.parametrize("method,template", ROUTES)
def test_unlisted_route_refuses_partial(partial_client, method, template):
    if (method, template) in ANONYMOUS | PARTIAL:
        pytest.skip("listed as reachable without a verified session")
    r = getattr(partial_client, method.lower())(_concrete(template))
    assert r.status_code == 401
    assert r.json()["error"]["details"]["session"] == "partial"


def test_the_test_route_is_exercised():
    unlisted = [r for r in ROUTES if r not in ANONYMOUS | PARTIAL]
    assert ("GET", "/_test/verified-only") in unlisted


def test_access_lists_contain_no_stale_entries():
    real = set(_routes(api))
    assert real >= ANONYMOUS | PARTIAL


def test_access_lists_are_exactly_as_specified():
    assert {
        ("GET", "/health"),
        ("GET", "/auth/session"),
        ("POST", "/auth/login"),
    } == ANONYMOUS
    assert {("POST", "/auth/logout")} == PARTIAL


def test_health_is_listed_anonymous(api_client):
    assert ("GET", "/health") in ANONYMOUS
    assert api_client.get("/health").status_code == 200
