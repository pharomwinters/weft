import pytest
from accounts import services
from accounts.models import User, UserSession
from api.errors import ApiError
from audit import events
from audit.models import AuditEvent

from .conftest import PASSWORD, ApiClient


@pytest.fixture
def admin(signed_in):
    return signed_in("admin@example.com", admin=True)


@pytest.fixture
def member(signed_in):
    return signed_in("member@example.com")


def _state(client) -> str:
    return client.get("/auth/session").json()["state"]


def test_non_admin_gets_403_on_every_admin_route(admin, member):
    target = admin[0].pk
    client = member[1]
    for r in (
        client.get("/admin/users"),
        client.post(f"/admin/users/{target}/deactivate"),
        client.post(f"/admin/users/{target}/reactivate"),
        client.put(f"/admin/users/{target}/admin", {"is_instance_admin": False}),
        client.post(f"/admin/users/{target}/reset-link"),
        client.post(f"/admin/users/{target}/reset-2fa"),
        client.post("/admin/users/999999/deactivate"),
        client.get("/admin/audit"),
    ):
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    admin[0].refresh_from_db()
    assert admin[0].is_active and admin[0].is_instance_admin


def test_list_users(admin, member, make_user):
    make_user("pending@example.com", active=False)
    rows = admin[1].get("/admin/users").json()
    assert [
        (r["email"], r["is_instance_admin"], r["is_active"], r["has_2fa"]) for r in rows
    ] == [
        ("admin@example.com", True, True, True),
        ("member@example.com", False, True, True),
        ("pending@example.com", False, False, False),
    ]
    assert set(rows[0]) == {
        "id",
        "email",
        "is_instance_admin",
        "is_active",
        "has_2fa",
        "created_at",
    }


def test_unknown_user_is_404(admin):
    r = admin[1].post("/admin/users/999999/deactivate")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_deactivate_ends_sessions_and_blocks_login(admin, member):
    user, client = member
    assert admin[1].post(f"/admin/users/{user.pk}/deactivate").status_code == 204
    assert _state(client) == "anonymous"
    assert not UserSession.objects.filter(user=user).exists()
    r = ApiClient().post("/auth/login", {"email": user.email, "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    done = AuditEvent.objects.get(event=events.USER_DEACTIVATED)
    assert done.actor == admin[0] and done.target_id == str(user.pk)


def test_cannot_deactivate_or_demote_last_active_admin(admin, member):
    user, client = admin
    for r in (
        client.post(f"/admin/users/{user.pk}/deactivate"),
        client.put(f"/admin/users/{user.pk}/admin", {"is_instance_admin": False}),
    ):
        assert r.status_code == 409 and r.json()["error"]["code"] == "last_admin"
    user.refresh_from_db()
    assert user.is_active and user.is_instance_admin
    assert _state(client) == "verified"


def test_inactive_admin_does_not_count_toward_last_admin(admin, make_user):
    gone = make_user("gone@example.com", admin=True, active=False)
    user, client = admin
    r = client.post(f"/admin/users/{user.pk}/deactivate")
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_admin"
    # The inactive one can be demoted: it never counted.
    r = client.put(f"/admin/users/{gone.pk}/admin", {"is_instance_admin": False})
    assert r.status_code == 204


def test_an_admin_can_step_down_when_another_is_active(admin, signed_in):
    other, _ = signed_in("other@example.com", admin=True)
    user, client = admin
    r = client.put(f"/admin/users/{user.pk}/admin", {"is_instance_admin": False})
    assert r.status_code == 204
    assert client.get("/admin/users").status_code == 403
    with pytest.raises(ApiError) as raised:
        services.deactivate(other)
    assert raised.value.code == "last_admin"


def test_reactivate(admin, member):
    user, _ = member
    admin[1].post(f"/admin/users/{user.pk}/deactivate")
    assert admin[1].post(f"/admin/users/{user.pk}/reactivate").status_code == 204
    user.refresh_from_db()
    assert user.is_active
    r = ApiClient().post("/auth/login", {"email": user.email, "password": PASSWORD})
    assert r.status_code == 200
    assert AuditEvent.objects.filter(event=events.USER_REACTIVATED).count() == 1


def test_admin_flag_change_is_audited(admin, member):
    user, client = member
    path = f"/admin/users/{user.pk}/admin"
    assert admin[1].put(path, {"is_instance_admin": True}).status_code == 204
    assert client.get("/admin/users").status_code == 200
    assert admin[1].put(path, {"is_instance_admin": True}).status_code == 204  # no-op
    assert admin[1].put(path, {"is_instance_admin": False}).status_code == 204
    rows = AuditEvent.objects.filter(event=events.ADMIN_FLAG_CHANGED).order_by("pk")
    assert [r.details for r in rows] == [
        {"is_instance_admin": True},
        {"is_instance_admin": False},
    ]
    assert all(r.actor == admin[0] and r.target_id == str(user.pk) for r in rows)
    assert User.objects.get(pk=user.pk).is_instance_admin is False
