import io
import json
import re

import pytest
from accounts import recovery
from accounts.models import User
from accounts.setup import bootstrap
from audit import events
from audit.models import AuditEvent
from audit.service import record
from config.env import load_config
from django.conf import settings

from .conftest import ApiClient


@pytest.fixture
def admin(signed_in):
    return signed_in("admin@example.com", admin=True)


def test_filter_by_event_and_actor(admin, make_user):
    user, client = admin
    other = make_user("other@example.com")
    record(events.LOGOUT, actor=other, target=other)
    record(events.WORKSPACE_CREATED, actor=other)

    body = client.get("/admin/audit?event=logout").json()
    assert [i["event"] for i in body["items"]] == ["logout"]
    assert body["items"][0]["actor_email"] == "other@example.com"
    assert set(body["items"][0]) == {
        "id",
        "time",
        "event",
        "actor_email",
        "target_type",
        "target_id",
        "ip",
        "details",
    }
    by_actor = client.get(f"/admin/audit?actor_id={other.pk}").json()["items"]
    assert [i["event"] for i in by_actor] == ["workspace_created", "logout"]
    both = client.get(f"/admin/audit?actor_id={user.pk}&event=logout").json()
    assert both == {"items": [], "next_before": None}


def test_pagination_newest_first(admin):
    _, client = admin
    for n in range(5):
        record(events.LOGOUT, details={"n": n})
    first = client.get("/admin/audit?event=logout&limit=2").json()
    assert [i["details"]["n"] for i in first["items"]] == [4, 3]
    assert first["next_before"] == first["items"][-1]["id"]
    second = client.get(
        f"/admin/audit?event=logout&limit=2&before={first['next_before']}"
    ).json()
    assert [i["details"]["n"] for i in second["items"]] == [2, 1]
    last = client.get(
        f"/admin/audit?event=logout&limit=2&before={second['next_before']}"
    ).json()
    assert [i["details"]["n"] for i in last["items"]] == [0]
    assert last["next_before"] is None


def test_limit_capped_at_200(admin):
    _, client = admin
    AuditEvent.objects.bulk_create(AuditEvent(event=events.LOGOUT) for _ in range(205))
    body = client.get("/admin/audit?event=logout&limit=5000").json()
    assert len(body["items"]) == 200 and body["next_before"] is not None
    assert len(client.get("/admin/audit?event=logout").json()["items"]) == 50
    assert len(client.get("/admin/audit?event=logout&limit=0").json()["items"]) == 1
    assert client.get("/admin/audit?limit=abc").status_code == 400


def test_no_secret_material_in_any_audit_row_after_full_flow(db, code_for):
    secrets_seen: list[str] = []

    # Setup by token.
    out = io.StringIO()
    bootstrap(load_config({**_env(), "INITIAL_ADMIN_EMAIL": ""}), out)
    found = re.search(r"Setup token: (\S+)", out.getvalue())
    assert found is not None
    setup_token = found[1]
    admin_password = "the admin's passphrase"
    admin = ApiClient()
    r = admin.post(
        "/setup/admin",
        {"token": setup_token, "email": "root@example.com", "password": admin_password},
    )
    assert r.status_code == 201
    secrets_seen += [setup_token, admin_password]

    # Enrol.
    root = User.objects.get(email="root@example.com")
    secrets_seen.append(admin.post("/auth/enrol/start").json()["secret"])
    code = code_for(root, confirmed=False)
    r = admin.post("/auth/enrol/confirm", {"code": code})
    assert r.status_code == 200
    secrets_seen += [code, *r.json()["recovery_codes"]]

    # Invite and accept.
    url = admin.post("/invitations", {}).json()["url"]
    invite_token = url.rsplit("/", 1)[1]
    invited_password = "the invitee's passphrase"
    r = ApiClient().post(
        f"/invitations/token/{invite_token}/accept",
        {"email": "new@example.com", "password": invited_password},
    )
    assert r.status_code == 201
    secrets_seen += [invite_token, invited_password]

    # A failed login, a recovery-code login, then a reset.
    ApiClient().post(
        "/auth/login", {"email": "root@example.com", "password": "a wrong passphrase"}
    )
    secrets_seen.append("a wrong passphrase")
    spare = recovery.generate(root)
    second = ApiClient()
    second.post(
        "/auth/login", {"email": "root@example.com", "password": admin_password}
    )
    assert second.post("/auth/recovery", {"code": spare[0]}).status_code == 200
    secrets_seen += spare

    invited = User.objects.get(email="new@example.com")
    url = admin.post(f"/admin/users/{invited.pk}/reset-link").json()["url"]
    reset_token = url.rsplit("/", 1)[1]
    reset_password = "the reset passphrase"
    r = ApiClient().post(f"/auth/reset/{reset_token}", {"new_password": reset_password})
    assert r.status_code == 204
    secrets_seen += [reset_token, reset_password]

    rows = list(AuditEvent.objects.all())
    recorded = {row.event for row in rows}
    assert {
        events.SETUP_COMPLETED,
        events.TOTP_ENROLLED,
        events.INVITATION_CREATED,
        events.INVITATION_ACCEPTED,
        events.LOGIN_FAILURE,
        events.RECOVERY_CODE_USED,
        events.RESET_LINK_CREATED,
        events.RESET_LINK_USED,
    } <= recorded
    dumped = json.dumps([[r.details, r.target_id, r.target_type] for r in rows])
    for secret in secrets_seen:
        assert secret and secret not in dumped
    viewed = admin.get("/admin/audit?limit=200").content.decode()
    for secret in secrets_seen:
        assert secret not in viewed


def _env() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgres://u:p@h/db",
        "SECRET_KEY": settings.SECRET_KEY,
        "TOTP_ENCRYPTION_KEY": settings.TOTP_ENCRYPTION_KEY,
        "PUBLIC_URL": settings.PUBLIC_URL,
    }
