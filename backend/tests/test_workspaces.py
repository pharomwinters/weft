import threading
from datetime import UTC, datetime, timedelta

import pytest
from api.errors import ApiError
from audit import events
from audit.models import AuditEvent
from django.db import connection
from workspaces import services
from workspaces.models import Membership, Role, Workspace


@pytest.fixture
def owner(signed_in):
    return signed_in("owner@example.com")


@pytest.fixture
def team(owner):
    """A workspace owned by owner@example.com, as the API returned it."""
    _, client = owner
    r = client.post("/workspaces", {"name": "Team"})
    assert r.status_code == 201
    return r.json()


def _add(client, team, user, role):
    r = client.post(
        f"/workspaces/{team['id']}/members", {"email": user.email, "role": role}
    )
    assert r.status_code == 201, r.content
    return r


def test_creator_becomes_owner(owner, team):
    user, client = owner
    assert team["name"] == "Team" and team["role"] == "owner"
    assert team["deleted_at"] is None
    members = client.get(f"/workspaces/{team['id']}/members").json()
    assert members == [
        {"user_id": user.pk, "email": "owner@example.com", "role": "owner"}
    ]
    assert Workspace.objects.get(pk=team["id"]).created_by == user


def test_name_trimmed_and_blank_rejected(owner, team):
    _, client = owner
    r = client.post("/workspaces", {"name": "  Sales  "})
    assert r.status_code == 201 and r.json()["name"] == "Sales"
    for bad in ("", "   ", "x" * 101):
        for r in (
            client.post("/workspaces", {"name": bad}),
            client.patch(f"/workspaces/{team['id']}", {"name": bad}),
        ):
            assert r.status_code == 400 and r.json()["error"]["code"] == "validation"
            assert "name" in r.json()["error"]["details"]
    assert client.post("/workspaces", {"name": "x" * 100}).status_code == 201
    r = client.patch(f"/workspaces/{team['id']}", {"name": " Renamed "})
    assert r.status_code == 200 and r.json()["name"] == "Renamed"


def test_list_shows_only_my_workspaces_admin_sees_all(owner, team, signed_in):
    _, client = owner
    _, other = signed_in("other@example.com")
    other.post("/workspaces", {"name": "Other"})
    _, admin = signed_in("admin@example.com", admin=True)

    assert [w["name"] for w in client.get("/workspaces").json()] == ["Team"]
    assert [w["name"] for w in other.get("/workspaces").json()] == ["Other"]
    seen = admin.get("/workspaces").json()
    assert [(w["name"], w["role"]) for w in seen] == [("Other", None), ("Team", None)]


def test_outsider_gets_404_not_403(team, signed_in):
    _, outsider = signed_in("outsider@example.com")
    base = f"/workspaces/{team['id']}"
    for r in (
        outsider.get(base),
        outsider.patch(base, {"name": "Mine"}),
        outsider.delete(base),
        outsider.post(f"{base}/restore"),
        outsider.get(f"{base}/members"),
        outsider.post(f"{base}/members", {"email": "x@example.com", "role": "viewer"}),
        outsider.get("/workspaces/999999"),
    ):
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("role", ["viewer", "editor"])
def test_viewer_rename_is_403(owner, team, signed_in, role):
    user, client = signed_in("member@example.com")
    _add(owner[1], team, user, role)
    base = f"/workspaces/{team['id']}"
    assert client.get(base).json()["role"] == role
    assert len(client.get(f"{base}/members").json()) == 2
    for r in (
        client.patch(base, {"name": "Mine"}),
        client.delete(base),
        client.post(f"{base}/members", {"email": "x@example.com", "role": "viewer"}),
        client.patch(f"{base}/members/{owner[0].pk}", {"role": "viewer"}),
        client.delete(f"{base}/members/{owner[0].pk}"),
    ):
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert Workspace.objects.get(pk=team["id"]).name == "Team"


def test_cannot_remove_or_demote_last_owner(owner, team, signed_in):
    user, client = owner
    _, admin = signed_in("admin@example.com", admin=True)
    path = f"/workspaces/{team['id']}/members/{user.pk}"
    for actor in (client, admin):  # self-demotion and an admin's attempt alike
        for r in (actor.patch(path, {"role": "editor"}), actor.delete(path)):
            assert r.status_code == 409 and r.json()["error"]["code"] == "last_owner"
    assert Membership.objects.get(user=user).role == Role.OWNER


def test_owner_can_leave_when_another_owner_exists(owner, team, signed_in):
    user, client = owner
    second, second_client = signed_in("second@example.com")
    _add(client, team, second, "owner")
    path = f"/workspaces/{team['id']}/members/{user.pk}"
    assert client.delete(path).status_code == 204
    assert client.get(f"/workspaces/{team['id']}").status_code == 404
    assert second_client.get(f"/workspaces/{team['id']}").json()["role"] == "owner"


def test_change_role(owner, team, signed_in):
    member, _ = signed_in("member@example.com")
    _add(owner[1], team, member, "viewer")
    path = f"/workspaces/{team['id']}/members/{member.pk}"
    r = owner[1].patch(path, {"role": "editor"})
    assert r.status_code == 200 and r.json()["role"] == "editor"
    assert owner[1].patch(path, {"role": "boss"}).status_code == 400
    missing = f"/workspaces/{team['id']}/members/999999"
    assert owner[1].patch(missing, {"role": "editor"}).status_code == 404
    assert owner[1].delete(missing).status_code == 404


def test_concurrent_removal_of_last_two_owners_leaves_one(transactional_db, make_user):
    first, second = make_user("a@example.com"), make_user("b@example.com")
    workspace = services.create(first, "Team")
    services.add_member(workspace, second, Role.OWNER)
    barrier = threading.Barrier(2)
    outcomes = []

    def remove(user) -> None:
        try:
            barrier.wait(timeout=5)
            services.remove_member(workspace, user)
            outcomes.append("removed")
        except ApiError as exc:
            outcomes.append(exc.code)
        finally:
            connection.close()

    threads = [threading.Thread(target=remove, args=(u,)) for u in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(outcomes) == ["last_owner", "removed"]
    owners = Membership.objects.filter(workspace=workspace, role=Role.OWNER)
    assert owners.count() == 1


def test_add_member_by_email_variant(owner, team, signed_in):
    member, _ = signed_in("b@example.com")
    r = owner[1].post(
        f"/workspaces/{team['id']}/members",
        {"email": " B@Example.com ", "role": "editor"},
    )
    assert r.status_code == 201
    assert r.json() == {
        "user_id": member.pk,
        "email": "b@example.com",
        "role": "editor",
    }


def test_add_unknown_email_is_404_user_not_found(owner, team):
    r = owner[1].post(
        f"/workspaces/{team['id']}/members",
        {"email": "nobody@example.com", "role": "viewer"},
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "user_not_found"


def test_add_existing_member_is_409_already_member(owner, team, signed_in):
    member, _ = signed_in("member@example.com")
    _add(owner[1], team, member, "viewer")
    r = owner[1].post(
        f"/workspaces/{team['id']}/members",
        {"email": "MEMBER@example.com", "role": "editor"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_member"
    assert Membership.objects.get(user=member).role == Role.VIEWER


def test_delete_is_soft_and_hides_workspace(owner, team):
    _, client = owner
    base = f"/workspaces/{team['id']}"
    assert client.delete(base).status_code == 204
    assert client.get(base).status_code == 404
    assert client.get(f"{base}/members").status_code == 404
    assert client.patch(base, {"name": "Back"}).status_code == 404
    assert client.get("/workspaces").json() == []
    assert Workspace.objects.get(pk=team["id"]).deleted_at is not None


def test_restore_within_30_days(owner, team, signed_in, time_machine):
    user, client = owner
    member, member_client = signed_in("member@example.com")
    _add(client, team, member, "editor")
    base = f"/workspaces/{team['id']}"
    client.delete(base)

    deleted = client.get("/workspaces?deleted=true").json()
    assert [w["id"] for w in deleted] == [team["id"]] and deleted[0]["deleted_at"]
    assert member_client.get("/workspaces?deleted=true").json() == []
    assert member_client.post(f"{base}/restore").status_code == 404

    time_machine.move_to(datetime.now(UTC) + timedelta(days=29))
    services.restore(Workspace.objects.get(pk=team["id"]), actor=user)
    assert Workspace.objects.get(pk=team["id"]).deleted_at is None


def test_restore_through_the_api(owner, team):
    _, client = owner
    base = f"/workspaces/{team['id']}"
    client.delete(base)
    r = client.post(f"{base}/restore")
    assert r.status_code == 200 and r.json()["deleted_at"] is None
    assert client.get(base).status_code == 200


def test_restore_after_30_days_is_409_restore_expired(owner, team, time_machine):
    user, client = owner
    client.delete(f"/workspaces/{team['id']}")
    time_machine.move_to(datetime.now(UTC) + timedelta(days=30, minutes=1))
    workspace = Workspace.objects.get(pk=team["id"])
    with pytest.raises(ApiError) as raised:
        services.restore(workspace, actor=user)
    assert (raised.value.status, raised.value.code) == (409, "restore_expired")
    assert Workspace.objects.get(pk=team["id"]).deleted_at is not None
    assert (
        list(Workspace.objects.filter(deleted_at__gte=services.restorable_since()))
        == []
    )


def test_admin_who_is_not_a_member_can_manage_and_sees_role_null(
    owner, team, signed_in
):
    _, admin = signed_in("admin@example.com", admin=True)
    member, _ = signed_in("member@example.com")
    base = f"/workspaces/{team['id']}"
    assert admin.get(base).json()["role"] is None
    assert admin.patch(base, {"name": "Renamed"}).json()["name"] == "Renamed"
    _add(admin, team, member, "viewer")
    path = f"{base}/members/{member.pk}"
    assert admin.patch(path, {"role": "owner"}).status_code == 200
    assert admin.delete(path).status_code == 204
    assert admin.delete(base).status_code == 204
    assert [w["id"] for w in admin.get("/workspaces?deleted=true").json()] == [
        team["id"]
    ]
    assert admin.post(f"{base}/restore").status_code == 200


def test_membership_and_workspace_changes_are_audited(owner, team, signed_in):
    user, client = owner
    member, _ = signed_in("member@example.com")
    base = f"/workspaces/{team['id']}"
    _add(client, team, member, "viewer")
    client.patch(f"{base}/members/{member.pk}", {"role": "editor"})
    client.delete(f"{base}/members/{member.pk}")
    client.delete(base)
    client.post(f"{base}/restore")

    wanted = [
        events.WORKSPACE_CREATED,
        events.MEMBERSHIP_ADDED,
        events.MEMBERSHIP_CHANGED,
        events.MEMBERSHIP_REMOVED,
        events.WORKSPACE_DELETED,
        events.WORKSPACE_RESTORED,
    ]
    rows = list(AuditEvent.objects.filter(event__in=wanted).order_by("pk"))
    assert [row.event for row in rows] == wanted
    for row in rows:
        assert row.actor == user and row.ip == "127.0.0.1"
        assert (row.target_type, row.target_id) == ("workspace", str(team["id"]))
    assert rows[2].details == {"user_id": member.pk, "from": "viewer", "to": "editor"}
