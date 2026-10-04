"""The spec's role table (section 6), checked exhaustively."""

import pytest
from api.errors import ApiError
from django.utils import timezone
from permissions import actions
from permissions.actions import (
    INSTANCE_CREATE_INVITATION,
    INSTANCE_MANAGE_USERS,
    INSTANCE_VIEW_AUDIT_LOG,
    WORKSPACE_CREATE,
    WORKSPACE_DELETE,
    WORKSPACE_INVITE,
    WORKSPACE_MANAGE_MEMBERS,
    WORKSPACE_RENAME,
    WORKSPACE_RESTORE,
    WORKSPACE_VIEW,
)
from permissions.core import INSTANCE, ROLE_ACTIONS, can, require, workspaces_for
from workspaces import services
from workspaces.models import Role

WHO = ["admin", "owner", "editor", "viewer", "outsider"]

# action -> who is allowed; "admin" is an instance admin with no membership
EXPECTED = {
    WORKSPACE_VIEW: {"admin", "owner", "editor", "viewer"},
    WORKSPACE_RENAME: {"admin", "owner"},
    WORKSPACE_MANAGE_MEMBERS: {"admin", "owner"},
    WORKSPACE_INVITE: {"admin", "owner"},
    WORKSPACE_DELETE: {"admin", "owner"},
    WORKSPACE_RESTORE: {"admin", "owner"},
}
INSTANCE_ADMIN_ONLY = [
    INSTANCE_MANAGE_USERS,
    INSTANCE_CREATE_INVITATION,
    INSTANCE_VIEW_AUDIT_LOG,
]


@pytest.fixture
def actors(make_user):
    return {who: make_user(f"{who}@example.com", admin=(who == "admin")) for who in WHO}


@pytest.fixture
def ws(actors):
    workspace = services.create(actors["owner"], "Team")
    services.add_member(workspace, actors["editor"], Role.EDITOR)
    services.add_member(workspace, actors["viewer"], Role.VIEWER)
    return workspace


@pytest.mark.parametrize("action", EXPECTED)
@pytest.mark.parametrize("who", WHO)
def test_workspace_matrix(db, actors, ws, action, who):
    allowed = who in EXPECTED[action]
    assert can(actors[who], action, ws) is allowed
    assert (ws in workspaces_for(actors[who], action)) is allowed


@pytest.mark.parametrize("action", INSTANCE_ADMIN_ONLY)
@pytest.mark.parametrize("who", WHO)
def test_instance_actions_are_admin_only(db, actors, ws, action, who):
    assert can(actors[who], action, INSTANCE) is (who == "admin")


@pytest.mark.parametrize("who", WHO)
def test_any_active_user_may_create_a_workspace(db, actors, who):
    assert can(actors[who], WORKSPACE_CREATE, INSTANCE) is True


@pytest.mark.parametrize("who", WHO)
def test_inactive_user_can_do_nothing(db, actors, ws, who):
    user = actors[who]
    user.is_active = False
    user.save()
    for action in EXPECTED:
        assert can(user, action, ws) is False
        assert ws not in workspaces_for(user, action)
    for action in [*INSTANCE_ADMIN_ONLY, WORKSPACE_CREATE]:
        assert can(user, action, INSTANCE) is False


@pytest.mark.parametrize("who", WHO)
def test_deleted_workspace_allows_only_restore(db, actors, ws, who):
    ws.deleted_at = timezone.now()
    ws.save()
    for action in EXPECTED:
        allowed = action == WORKSPACE_RESTORE and who in EXPECTED[action]
        assert can(actors[who], action, ws) is allowed
        assert (ws in workspaces_for(actors[who], action)) is allowed


def test_unknown_action_raises_value_error(db, actors, ws):
    with pytest.raises(ValueError):
        can(actors["admin"], "workspace.explode", ws)
    with pytest.raises(ValueError):
        can(actors["admin"], "workspace.explode", INSTANCE)
    with pytest.raises(ValueError):
        workspaces_for(actors["admin"], "workspace.explode")


def test_action_on_the_wrong_kind_of_target_raises(db, actors, ws):
    with pytest.raises(ValueError):
        can(actors["admin"], INSTANCE_MANAGE_USERS, ws)
    with pytest.raises(ValueError):
        can(actors["admin"], WORKSPACE_VIEW, INSTANCE)
    with pytest.raises(ValueError):
        can(actors["admin"], WORKSPACE_VIEW, object())


def test_require_is_404_for_the_unseen_and_403_for_the_seen(db, actors, ws):
    require(actors["owner"], WORKSPACE_RENAME, ws)
    with pytest.raises(ApiError) as hidden:
        require(actors["outsider"], WORKSPACE_RENAME, ws)
    assert (hidden.value.status, hidden.value.code) == (404, "not_found")
    with pytest.raises(ApiError) as seen:
        require(actors["viewer"], WORKSPACE_RENAME, ws)
    assert (seen.value.status, seen.value.code) == (403, "forbidden")
    with pytest.raises(ApiError) as instance:
        require(actors["owner"], INSTANCE_MANAGE_USERS, INSTANCE)
    assert instance.value.status == 403


def test_role_table_covers_every_role():
    assert set(ROLE_ACTIONS) == set(Role)


def test_every_action_constant_is_covered_by_this_file():
    declared = {
        value
        for name, value in vars(actions).items()
        if name.isupper() and isinstance(value, str)
    }
    covered = set(EXPECTED) | set(INSTANCE_ADMIN_ONLY) | {WORKSPACE_CREATE}
    assert declared == covered
