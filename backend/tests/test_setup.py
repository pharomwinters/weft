import io
import re
import threading

import pytest
from accounts import setup
from accounts.models import SetupToken, User
from accounts.setup import bootstrap
from audit import events
from audit.models import AuditEvent
from config.env import Config, ConfigError
from django.core.management import call_command
from django.db import connection

from .conftest import ApiClient

ADMIN = {"email": "Root@Example.com ", "password": "a long setup passphrase"}


@pytest.fixture
def cfg():
    def _cfg(email: str | None = None, password: str | None = None) -> Config:
        return Config(
            database_url="postgres://unused",
            secret_key="k" * 50,
            totp_encryption_key="unused",
            public_url="http://localhost:8000",
            trusted_proxy_count=0,
            initial_admin_email=email,
            initial_admin_password=password,
        )

    return _cfg


@pytest.fixture
def out():
    return io.StringIO()


def _token(out: io.StringIO) -> str:
    match = re.search(r"^Setup token: (\S+)$", out.getvalue(), re.M)
    assert match is not None
    return match[1]


@pytest.fixture
def token(db, cfg, out) -> str:
    assert bootstrap(cfg(), out) == "token"
    return _token(out)


def test_env_route_creates_admin_who_must_change_password(db, cfg, out):
    config = cfg(email="Root@Example.com", password="initial-password-1")
    assert bootstrap(config, out) == "env_admin"
    u = User.objects.get()
    assert u.is_instance_admin and u.must_change_password
    assert u.email == "root@example.com" and u.check_password("initial-password-1")
    assert "Setup token" not in out.getvalue()
    assert "initial-password-1" not in out.getvalue()
    assert not SetupToken.objects.exists()
    done = AuditEvent.objects.get(event=events.SETUP_COMPLETED)
    assert done.target_id == str(u.pk) and done.details == {"route": "env"}


def test_env_route_needs_both_values(db, cfg, out):
    assert bootstrap(cfg(email="root@example.com", password=None), out) == "token"
    assert bootstrap(cfg(email=None, password="initial-password-1"), out) == "token"
    assert not User.objects.exists()


def test_env_values_ignored_once_an_admin_exists(db, cfg, out, make_user):
    make_user("first@example.com", admin=True)
    config = cfg(email="root@example.com", password="initial-password-1")
    assert bootstrap(config, out) == "exists"
    assert User.objects.count() == 1 and out.getvalue() == ""


def test_env_admin_not_recreated_after_password_change(db, cfg, out):
    config = cfg(email="root@example.com", password="initial-password-1")
    bootstrap(config, out)
    u = User.objects.get()
    u.set_password("a changed passphrase")
    u.must_change_password = False
    u.save()

    assert bootstrap(config, out) == "exists"
    u = User.objects.get()
    assert u.check_password("a changed passphrase") and not u.must_change_password


@pytest.mark.parametrize(
    "email,password,variable",
    [
        ("root@example.com", "Sh0rt!", "INITIAL_ADMIN_PASSWORD"),
        ("root@example.com", "password123456", "INITIAL_ADMIN_PASSWORD"),
        ("not-an-email", "initial-password-1", "INITIAL_ADMIN_EMAIL"),
    ],
)
def test_weak_env_password_is_a_config_error(db, cfg, out, email, password, variable):
    with pytest.raises(ConfigError, match=variable) as raised:
        bootstrap(cfg(email=email, password=password), out)
    assert password not in str(raised.value)
    assert not User.objects.exists()


def test_token_route_prints_token_and_stores_only_hash(db, cfg, out):
    assert bootstrap(cfg(), out) == "token"
    token = _token(out)
    assert out.getvalue() == f"Setup token: {token}\n"
    assert len(token) >= 43
    assert token not in str(SetupToken.objects.values())
    assert SetupToken.objects.count() == 1


def test_restart_replaces_the_token(db, cfg, out, token, api_client):
    assert bootstrap(cfg(), out) == "token"
    new = out.getvalue().splitlines()[-1].removeprefix("Setup token: ")
    assert new != token and SetupToken.objects.count() == 1

    r = api_client.post("/setup/admin", {"token": token, **ADMIN})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"
    assert not User.objects.exists()
    assert api_client.post("/setup/admin", {"token": new, **ADMIN}).status_code == 201


def test_status_reports_needs_setup(db, api_client):
    r = api_client.get("/setup/status")
    assert r.status_code == 200 and r.json() == {"needs_setup": True}


def test_setup_creates_admin_and_leads_to_enrolment(token, api_client):
    r = api_client.post("/setup/admin", {"token": token, **ADMIN})
    assert r.status_code == 201 and r.json() == {"next": "enrol"}
    u = User.objects.get()
    assert u.email == "root@example.com" and u.is_instance_admin
    assert not u.must_change_password
    session = api_client.get("/auth/session").json()
    assert session["state"] == "partial" and session["next"] == "enrol"
    assert not SetupToken.objects.exists()
    done = AuditEvent.objects.get(event=events.SETUP_COMPLETED)
    assert done.actor == u and done.details == {"route": "token"}
    assert token not in str(list(AuditEvent.objects.values()))


def test_setup_applies_email_and_password_rules(token, api_client):
    r = api_client.post(
        "/setup/admin", {"token": token, "email": "root@example.com", "password": "x"}
    )
    assert r.status_code == 400 and "password" in r.json()["error"]["details"]
    r = api_client.post(
        "/setup/admin", {"token": token, "email": "nope", "password": ADMIN["password"]}
    )
    assert r.status_code == 400 and "email" in r.json()["error"]["details"]
    # A refused attempt with the right token does not use the token up.
    assert not User.objects.exists() and SetupToken.objects.count() == 1


def test_setup_endpoints_are_404_once_admin_exists(token, api_client):
    assert api_client.post("/setup/admin", {"token": token, **ADMIN}).status_code == 201
    other = ApiClient()
    for r in (
        other.get("/setup/status"),
        other.post("/setup/admin", {"token": token, **ADMIN}),
        other.post("/setup/admin", {"token": "wrong", **ADMIN}),
    ):
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert User.objects.count() == 1


def test_inactive_admin_still_closes_setup(token, api_client, make_user):
    make_user("gone@example.com", admin=True, active=False)
    assert setup.admin_exists()
    assert api_client.get("/setup/status").status_code == 404
    r = api_client.post("/setup/admin", {"token": token, **ADMIN})
    assert r.status_code == 404 and User.objects.count() == 1


def test_wrong_tokens_count_toward_ip_block(token, api_client):
    for _ in range(20):
        r = api_client.post("/setup/admin", {"token": "wrong", **ADMIN})
        assert r.status_code == 401
    r = api_client.post("/setup/admin", {"token": token, **ADMIN})
    assert r.status_code == 429 and r.json()["error"]["code"] == "locked"
    assert not User.objects.exists()


def test_two_simultaneous_setups_create_one_admin(transactional_db, cfg, out):
    bootstrap(cfg(), out)
    token = _token(out)
    barrier = threading.Barrier(2)
    statuses = []

    def attempt(email: str) -> None:
        try:
            barrier.wait(timeout=5)
            body = {"token": token, "email": email, "password": ADMIN["password"]}
            statuses.append(ApiClient().post("/setup/admin", body).status_code)
        finally:
            connection.close()

    threads = [
        threading.Thread(target=attempt, args=(f"admin{i}@example.com",))
        for i in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(statuses) == [201, 404]
    assert User.objects.filter(is_instance_admin=True).count() == 1


def test_bootstrap_command_prints_exactly_the_token_line(db, capsys):
    call_command("bootstrap")
    printed = capsys.readouterr().out
    assert re.fullmatch(r"Setup token: \S+\n", printed)
    assert SetupToken.objects.count() == 1
