import pytest
from django.test import Client


@pytest.fixture
def dist(settings, tmp_path):
    """A built frontend in a temporary directory, as `pnpm build` leaves it."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>app</title>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('app')")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    settings.FRONTEND_DIST = tmp_path
    settings.WHITENOISE_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def client(dist):
    # Created after the settings change: WhiteNoise reads its root when the
    # middleware is built, which happens on a client's first request.
    return Client()


@pytest.mark.parametrize("path", ["/", "/login", "/workspaces/7", "/invite/some-token"])
def test_spa_route_serves_index(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert r["Content-Type"].startswith("text/html")
    assert b"<title>app</title>" in r.content


@pytest.mark.parametrize("path", ["/api/v1/nope", "/api/nope", "/api/"])
def test_api_404_is_json_not_index(client, path):
    r = client.get(path)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_index_is_not_cached_but_hashed_assets_are(client):
    assert client.get("/login")["Cache-Control"] == "no-cache"
    asset = client.get("/assets/index-abc123.js")
    assert asset.status_code == 200
    assert b"".join(asset.streaming_content) == b"console.log('app')"
    assert "immutable" in asset["Cache-Control"]
    assert "max-age=315360000" in asset["Cache-Control"]
    plain = client.get("/favicon.svg")
    assert plain.status_code == 200 and "immutable" not in plain["Cache-Control"]


def test_missing_asset_is_404_not_index(client):
    r = client.get("/assets/index-oldhash.js")
    assert r.status_code == 404 and b"<title>" not in r.content


def test_static_files_and_index_carry_the_security_headers(client):
    for path in ("/login", "/assets/index-abc123.js"):
        r = client.get(path)
        assert "default-src 'self'" in r["Content-Security-Policy"]
        assert r["Referrer-Policy"] == "no-referrer"


def test_files_outside_dist_are_not_served(client, dist):
    (dist.parent / "secret.txt").write_text("outside")
    r = client.get("/../secret.txt")
    assert b"outside" not in getattr(r, "content", b"")
    r = client.get("/assets/../../secret.txt")
    assert b"outside" not in getattr(r, "content", b"")


def test_missing_dist_gives_clear_503(settings, tmp_path):
    settings.FRONTEND_DIST = tmp_path / "nowhere"
    settings.WHITENOISE_ROOT = None
    r = Client().get("/login")
    assert r.status_code == 503
    assert r["Content-Type"].startswith("text/plain")
    assert b"frontend has not been built" in r.content
    assert b"Traceback" not in r.content
