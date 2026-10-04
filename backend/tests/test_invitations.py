import threading
from datetime import UTC, datetime, timedelta

import pytest
from accounts import invitations
from accounts.models import Invitation, User
from audit import events
from audit.models import AuditEvent
from django.db import connection
from django.utils import timezone
from workspaces import services
from workspaces.models import Membership, Role, Workspace

from .conftest import ApiClient

PASSWORD = "an invited passphrase"
PREFIX = "http://localhost:8000/invite/"


@pytest.fixture
def admin(signed_in):
    return signed_in("admin@example.com", admin=True)


@pytest.fixture
def owner(signed_in):
    return signed_in("owner@example.com")


@pytest.fixture
def team(owner) -> Workspace:
    return services.create(owner[0], "Team")


def _token(response) -> str:
    assert response.status_code == 201, response.content
    url = response.json()["url"]
    assert url.startswith(PREFIX)
    return url.removeprefix(PREFIX)


def _accept(token, email="new@example.com", password=PASSWORD, client=None):
    client = client or ApiClient()
    body = {"email": email, "password": password}
    return client.post(f"/invitations/token/{token}/accept", body)


def test_admin_creates_instance_invitation(admin):
    user, client = admin
    r = client.post("/invitations", {})
    assert set(r.json()) == {"id", "url", "expires_at"}
    token = _token(r)
    assert len(token) >= 43
    invitation = Invitation.objects.get()
    assert invitation.created_by == user and invitation.workspace is None
    info = ApiClient().get(f"/invitations/token/{token}")
    assert info.status_code == 200
    assert info.json() == {"workspace_name": None, "role": None}
    created = AuditEvent.objects.get(event=events.INVITATION_CREATED)
    assert created.actor == user and created.target_id == str(invitation.pk)


def test_owner_creates_workspace_invitation(owner, team):
    r = owner[1].post("/invitations", {"workspace_id": team.pk, "role": "viewer"})
    info = ApiClient().get(f"/invitations/token/{_token(r)}")
    assert info.json() == {"workspace_name": "Team", "role": "viewer"}
    r = owner[1].post("/invitations", {"workspace_id": team.pk})
    assert r.status_code == 400 and "role" in r.json()["error"]["details"]
    r = owner[1].post("/invitations", {"workspace_id": team.pk, "role": "boss"})
    assert r.status_code == 400


def test_editor_cannot_invite(owner, team, signed_in):
    editor, client = signed_in("editor@example.com")
    services.add_member(team, editor, Role.EDITOR)
    r = client.post("/invitations", {"workspace_id": team.pk, "role": "viewer"})
    assert r.status_code == 403
    assert client.get(f"/invitations?workspace_id={team.pk}").status_code == 403
    _, outsider = signed_in("outsider@example.com")
    r = outsider.post("/invitations", {"workspace_id": team.pk, "role": "viewer"})
    assert r.status_code == 404
    assert not Invitation.objects.exists()


def test_owner_cannot_create_instance_invitation(owner):
    assert owner[1].post("/invitations", {}).status_code == 403
    assert owner[1].get("/invitations").status_code == 403
    assert not Invitation.objects.exists()


def test_token_appears_only_in_create_response(admin, owner, team):
    token = _token(admin[1].post("/invitations", {}))
    ws_token = _token(
        owner[1].post("/invitations", {"workspace_id": team.pk, "role": "editor"})
    )
    listed = admin[1].get("/invitations")
    assert listed.status_code == 200 and len(listed.json()) == 2
    assert set(listed.json()[0]) == {
        "id",
        "workspace_id",
        "workspace_name",
        "role",
        "created_by_email",
        "expires_at",
    }
    mine = owner[1].get(f"/invitations?workspace_id={team.pk}")
    assert [i["role"] for i in mine.json()] == ["editor"]
    _accept(token)
    haystack = (
        listed.content.decode()
        + mine.content.decode()
        + str(list(Invitation.objects.values()))
        + str(list(AuditEvent.objects.values()))
    )
    assert token not in haystack and ws_token not in haystack


def test_revoke(admin, owner, team, signed_in):
    instance = admin[1].post("/invitations", {})
    in_team = owner[1].post("/invitations", {"workspace_id": team.pk, "role": "viewer"})
    instance_id, team_id = instance.json()["id"], in_team.json()["id"]
    # An owner manages their workspace's invitations, not the instance's.
    assert owner[1].delete(f"/invitations/{instance_id}").status_code == 403
    _, outsider = signed_in("outsider@example.com")
    assert outsider.delete(f"/invitations/{team_id}").status_code == 404

    assert owner[1].delete(f"/invitations/{team_id}").status_code == 204
    assert admin[1].delete(f"/invitations/{instance_id}").status_code == 204
    assert admin[1].delete(f"/invitations/{instance_id}").status_code == 404
    assert admin[1].get("/invitations").json() == []
    assert _accept(_token(instance)).status_code == 404
    assert _accept(_token(in_team)).status_code == 404


def test_accept_creates_user_joins_workspace_and_requires_enrolment(owner, team):
    token = _token(
        owner[1].post("/invitations", {"workspace_id": team.pk, "role": "editor"})
    )
    client = ApiClient()
    r = _accept(token, client=client)
    assert r.status_code == 201 and r.json() == {"next": "enrol"}
    user = User.objects.get(email="new@example.com")
    assert not user.is_instance_admin and user.check_password(PASSWORD)
    assert Membership.objects.get(user=user, workspace=team).role == Role.EDITOR
    session = client.get("/auth/session").json()
    assert session["state"] == "partial" and session["next"] == "enrol"
    assert client.get("/workspaces").status_code == 401

    invitation = Invitation.objects.get()
    assert invitation.used_by == user and invitation.used_at is not None
    accepted = AuditEvent.objects.get(event=events.INVITATION_ACCEPTED)
    assert accepted.actor == user and accepted.target_id == str(invitation.pk)
    assert AuditEvent.objects.filter(event=events.MEMBERSHIP_ADDED).exists()


def test_instance_invitation_joins_no_workspace(admin):
    token = _token(admin[1].post("/invitations", {}))
    assert _accept(token).status_code == 201
    assert not Membership.objects.exists()


def test_accept_normalises_email(admin):
    token = _token(admin[1].post("/invitations", {}))
    assert _accept(token, " New@Example.COM ").status_code == 201
    assert User.objects.filter(email="new@example.com").exists()


def test_accept_applies_password_rules(admin):
    token = _token(admin[1].post("/invitations", {}))
    for password in ("short", "password123456", "newperson2026"):
        r = _accept(token, "newperson@example.com", password)
        assert r.status_code == 400 and "password" in r.json()["error"]["details"]
    r = _accept(token, "not an email")
    assert r.status_code == 400 and "email" in r.json()["error"]["details"]
    assert _accept(token, "x" * 300 + "@example.com").status_code == 400
    assert _accept(token).status_code == 201  # the refusals left it usable


def test_accept_with_existing_email_is_409_and_leaves_invitation_unused(admin):
    token = _token(admin[1].post("/invitations", {}))
    r = _accept(token, " ADMIN@example.com")
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"
    assert Invitation.objects.get().used_at is None
    assert User.objects.count() == 1
    assert _accept(token).status_code == 201


def _kill(state: str, client) -> str:
    if state == "unknown":
        return "no-such-token"
    r = client.post("/invitations", {})
    token = _token(r)
    invitation = Invitation.objects.get(pk=r.json()["id"])
    if state == "used":
        assert _accept(token, "first@example.com").status_code == 201
    elif state == "expired":
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
        invitation.save()
    elif state == "revoked":
        assert client.delete(f"/invitations/{invitation.pk}").status_code == 204
    return token


def test_dead_tokens_are_indistinguishable(admin):
    answers = set()
    for state in ["unknown", "used", "expired", "revoked"]:
        token = _kill(state, admin[1])
        inspect = ApiClient().get(f"/invitations/token/{token}")
        accept = _accept(token)
        assert inspect.status_code == accept.status_code == 404
        assert inspect.json()["error"]["code"] == "invalid_token"
        answers.add((inspect.content, accept.content))
    assert len(answers) == 1
    assert not User.objects.filter(email="new@example.com").exists()


def test_invitation_expires_after_7_days(admin, time_machine):
    token = _token(admin[1].post("/invitations", {}))
    start = datetime.now(UTC)
    time_machine.move_to(start + timedelta(days=6, hours=23))
    assert ApiClient().get(f"/invitations/token/{token}").status_code == 200
    time_machine.move_to(start + timedelta(days=7, minutes=1))
    assert ApiClient().get(f"/invitations/token/{token}").status_code == 404
    assert _accept(token).status_code == 404


def test_two_simultaneous_accepts_create_one_user(transactional_db, make_user):
    creator = make_user("admin@example.com", admin=True)
    _, url = invitations.create(creator, None, None)
    token = url.rsplit("/", 1)[1]
    barrier = threading.Barrier(2)
    statuses = []

    def attempt(email: str) -> None:
        try:
            barrier.wait(timeout=5)
            statuses.append(_accept(token, email).status_code)
        finally:
            connection.close()

    threads = [
        threading.Thread(target=attempt, args=(f"new{i}@example.com",))
        for i in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(statuses) == [201, 404]
    assert User.objects.count() == 2


def test_bad_tokens_count_toward_ip_block(admin):
    token = _token(admin[1].post("/invitations", {}))
    stranger = ApiClient()
    for i in range(20):
        path = f"/invitations/token/wrong-{i}"
        r = (
            stranger.get(path)
            if i % 2
            else stranger.post(
                f"{path}/accept", {"email": "new@example.com", "password": PASSWORD}
            )
        )
        assert r.status_code == 404
    for r in (stranger.get(f"/invitations/token/{token}"), _accept(token)):
        assert r.status_code == 429 and r.json()["error"]["code"] == "locked"
    assert User.objects.count() == 1


def test_invitation_to_deleted_workspace_is_invalid(owner, team):
    token = _token(
        owner[1].post("/invitations", {"workspace_id": team.pk, "role": "viewer"})
    )
    services.soft_delete(team, actor=owner[0])
    assert ApiClient().get(f"/invitations/token/{token}").status_code == 404
    r = _accept(token)
    assert r.status_code == 404 and r.json()["error"]["code"] == "invalid_token"
    assert not User.objects.filter(email="new@example.com").exists()
