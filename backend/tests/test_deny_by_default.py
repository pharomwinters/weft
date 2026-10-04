import re

import pytest
from api.access import ANONYMOUS, PARTIAL
from api.api import api
from api.auth import verified
from api.errors import register_error_handlers
from config import urls as config_urls
from django.urls import URLPattern, URLResolver, path
from ninja import NinjaAPI
from ninja.utils import normalize_path

# A route that needs a verified session, served from a separate API instance
# ahead of the real one so the real `api` stays untouched.
test_api = NinjaAPI(
    urls_namespace="deny", auth=verified, docs_url=None, openapi_url=None
)
register_error_handlers(test_api)


@test_api.get("/_test/verified-only")
def verified_only(request):
    return {}


@test_api.get("/_test/hidden", include_in_schema=False)
def hidden(request):
    return {}


urlpatterns = [path("api/v1/", test_api.urls), *config_urls.urlpatterns]
pytestmark = pytest.mark.urls(__name__)


def _routes(a: NinjaAPI):
    """Every registered (METHOD, path template), including hidden ones.

    Walks the bound routers rather than the OpenAPI schema, which omits any
    operation declared with include_in_schema=False.
    """
    routes = []
    for bound in a._get_bound_routers():
        for template, path_view in bound.path_operations.items():
            full = normalize_path("/".join(i for i in (bound.prefix, template) if i))
            routes.extend(
                (method, full) for op in path_view.operations for method in op.methods
            )
    return routes


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
        ("GET", "/setup/status"),
        ("POST", "/setup/admin"),
        ("GET", "/invitations/token/{token}"),
        ("POST", "/invitations/token/{token}/accept"),
        ("GET", "/auth/reset/{token}"),
        ("POST", "/auth/reset/{token}"),
    } == ANONYMOUS
    assert {
        ("POST", "/auth/logout"),
        ("POST", "/auth/enrol/start"),
        ("POST", "/auth/enrol/confirm"),
        ("POST", "/auth/verify"),
        ("POST", "/auth/recovery"),
        ("POST", "/auth/password/forced"),
    } == PARTIAL


def test_health_is_listed_anonymous(api_client):
    assert ("GET", "/health") in ANONYMOUS
    assert api_client.get("/health").status_code == 200


def test_walk_sees_routes_hidden_from_the_schema(api_client):
    schema_paths = test_api.get_openapi_schema(path_prefix="")["paths"]
    assert "/_test/hidden" not in schema_paths
    assert ("GET", "/_test/hidden") in ROUTES
    r = api_client.get("/_test/hidden")
    assert r.status_code == 401
    assert r.json()["error"]["details"]["session"] == "anonymous"


def test_api_urls_are_only_the_api_mount_and_the_catch_all():
    patterns = config_urls.urlpatterns
    assert len(patterns) == 2
    mount, catch_all = patterns
    assert isinstance(mount, URLResolver) and isinstance(catch_all, URLPattern)
    assert str(mount.pattern) == "api/v1/"
    assert mount.namespace == api.urls_namespace
    assert [str(p.pattern) for p in mount.url_patterns] == [
        str(p.pattern) for p in api.urls[0]
    ]
    assert str(catch_all.pattern) == "^api/"
    assert catch_all.callback is config_urls.api_not_found
