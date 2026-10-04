import pytest
from audit import events
from audit.models import AuditEvent
from audit.service import record


def test_record_stores_actor_target_ip(db, make_user, rf):
    u = make_user()
    req = rf.get("/", REMOTE_ADDR="203.0.113.9")
    e = record(events.LOGIN_SUCCESS, request=req, actor=u, target=u)
    assert (e.actor, e.target_type, e.target_id, e.ip) == (
        u,
        "user",
        str(u.pk),
        "203.0.113.9",
    )
    assert e.event == "login_success"
    assert e.time is not None


def test_record_without_request_or_target(db):
    e = record(events.LOGOUT, details={"reason": "x"})
    assert (e.ip, e.target_type, e.target_id, e.actor, e.details) == (
        None,
        "",
        "",
        None,
        {"reason": "x"},
    )


def test_event_constants_are_lowercase_names():
    assert events.TWOFA_RESET == "twofa_reset"
    assert events.SETUP_COMPLETED == "setup_completed"


def test_forbidden_detail_key_raises(db):
    with pytest.raises(ValueError):
        record(events.LOGIN_FAILURE, details={"password": "x"})
    assert not AuditEvent.objects.exists()


def test_forbidden_detail_key_nested_and_case_insensitive(db):
    with pytest.raises(ValueError):
        record(events.LOGIN_FAILURE, details={"a": {"b": [{"Token": "x"}]}})
    with pytest.raises(ValueError):
        record(events.LOGIN_FAILURE, details={"SECRET": "x"})
    assert not AuditEvent.objects.exists()


def test_events_are_append_only(db):
    e = record(events.LOGOUT)
    with pytest.raises(RuntimeError):
        e.save()
    with pytest.raises(RuntimeError):
        e.delete()


def test_queryset_update_and_delete_are_refused(db):
    record(events.LOGOUT)
    with pytest.raises(RuntimeError):
        AuditEvent.objects.update(event="x")
    with pytest.raises(RuntimeError):
        AuditEvent.objects.all().delete()
    assert AuditEvent.objects.get().event == "logout"


def test_event_survives_actor_deletion(db, make_user):
    u = make_user()
    e = record(events.LOGIN_SUCCESS, actor=u)
    u.delete()
    e.refresh_from_db()
    assert e.actor is None
    assert AuditEvent.objects.count() == 1
