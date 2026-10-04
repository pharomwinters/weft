from datetime import timedelta

import pytest
from accounts.models import IpFailure
from accounts.net import client_ip
from accounts.throttle import (
    ACCOUNT_LIMIT,
    IP_LIMIT,
    WINDOW,
    is_blocked,
    record_failure,
    record_success,
    reset_account,
)
from audit import events
from audit.models import AuditEvent

EMAIL = "a@example.com"


def test_constants_agree_with_axes_settings(settings):
    assert (5, 20, timedelta(minutes=15)) == (ACCOUNT_LIMIT, IP_LIMIT, WINDOW)
    assert settings.AXES_FAILURE_LIMIT == ACCOUNT_LIMIT
    assert settings.AXES_COOLOFF_TIME == WINDOW


def test_forwarded_header_ignored_when_no_trusted_proxy(rf, settings):
    settings.TRUSTED_PROXY_COUNT = 0
    req = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4")
    assert client_ip(req) == "10.0.0.1"


def test_one_trusted_proxy_uses_rightmost_entry(rf, settings):
    settings.TRUSTED_PROXY_COUNT = 1
    req = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="6.6.6.6, 1.2.3.4")
    assert client_ip(req) == "1.2.3.4"  # attacker-supplied 6.6.6.6 is ignored


def test_two_trusted_proxies_use_second_from_right(rf, settings):
    settings.TRUSTED_PROXY_COUNT = 2
    req = rf.get(
        "/",
        REMOTE_ADDR="10.0.0.1",
        HTTP_X_FORWARDED_FOR="6.6.6.6, 1.2.3.4, 10.0.0.2",
    )
    assert client_ip(req) == "1.2.3.4"


def test_ipv6_is_supported(rf, settings):
    settings.TRUSTED_PROXY_COUNT = 1
    req = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="2001:db8::1")
    assert client_ip(req) == "2001:db8::1"
    assert client_ip(rf.get("/", REMOTE_ADDR="2001:db8::2")) == "2001:db8::2"


@pytest.mark.parametrize("header", ["not-an-ip", "1.2.3.4, garbage", "", "1.2.3.4,"])
def test_garbage_forwarded_header_falls_back_to_remote_addr(rf, settings, header):
    settings.TRUSTED_PROXY_COUNT = 1
    req = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR=header)
    assert client_ip(req) == "10.0.0.1"


def test_too_few_forwarded_entries_falls_back_to_remote_addr(rf, settings):
    settings.TRUSTED_PROXY_COUNT = 2
    req = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4")
    assert client_ip(req) == "10.0.0.1"


def test_account_locks_after_five_failures(db, req):
    for _ in range(4):
        record_failure(req, EMAIL)
    assert not is_blocked(req, EMAIL)
    record_failure(req, EMAIL)
    assert is_blocked(req, EMAIL)


def test_account_lock_expires_after_15_minutes(db, req, time_machine):
    time_machine.move_to("2026-10-03 12:00:00", tick=False)
    for _ in range(5):
        record_failure(req, EMAIL)
    time_machine.move_to("2026-10-03 12:14:00", tick=False)
    assert is_blocked(req, EMAIL)
    time_machine.move_to("2026-10-03 12:15:01", tick=False)
    assert not is_blocked(req, EMAIL)


def test_failures_while_locked_do_not_extend_the_lock(db, req, time_machine):
    time_machine.move_to("2026-10-03 12:00:00", tick=False)
    for _ in range(5):
        record_failure(req, EMAIL)
    time_machine.move_to("2026-10-03 12:10:00", tick=False)
    record_failure(req, EMAIL)
    time_machine.move_to("2026-10-03 12:15:01", tick=False)
    assert not is_blocked(req, EMAIL)


def test_success_clears_account_counter(db, req):
    for _ in range(4):
        record_failure(req, EMAIL)
    record_success(req, EMAIL)
    record_failure(req, EMAIL)
    assert not is_blocked(req, EMAIL)


def test_reset_account_unlocks_but_leaves_address_counts(db, req):
    for _ in range(5):
        record_failure(req, EMAIL)
    assert is_blocked(req, EMAIL)
    reset_account(EMAIL)
    assert not is_blocked(req, EMAIL)
    for _ in range(IP_LIMIT - 5):
        record_failure(req, None)
    assert is_blocked(req, None)


def test_email_variants_share_one_counter(db, req):
    for e in [
        "A@example.com",
        " a@example.com",
        "a@EXAMPLE.com",
        "a@example.com",
        "A@Example.Com",
    ]:
        record_failure(req, e)
    assert is_blocked(req, "a@example.com")
    assert is_blocked(req, " A@EXAMPLE.COM ")


def test_unknown_email_locks_like_a_real_one(db, req, make_user):
    make_user("real@example.com")
    for e in ("real@example.com", "ghost@example.com"):
        for _ in range(5):
            record_failure(req, e)
    assert is_blocked(req, "real@example.com")
    assert is_blocked(req, "ghost@example.com")


def test_account_lock_does_not_depend_on_address(db, rf):
    for n in range(5):
        record_failure(rf.get("/", REMOTE_ADDR=f"203.0.113.{n + 20}"), EMAIL)
    assert is_blocked(rf.get("/", REMOTE_ADDR="198.51.100.1"), EMAIL)
    assert not is_blocked(rf.get("/", REMOTE_ADDR="198.51.100.1"), "other@example.com")


def test_failures_without_email_only_count_against_address(db, req):
    for _ in range(10):
        record_failure(req, None)
    assert not is_blocked(req, EMAIL)
    assert not is_blocked(req, None)


def test_ip_blocked_after_twenty_failures_across_accounts(db, rf):
    req = rf.get("/", REMOTE_ADDR="203.0.113.9")
    for n in range(IP_LIMIT - 1):
        record_failure(req, f"user{n}@example.com")
    assert not is_blocked(req, None)
    record_failure(req, "user-last@example.com")
    assert is_blocked(req, None)
    assert is_blocked(req, "fresh@example.com")
    assert not is_blocked(rf.get("/", REMOTE_ADDR="203.0.113.10"), None)


def test_ip_block_lifts_when_failures_leave_the_window(db, rf, time_machine):
    req = rf.get("/", REMOTE_ADDR="203.0.113.9")
    time_machine.move_to("2026-10-03 12:00:00", tick=False)
    for n in range(IP_LIMIT):
        record_failure(req, f"user{n}@example.com")
    assert is_blocked(req, None)
    time_machine.move_to("2026-10-03 12:14:59", tick=False)
    assert is_blocked(req, None)
    time_machine.move_to("2026-10-03 12:15:01", tick=False)
    assert not is_blocked(req, None)


def test_ip_block_lasts_15_minutes_from_the_crossing_failure(db, rf, time_machine):
    req = rf.get("/", REMOTE_ADDR="203.0.113.9")
    time_machine.move_to("2026-10-03 12:00:00", tick=False)
    for _ in range(IP_LIMIT - 1):
        record_failure(req, None)
    time_machine.move_to("2026-10-03 12:14:59", tick=False)
    record_failure(req, None)
    time_machine.move_to("2026-10-03 12:29:58", tick=False)
    assert is_blocked(req, None)
    time_machine.move_to("2026-10-03 12:30:00", tick=False)
    assert not is_blocked(req, None)


def test_failures_during_an_ip_block_do_not_extend_it(db, rf, time_machine):
    req = rf.get("/", REMOTE_ADDR="203.0.113.9")
    time_machine.move_to("2026-10-03 12:00:00", tick=False)
    for _ in range(IP_LIMIT):
        record_failure(req, None)
    time_machine.move_to("2026-10-03 12:10:00", tick=False)
    record_failure(req, None)
    assert IpFailure.objects.count() == IP_LIMIT
    assert AuditEvent.objects.filter(event=events.LOGIN_FAILURE).count() == IP_LIMIT + 1
    time_machine.move_to("2026-10-03 12:15:01", tick=False)
    assert not is_blocked(req, None)


def test_account_lock_lasts_full_window_across_addresses_and_agents(
    db, rf, time_machine
):
    time_machine.move_to("2026-10-03 12:00:00", tick=False)
    record_failure(
        rf.get("/", REMOTE_ADDR="203.0.113.1", HTTP_USER_AGENT="ua-0"), EMAIL
    )
    time_machine.move_to("2026-10-03 12:14:00", tick=False)
    for n in range(1, 5):
        record_failure(
            rf.get("/", REMOTE_ADDR=f"203.0.113.{n + 1}", HTTP_USER_AGENT=f"ua-{n}"),
            EMAIL,
        )
    probe = rf.get("/", REMOTE_ADDR="198.51.100.1")
    assert is_blocked(probe, EMAIL)
    time_machine.move_to("2026-10-03 12:28:00", tick=False)
    assert is_blocked(probe, EMAIL)
    time_machine.move_to("2026-10-03 12:29:01", tick=False)
    assert not is_blocked(probe, EMAIL)


def test_overlong_email_counts_only_against_the_address(db, req):
    long_email = "x" * 1000 + "@example.com"
    record_failure(req, long_email)
    assert AuditEvent.objects.filter(event=events.LOGIN_FAILURE).count() == 1
    failures = AuditEvent.objects.filter(event=events.LOGIN_FAILURE)
    assert all(e.details == {} for e in failures) and failures.exists()
    assert IpFailure.objects.filter(ip="203.0.113.9").count() == 1
    assert not is_blocked(req, long_email)
    record_success(req, long_email)
    reset_account(long_email)


def test_old_address_rows_are_pruned_on_write(db, req, time_machine):
    time_machine.move_to("2026-10-03 12:00:00", tick=False)
    record_failure(req, None)
    time_machine.move_to("2026-10-04 12:00:01", tick=False)
    record_failure(req, None)
    assert IpFailure.objects.count() == 1


def test_rotating_forwarded_header_does_not_dodge_ip_block(db, rf, settings):
    settings.TRUSTED_PROXY_COUNT = 0
    for n in range(IP_LIMIT):
        req = rf.get(
            "/",
            REMOTE_ADDR="203.0.113.9",
            HTTP_X_FORWARDED_FOR=f"9.9.9.{n}",
        )
        record_failure(req, None)
    spoofed = rf.get("/", REMOTE_ADDR="203.0.113.9", HTTP_X_FORWARDED_FOR="7.7.7.7")
    assert is_blocked(spoofed, None)


def test_lockout_recorded_once_in_audit(db, req):
    for _ in range(8):
        record_failure(req, EMAIL)
    lockouts = AuditEvent.objects.filter(event=events.LOCKOUT)
    assert [e.details for e in lockouts] == [{"scope": "account"}]
    failures = AuditEvent.objects.filter(event=events.LOGIN_FAILURE)
    assert failures.count() == 8
    assert {(e.ip, e.details["email"]) for e in failures} == {("203.0.113.9", EMAIL)}


def test_ip_lockout_recorded_once_in_audit(db, req):
    for _ in range(IP_LIMIT + 3):
        record_failure(req, None)
    lockouts = AuditEvent.objects.filter(event=events.LOCKOUT)
    assert [e.details for e in lockouts] == [{"scope": "ip"}]
    assert AuditEvent.objects.get(event=events.LOCKOUT).ip == "203.0.113.9"
    failures = AuditEvent.objects.filter(event=events.LOGIN_FAILURE)
    assert all(e.details == {} for e in failures) and failures.exists()


def test_failure_without_email_is_audited_without_email(db, req):
    record_failure(req, None)
    failures = AuditEvent.objects.filter(event=events.LOGIN_FAILURE)
    assert all(e.details == {} for e in failures) and failures.exists()
