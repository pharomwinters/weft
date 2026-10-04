import io
from datetime import UTC, datetime, timedelta

import pytest
from accounts import recovery, services
from accounts.models import ResetLink, TotpDevice, UserSession
from audit import events
from audit.models import AuditEvent
from django.core.management import call_command
from django.core.management.base import CommandError

from .conftest import PASSWORD, ApiClient

NEW_PASSWORD = "a freshly reset passphrase"
PREFIX = "http://localhost:8000/reset/"


@pytest.fixture
def admin(signed_in):
    return signed_in("admin@example.com", admin=True)


@pytest.fixture
def member(signed_in):
    return signed_in("member@example.com")


def _link(admin, user) -> str:
    r = admin[1].post(f"/admin/users/{user.pk}/reset-link")
    assert r.status_code == 201 and set(r.json()) == {"url", "expires_at"}
    assert r.json()["url"].startswith(PREFIX)
    return r.json()["url"].removeprefix(PREFIX)


def _redeem(token, password=NEW_PASSWORD):
    return ApiClient().post(f"/auth/reset/{token}", {"new_password": password})


def _login(email, password):
    client = ApiClient()
    return client, client.post("/auth/login", {"email": email, "password": password})


def test_reset_link_sets_password_but_second_factor_still_required(admin, member):
    user, _ = member
    token = _link(admin, user)
    assert ApiClient().get(f"/auth/reset/{token}").status_code == 204
    assert _redeem(token).status_code == 204

    assert _login(user.email, PASSWORD)[1].status_code == 401
    client, r = _login(user.email, NEW_PASSWORD)
    assert r.status_code == 200 and r.json() == {"next": "verify"}
    assert client.get("/workspaces").status_code == 401
    kinds = set(AuditEvent.objects.values_list("event", flat=True))
    assert {events.RESET_LINK_CREATED, events.RESET_LINK_USED} <= kinds
    assert events.PASSWORD_CHANGED in kinds


def test_reset_applies_password_rules(admin, member):
    token = _link(admin, member[0])
    r = _redeem(token, "short")
    assert r.status_code == 400 and "password" in r.json()["error"]["details"]
    assert _redeem(token).status_code == 204  # the refusal left the link usable


def test_reset_link_single_use_and_expires_after_24_hours(admin, member, time_machine):
    user, _ = member
    token = _link(admin, user)
    assert _redeem(token).status_code == 204
    assert _redeem(token, "another passphrase here").status_code == 404
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)

    token = _link(admin, user)
    start = datetime.now(UTC)
    time_machine.move_to(start + timedelta(hours=23, minutes=59))
    assert ApiClient().get(f"/auth/reset/{token}").status_code == 204
    time_machine.move_to(start + timedelta(hours=24, minutes=1))
    assert ApiClient().get(f"/auth/reset/{token}").status_code == 404
    assert _redeem(token, "another passphrase here").status_code == 404


def test_reset_ends_all_sessions_and_clears_must_change_and_lockout(admin, member):
    user, client = member
    user.must_change_password = True
    user.save()
    for _ in range(5):
        _login(user.email, "wrong wrong wrong")
    assert _login(user.email, PASSWORD)[1].status_code == 429

    assert _redeem(_link(admin, user)).status_code == 204
    assert client.get("/auth/session").json()["state"] == "anonymous"
    assert not UserSession.objects.filter(user=user).exists()
    user.refresh_from_db()
    assert user.must_change_password is False
    assert _login(user.email, NEW_PASSWORD)[1].status_code == 200


def test_dead_reset_tokens_indistinguishable(admin, member, signed_in):
    user, _ = member
    used = _link(admin, user)
    _redeem(used)
    expired = _link(admin, user)
    ResetLink.objects.filter(used_at__isnull=True).update(
        expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )
    other, _ = signed_in("other@example.com")
    deactivated = _link(admin, other)
    services.deactivate(other)

    answers = set()
    for token in (used, expired, deactivated, "no-such-token"):
        inspect = ApiClient().get(f"/auth/reset/{token}")
        redeem = _redeem(token, "another passphrase here")
        assert inspect.status_code == redeem.status_code == 404
        assert inspect.json()["error"]["code"] == "invalid_token"
        answers.add((inspect.content, redeem.content))
    assert len(answers) == 1


def test_bad_reset_tokens_count_toward_ip_block(admin, member):
    token = _link(admin, member[0])
    for i in range(20):
        assert _redeem(f"wrong-{i}").status_code == 404
    assert _redeem(token).status_code == 429


def test_creating_a_second_link_invalidates_the_first(admin, member):
    user, _ = member
    first = _link(admin, user)
    second = _link(admin, user)
    assert _redeem(first).status_code == 404
    assert _redeem(second).status_code == 204


def test_reset_token_is_stored_hashed_and_not_audited(admin, member):
    token = _link(admin, member[0])
    haystack = str(list(ResetLink.objects.values())) + str(
        list(AuditEvent.objects.values())
    )
    assert token not in haystack


def test_reset_2fa_forces_reenrolment_and_ends_sessions(admin, member):
    user, client = member
    codes = recovery.generate(user)
    assert admin[1].post(f"/admin/users/{user.pk}/reset-2fa").status_code == 204
    assert client.get("/auth/session").json()["state"] == "anonymous"
    assert not TotpDevice.objects.filter(user=user).exists()

    fresh, r = _login(user.email, PASSWORD)
    assert r.json() == {"next": "enrol"}
    r = fresh.post("/auth/recovery", {"code": codes[0]})
    assert r.status_code == 401 and r.json()["error"]["details"]["next"] == "enrol"
    done = AuditEvent.objects.get(event=events.TWOFA_RESET)
    assert done.actor == admin[0] and done.target_id == str(user.pk)


def test_reset_2fa_command(member):
    user, client = member
    out = io.StringIO()
    call_command("reset_2fa", " Member@Example.com ", stdout=out)
    assert "member@example.com" in out.getvalue()
    assert not TotpDevice.objects.filter(user=user).exists()
    assert client.get("/auth/session").json()["state"] == "anonymous"
    assert AuditEvent.objects.get(event=events.TWOFA_RESET).actor is None


def test_reset_password_command_prints_working_url(member):
    user, _ = member
    out = io.StringIO()
    call_command("reset_password", "member@example.com", stdout=out)
    url = out.getvalue().strip()
    assert url.startswith(PREFIX) and "\n" not in url
    assert ResetLink.objects.get().created_by is None
    assert _redeem(url.removeprefix(PREFIX)).status_code == 204
    assert _login(user.email, NEW_PASSWORD)[1].json() == {"next": "verify"}


@pytest.mark.parametrize("command", ["reset_2fa", "reset_password"])
def test_commands_fail_for_unknown_email(db, command):
    with pytest.raises(CommandError, match="nobody@example"):
        call_command(command, "nobody@example.com")


def _half_logged_in(email) -> ApiClient:
    client, r = _login(email, PASSWORD)
    assert r.status_code == 200
    return client


def test_2fa_reset_kills_a_half_finished_login(admin, member):
    """A stolen password must not be able to enrol a device after a recovery."""
    user, _ = member
    stale = _half_logged_in(user.email)
    assert admin[1].post(f"/admin/users/{user.pk}/reset-2fa").status_code == 204
    assert stale.get("/auth/session").json()["state"] == "anonymous"
    r = stale.post("/auth/enrol/start")
    assert r.status_code == 401 and r.json()["error"]["details"]["next"] == "login"
    assert not TotpDevice.objects.filter(user=user).exists()


def test_password_reset_kills_a_half_finished_login(admin, member, code_for):
    user, _ = member
    stale = _half_logged_in(user.email)
    assert _redeem(_link(admin, user)).status_code == 204
    r = stale.post("/auth/verify", {"code": code_for(user, 1)})
    assert r.status_code == 401 and r.json()["error"]["code"] == "auth_required"


def test_password_change_kills_a_half_finished_login(member, code_for):
    user, client = member
    stale = _half_logged_in(user.email)
    r = client.post(
        "/account/password",
        {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 204
    assert client.get("/auth/session").json()["state"] == "verified"
    assert stale.get("/auth/session").json()["state"] == "anonymous"
