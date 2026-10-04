from datetime import UTC, datetime, timedelta

import pytest
from accounts import recovery
from accounts.models import TotpDevice, User, UserSession
from audit import events
from audit.models import AuditEvent

from .conftest import PASSWORD, ApiClient

NEW_PASSWORD = "a brand new passphrase"
NOW = datetime(2026, 10, 3, 12, 0, 10, tzinfo=UTC)


def login(client, email="u@example.com", password=PASSWORD):
    return client.post("/auth/login", {"email": email, "password": password})


def state(client) -> str:
    return client.get("/auth/session").json()["state"]


@pytest.fixture
def must_change_user(make_user, enrolled) -> User:
    return enrolled(make_user(must_change=True))


@pytest.fixture
def after_second_factor(api_client, must_change_user, code_for) -> ApiClient:
    """Password and code accepted; only the forced change is left."""
    assert login(api_client).json() == {"next": "verify"}
    r = api_client.post("/auth/verify", {"code": code_for(must_change_user)})
    assert r.json() == {"next": "change_password"}
    return api_client


def test_forced_change_comes_after_second_factor(after_second_factor, must_change_user):
    client = after_second_factor
    assert state(client) == "partial"
    assert client.get("/account").status_code == 401

    r = client.post("/auth/password/forced", {"new_password": NEW_PASSWORD})
    assert r.status_code == 200 and r.json() == {"next": None}
    assert state(client) == "verified"
    must_change_user.refresh_from_db()
    assert must_change_user.must_change_password is False
    assert must_change_user.check_password(NEW_PASSWORD)
    assert UserSession.objects.filter(user=must_change_user).count() == 1
    changed = AuditEvent.objects.filter(event=events.PASSWORD_CHANGED)
    assert changed.count() == 1 and changed.get().details == {}


def test_forced_change_refused_before_second_factor(api_client, must_change_user):
    login(api_client)
    r = api_client.post("/auth/password/forced", {"new_password": NEW_PASSWORD})
    assert r.status_code == 401
    assert r.json()["error"]["details"] == {"session": "partial", "next": "verify"}
    must_change_user.refresh_from_db()
    assert must_change_user.check_password(PASSWORD)


def test_forced_change_applies_password_rules(after_second_factor):
    for bad in ("short", PASSWORD, "x" * 2000):
        r = after_second_factor.post("/auth/password/forced", {"new_password": bad})
        assert r.status_code == 400 and r.json()["error"]["code"] == "validation"
        assert r.json()["error"]["details"][
            "new_password" if len(bad) > 1024 else "password"
        ]
    assert state(after_second_factor) == "partial"


@pytest.mark.parametrize("client_fixture", ["partial_client", "verified_client"])
def test_forced_change_is_409_when_not_required(request, client_fixture):
    client = request.getfixturevalue(client_fixture)
    r = client.post("/auth/password/forced", {"new_password": NEW_PASSWORD})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_required"


def test_account_returns_the_profile(verified_client, user):
    assert verified_client.get("/account").json() == {
        "id": user.pk,
        "email": "u@example.com",
        "is_instance_admin": False,
    }


def test_change_password_requires_current(verified_client, user):
    r = verified_client.post(
        "/account/password",
        {"current_password": "not the password", "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_change_password_keeps_this_session_and_audits(verified_client, user):
    r = verified_client.post(
        "/account/password",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 204
    assert state(verified_client) == "verified"
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    sessions = verified_client.get("/account/sessions").json()
    assert [s["current"] for s in sessions] == [True]
    assert AuditEvent.objects.filter(event=events.PASSWORD_CHANGED, actor=user).exists()


def test_change_password_ends_other_sessions(user, make_verified_client):
    mine = make_verified_client(user)
    other = make_verified_client(user, offset=1)
    r = mine.post(
        "/account/password",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 204
    assert state(mine) == "verified" and state(other) == "anonymous"
    assert UserSession.objects.filter(user=user).count() == 1


def test_new_password_same_as_old_rejected(verified_client):
    r = verified_client.post(
        "/account/password",
        {"current_password": PASSWORD, "new_password": PASSWORD},
    )
    assert r.status_code == 400 and "password" in r.json()["error"]["details"]


def test_wrong_current_passwords_lock_the_account(verified_client):
    body = {"current_password": "not the password", "new_password": NEW_PASSWORD}
    for _ in range(5):
        assert verified_client.post("/account/password", body).status_code == 401
    r = verified_client.post(
        "/account/password",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 429


def test_sessions_list_marks_current(user, make_verified_client):
    mine = make_verified_client(user)
    make_verified_client(user, offset=1)
    rows = mine.get("/account/sessions").json()
    assert len(rows) == 2 and sorted(r["current"] for r in rows) == [False, True]
    assert set(rows[0]) == {"id", "ip", "user_agent", "created", "last_seen", "current"}
    assert "session_key" not in str(rows)


def test_revoke_other_session(user, make_verified_client):
    mine = make_verified_client(user)
    other = make_verified_client(user, offset=1)
    target = next(r for r in mine.get("/account/sessions").json() if not r["current"])
    assert mine.delete(f"/account/sessions/{target['id']}").status_code == 204
    assert state(other) == "anonymous" and state(mine) == "verified"
    assert len(mine.get("/account/sessions").json()) == 1


def test_cannot_revoke_another_users_session(
    verified_client, make_user, enrolled, make_verified_client
):
    stranger = enrolled(make_user("other@example.com"))
    theirs = make_verified_client(stranger)
    row = UserSession.objects.get(user=stranger)
    r = verified_client.delete(f"/account/sessions/{row.pk}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert state(theirs) == "verified"


def test_reenrol_requires_current_code(verified_client, user):
    r = verified_client.post("/account/2fa/reenrol/start", {"code": "000000"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_code"
    assert TotpDevice.objects.filter(user=user).count() == 1


def test_reenrol_replaces_device_and_recovery_codes(
    verified_client, user, code_for, make_verified_client
):
    old_recovery = recovery.generate(user)
    r = verified_client.post("/account/2fa/reenrol/start", {"code": code_for(user, 1)})
    assert r.status_code == 200 and set(r.json()) == {"secret", "otpauth_uri"}
    r = verified_client.post(
        "/account/2fa/reenrol/confirm", {"code": code_for(user, confirmed=False)}
    )
    assert r.status_code == 200 and len(r.json()["recovery_codes"]) == 10
    assert TotpDevice.objects.get(user=user).confirmed is True

    fresh = ApiClient()
    login(fresh)
    assert fresh.post("/auth/recovery", {"code": old_recovery[0]}).status_code == 401
    r = fresh.post("/auth/recovery", {"code": r.json()["recovery_codes"][0]})
    assert r.status_code == 200
    assert make_verified_client(user, offset=1) is not None  # the new device works


def test_reenrol_accepts_a_recovery_code(verified_client, user):
    code = recovery.generate(user)[0]
    r = verified_client.post("/account/2fa/reenrol/start", {"code": code})
    assert r.status_code == 200
    assert AuditEvent.objects.filter(event=events.RECOVERY_CODE_USED).count() == 1


def test_old_device_keeps_working_until_reenrol_confirmed(
    verified_client, user, code_for, make_verified_client, time_machine
):
    r = verified_client.post("/account/2fa/reenrol/start", {"code": code_for(user, 1)})
    assert r.status_code == 200
    bad = verified_client.post("/account/2fa/reenrol/confirm", {"code": "000000"})
    assert bad.status_code == 401
    assert TotpDevice.objects.filter(user=user, confirmed=True).count() == 1
    assert TotpDevice.objects.filter(user=user, confirmed=False).count() == 1
    # Past the time steps this test has already used up on the old device.
    time_machine.move_to(datetime.now(UTC) + timedelta(minutes=5))
    assert state(make_verified_client(user)) == "verified"


def test_reenrol_failures_count_toward_lockout(verified_client, user, code_for):
    for _ in range(5):
        verified_client.post("/account/2fa/reenrol/start", {"code": "000000"})
    r = verified_client.post("/account/2fa/reenrol/start", {"code": code_for(user, 1)})
    assert r.status_code == 429 and r.json()["error"]["code"] == "locked"


def test_last_seen_updates_at_most_once_a_minute(
    user, make_verified_client, time_machine
):
    time_machine.move_to(NOW, tick=False)
    client = make_verified_client(user)
    row = UserSession.objects.get(user=user)
    assert row.last_seen == NOW

    time_machine.move_to(NOW + timedelta(seconds=59), tick=False)
    client.get("/account")
    row.refresh_from_db()
    assert row.last_seen == NOW

    later = NOW + timedelta(seconds=61)
    time_machine.move_to(later, tick=False)
    client.get("/account")
    row.refresh_from_db()
    assert row.last_seen == later and row.created == NOW
