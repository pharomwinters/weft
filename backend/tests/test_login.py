from datetime import UTC, datetime, timedelta

import pytest
from accounts import throttle
from audit import events
from audit.models import AuditEvent
from django.contrib.auth.hashers import get_hasher
from django.test import Client

GOOD = "correct horse battery"


def login(client, email="a@example.com", password=GOOD):
    return client.post("/auth/login", {"email": email, "password": password})


def test_login_success_starts_partial_session(api_client, make_user):
    make_user("a@example.com")
    r = login(api_client, "A@Example.com ")
    assert r.status_code == 200 and r.json() == {"next": "enrol"}
    body = api_client.get("/auth/session").json()
    assert body["state"] == "partial" and body["next"] == "enrol"
    assert body["user"]["email"] == "a@example.com"


def test_anonymous_session_reports_login_next(api_client):
    assert api_client.get("/auth/session").json() == {
        "state": "anonymous",
        "next": "login",
        "user": None,
    }


def test_wrong_password_and_unknown_email_are_indistinguishable(api_client, make_user):
    make_user("a@example.com")
    r1 = login(api_client, "a@example.com", "wrong wrong wrong")
    r2 = login(api_client, "nobody@example.com", "wrong wrong wrong")
    assert r1.status_code == r2.status_code == 401 and r1.json() == r2.json()
    assert r1.json()["error"]["code"] == "invalid_credentials"


def _count_hash_checks(monkeypatch):
    hasher = type(get_hasher())
    original = hasher.verify
    calls = []

    def counting(self, password, encoded):
        calls.append(password)
        return original(self, password, encoded)

    monkeypatch.setattr(hasher, "verify", counting)
    return calls


def test_unknown_email_still_runs_a_password_hash(api_client, make_user, monkeypatch):
    make_user("a@example.com")
    calls = _count_hash_checks(monkeypatch)
    login(api_client, "nobody@example.com", "wrong wrong wrong")
    unknown = len(calls)
    login(api_client, "a@example.com", "wrong wrong wrong")
    assert unknown == 1 and len(calls) == 2


def test_inactive_user_gets_invalid_credentials(api_client, make_user, monkeypatch):
    make_user("off@example.com", active=False)
    calls = _count_hash_checks(monkeypatch)
    r = login(api_client, "off@example.com")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"
    assert len(calls) == 1
    assert api_client.get("/auth/session").json()["state"] == "anonymous"


def test_each_failure_is_counted_once(api_client, make_user, monkeypatch):
    make_user("a@example.com")
    seen = []
    monkeypatch.setattr(throttle, "record_failure", lambda r, e: seen.append(e))
    login(api_client, "A@example.com", "wrong wrong wrong")
    login(api_client, "nobody@example.com", "wrong wrong wrong")
    assert seen == ["a@example.com", "nobody@example.com"]


def test_sixth_attempt_is_429_locked_even_with_right_password(api_client, make_user):
    make_user("a@example.com")
    for _ in range(5):
        assert login(api_client, password="wrong wrong wrong").status_code == 401
    r = login(api_client)
    assert r.status_code == 429 and r.json()["error"]["code"] == "locked"
    assert api_client.get("/auth/session").json()["state"] == "anonymous"


def test_locked_attempt_is_not_counted(api_client, make_user, monkeypatch):
    make_user("a@example.com")
    for _ in range(5):
        login(api_client, password="wrong wrong wrong")
    before = AuditEvent.objects.filter(event=events.LOGIN_FAILURE).count()
    login(api_client, password="wrong wrong wrong")
    assert AuditEvent.objects.filter(event=events.LOGIN_FAILURE).count() == before


def test_correct_password_does_not_clear_the_failure_counter(api_client, make_user):
    make_user("a@example.com")
    for _ in range(4):
        login(api_client, password="wrong wrong wrong")
    assert login(api_client).status_code == 200
    login(api_client, password="wrong wrong wrong")  # the fifth failure
    assert login(api_client).status_code == 429


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "a" * 250 + "@x.com", "password": GOOD},
        {"email": "a@example.com", "password": "x" * 1025},
    ],
)
def test_overlong_input_is_400_validation(api_client, make_user, payload):
    make_user("a@example.com")
    r = api_client.post("/auth/login", payload)
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation"
    assert not AuditEvent.objects.filter(event=events.LOGIN_FAILURE).exists()


def test_partial_session_expires_after_10_minutes(partial_client, time_machine):
    time_machine.move_to(datetime.now(UTC) + timedelta(minutes=10, seconds=1))
    body = partial_client.get("/auth/session").json()
    assert body["state"] == "anonymous" and body["next"] == "login"


def test_partial_session_of_deactivated_user_reports_anonymous(partial_client):
    from accounts.models import User

    User.objects.update(is_active=False)
    assert partial_client.get("/auth/session").json()["state"] == "anonymous"


def test_logout_flushes_session(partial_client):
    assert partial_client.post("/auth/logout").status_code == 204
    assert partial_client.get("/auth/session").json()["state"] == "anonymous"
    assert partial_client.post("/auth/logout").status_code == 401


def test_logout_when_anonymous_is_401(api_client):
    r = api_client.post("/auth/logout")
    assert r.status_code == 401
    assert r.json()["error"]["details"] == {"session": "anonymous", "next": "login"}


def _csrf_client():
    return Client(enforce_csrf_checks=True)


def _post(client, token=None):
    headers = {"HTTP_X_CSRFTOKEN": token} if token else {}
    return client.post(
        "/api/v1/auth/login",
        data='{"email": "a@example.com", "password": "correct horse battery"}',
        content_type="application/json",
        **headers,
    )


def test_post_without_csrf_token_is_403(make_user):
    make_user("a@example.com")
    r = _post(_csrf_client())
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"
    assert set(r.json()["error"]) == {"code", "message", "details"}


def test_post_with_csrf_token_succeeds(make_user):
    make_user("a@example.com")
    client = _csrf_client()
    client.get("/api/v1/auth/session")
    token = client.cookies["csrftoken"].value
    assert _post(client, token).status_code == 200


def test_login_success_and_failure_are_audited(api_client, make_user):
    user = make_user("a@example.com")
    login(api_client, password="wrong wrong wrong")
    login(api_client)
    api_client.post("/auth/logout")
    failure = AuditEvent.objects.get(event=events.LOGIN_FAILURE)
    assert failure.details == {"email": "a@example.com"}
    success = AuditEvent.objects.get(event=events.LOGIN_SUCCESS)
    assert success.actor == user and success.target_id == str(user.pk)
    assert AuditEvent.objects.get(event=events.LOGOUT).actor == user
    assert "correct horse" not in str([e.details for e in AuditEvent.objects.all()])
