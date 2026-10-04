from datetime import UTC, datetime, timedelta

import pytest
from accounts import recovery, sessions, throttle
from accounts.models import RecoveryCode, TotpDevice, UserSession
from accounts.totp import begin_enrolment, clear, confirm_enrolment, verify
from audit import events
from audit.models import AuditEvent
from django.contrib.sessions.models import Session

from .conftest import PASSWORD, ApiClient

NOW = datetime(2026, 10, 3, 12, 0, 10, tzinfo=UTC)


def login(client, email="u@example.com", password=PASSWORD):
    return client.post("/auth/login", {"email": email, "password": password})


@pytest.fixture
def enrolled_user(user):
    return user


@pytest.fixture
def partial_enrolled_client(api_client, enrolled_user) -> ApiClient:
    assert login(api_client).json() == {"next": "verify"}
    return api_client


@pytest.fixture
def code_for_pending(code_for):
    return lambda user, offset=0: code_for(user, offset, confirmed=False)


def _start(client) -> dict:
    r = client.post("/auth/enrol/start")
    assert r.status_code == 200
    return r.json()


def _partial_user():
    from accounts.models import User

    return User.objects.get(email="u@example.com")


def test_secret_is_not_stored_in_plaintext(db, make_user):
    u = make_user()
    secret, uri = begin_enrolment(u)
    raw = TotpDevice.objects.get(user=u).secret_encrypted
    assert secret not in str(raw) and uri.startswith("otpauth://totp/")
    assert f"secret={secret}" in uri and "u%40example.com" in uri


def test_begin_enrolment_replaces_the_pending_device(db, make_user):
    u = make_user()
    first, _ = begin_enrolment(u)
    second, _ = begin_enrolment(u)
    assert first != second
    assert TotpDevice.objects.filter(user=u).count() == 1


def test_enrolment_needs_a_valid_code(partial_client):
    _start(partial_client)
    r = partial_client.post("/auth/enrol/confirm", {"code": "000000"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_code"
    assert TotpDevice.objects.get().confirmed is False
    assert not RecoveryCode.objects.exists()
    assert partial_client.get("/auth/session").json()["state"] == "partial"


def test_confirm_returns_ten_codes_once_and_verifies_session(
    partial_client, code_for_pending
):
    body = _start(partial_client)
    assert set(body) == {"secret", "otpauth_uri"}
    u = _partial_user()
    r = partial_client.post("/auth/enrol/confirm", {"code": code_for_pending(u)})
    assert r.status_code == 200
    assert len(r.json()["recovery_codes"]) == 10 and r.json()["next"] is None
    session = partial_client.get("/auth/session").json()
    assert session["state"] == "verified" and session["next"] is None
    assert TotpDevice.objects.get(user=u).confirmed is True
    assert AuditEvent.objects.filter(event=events.TOTP_ENROLLED, actor=u).count() == 1
    # The codes are never shown again: both enrolment endpoints are now closed.
    for path in ("/auth/enrol/start", "/auth/enrol/confirm"):
        again = partial_client.post(path, {"code": "000000"})
        assert again.status_code == 409


def test_enrolled_user_cannot_enrol_again_from_a_partial_session(
    partial_enrolled_client, enrolled_user, code_for
):
    r = partial_enrolled_client.post("/auth/enrol/start")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_enrolled"
    r = partial_enrolled_client.post(
        "/auth/enrol/confirm", {"code": code_for(enrolled_user)}
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_enrolled"


def test_recovery_codes_have_the_documented_format(db, make_user):
    codes = recovery.generate(make_user())
    assert len(set(codes)) == 10
    for code in codes:
        groups = code.split("-")
        assert [len(g) for g in groups] == [4, 4, 4, 4]
        assert set("".join(groups)) <= set(recovery.ALPHABET)
    assert len(recovery.ALPHABET) == 32 and recovery.ALPHABET.islower()


def test_recovery_codes_stored_hashed(db, make_user):
    codes = recovery.generate(make_user())
    stored = str(list(RecoveryCode.objects.values()))
    for code in codes:
        assert code not in stored and code.replace("-", "") not in stored


def test_generate_replaces_existing_codes(db, make_user):
    u = make_user()
    old = recovery.generate(u)
    recovery.generate(u)
    assert RecoveryCode.objects.filter(user=u).count() == 10
    assert recovery.redeem(u, old[0]) is False


def test_user_without_device_cannot_reach_verify(partial_client):
    for path in ("/auth/verify", "/auth/recovery"):
        r = partial_client.post(path, {"code": "123456"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "auth_required"
        assert r.json()["error"]["details"] == {"session": "partial", "next": "enrol"}


def test_session_key_rotates_on_promotion(
    partial_enrolled_client, enrolled_user, code_for
):
    cookies = partial_enrolled_client._client.cookies
    before = cookies["sessionid"].value
    r = partial_enrolled_client.post("/auth/verify", {"code": code_for(enrolled_user)})
    assert r.status_code == 200 and r.json() == {"next": None}
    after = cookies["sessionid"].value
    assert before != after
    assert not Session.objects.filter(session_key=before).exists()
    row = UserSession.objects.get(user=enrolled_user)
    assert row.session_key == after and row.ip == "127.0.0.1"


def test_accepted_code_cannot_be_replayed(db, enrolled_user, code_for):
    u = enrolled_user
    c = code_for(u)
    assert verify(u, c) is True
    assert verify(u, c) is False


def test_earlier_step_is_rejected_after_a_later_one(db, enrolled_user, code_for):
    u = enrolled_user
    earlier = code_for(u, -1)
    assert verify(u, code_for(u)) is True
    assert verify(u, earlier) is False


def test_adjacent_step_accepted_two_steps_away_rejected(
    db, enrolled_user, code_for, time_machine
):
    time_machine.move_to(NOW, tick=False)
    u = enrolled_user
    assert verify(u, code_for(u, -2)) is False
    assert verify(u, code_for(u, 2)) is False
    assert verify(u, code_for(u, -1)) is True
    assert verify(u, code_for(u, 1)) is True


def test_code_expires_with_the_clock(db, enrolled_user, code_for, time_machine):
    time_machine.move_to(NOW, tick=False)
    code = code_for(enrolled_user)
    time_machine.move_to(NOW + timedelta(seconds=61), tick=False)
    assert verify(enrolled_user, code) is False


def test_confirm_enrolment_replaces_the_confirmed_device(db, enrolled_user, code_for):
    u = enrolled_user
    old_code = code_for(u)
    begin_enrolment(u)
    assert confirm_enrolment(u, "000000") is False
    assert TotpDevice.objects.filter(user=u).count() == 2
    assert confirm_enrolment(u, code_for(u, confirmed=False)) is True
    assert TotpDevice.objects.get(user=u).confirmed is True
    assert verify(u, old_code) is False


def test_clear_removes_devices_and_recovery_codes(db, enrolled_user):
    recovery.generate(enrolled_user)
    clear(enrolled_user)
    assert not TotpDevice.objects.exists() and not RecoveryCode.objects.exists()


@pytest.mark.parametrize("bad", ["", "abcdef", "12345", "1234567", "1" * 500, "١٢٣٤٥٦"])
def test_malformed_code_is_a_failure_not_an_error(partial_enrolled_client, bad):
    for path in ("/auth/verify", "/auth/recovery"):
        r = partial_enrolled_client.post(path, {"code": bad})
        assert r.status_code in (400, 401)
        assert r.json()["error"]["code"] in ("validation", "invalid_code")


def test_malformed_code_at_enrolment_is_a_failure(partial_client):
    _start(partial_client)
    for bad in ["", "abcdef", "1" * 500, "١٢٣٤٥٦"]:
        r = partial_client.post("/auth/enrol/confirm", {"code": bad})
        assert r.status_code in (400, 401)


def test_code_with_spaces_and_leading_zero_accepted(
    partial_enrolled_client, enrolled_user, monkeypatch
):
    # Pin the algorithm's output so the code is certain to start with a zero.
    monkeypatch.setattr("django_otp.oath.hotp", lambda key, counter, digits=6: 12345)
    r = partial_enrolled_client.post("/auth/verify", {"code": "012 345"})
    assert r.status_code == 200 and r.json() == {"next": None}


def test_code_without_its_leading_zero_is_rejected(
    partial_enrolled_client, monkeypatch
):
    monkeypatch.setattr("django_otp.oath.hotp", lambda key, counter, digits=6: 12345)
    r = partial_enrolled_client.post("/auth/verify", {"code": "12345"})
    assert r.status_code == 401


def test_recovery_code_works_once(partial_enrolled_client, enrolled_user, api_client):
    code = recovery.generate(enrolled_user)[0]
    r = partial_enrolled_client.post("/auth/recovery", {"code": code})
    assert r.status_code == 200 and r.json() == {"next": None}
    assert partial_enrolled_client.get("/auth/session").json()["state"] == "verified"
    used = AuditEvent.objects.filter(event=events.RECOVERY_CODE_USED)
    assert used.count() == 1 and used.get().actor == enrolled_user
    assert "code" not in str(used.get().details)

    second = ApiClient()
    login(second)
    r = second.post("/auth/recovery", {"code": code})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_code"
    assert used.count() == 1


def test_recovery_code_accepts_upper_case_and_missing_dashes(
    partial_enrolled_client, enrolled_user
):
    code = recovery.generate(enrolled_user)[0]
    typed = code.replace("-", "").upper()
    r = partial_enrolled_client.post("/auth/recovery", {"code": f" {typed} "})
    assert r.status_code == 200


def test_another_users_recovery_code_is_rejected(
    partial_enrolled_client, make_user, enrolled
):
    other = enrolled(make_user("other@example.com"))
    code = recovery.generate(other)[0]
    r = partial_enrolled_client.post("/auth/recovery", {"code": code})
    assert r.status_code == 401


@pytest.mark.parametrize("path", ["/auth/verify", "/auth/recovery"])
def test_five_bad_codes_lock_the_account(
    partial_enrolled_client, enrolled_user, code_for, path
):
    for _ in range(5):
        r = partial_enrolled_client.post(path, {"code": "000000"})
        assert r.status_code == 401
    good = code_for(enrolled_user)
    for locked_path in ("/auth/verify", "/auth/recovery"):
        r = partial_enrolled_client.post(locked_path, {"code": good})
        assert r.status_code == 429 and r.json()["error"]["code"] == "locked"
    assert partial_enrolled_client.get("/auth/session").json()["state"] == "partial"


def test_bad_password_and_bad_code_failures_add_up(api_client, enrolled_user, code_for):
    for _ in range(3):
        assert login(api_client, password="wrong wrong wrong").status_code == 401
    assert login(api_client).status_code == 200
    for _ in range(2):
        assert api_client.post("/auth/verify", {"code": "000000"}).status_code == 401
    r = api_client.post("/auth/verify", {"code": code_for(enrolled_user)})
    assert r.status_code == 429


def test_full_verification_clears_failure_counter(
    api_client, enrolled_user, code_for, rf
):
    for _ in range(4):
        login(api_client, password="wrong wrong wrong")
    login(api_client)
    r = api_client.post("/auth/verify", {"code": code_for(enrolled_user)})
    assert r.status_code == 200
    # Four more failures would lock an uncleared counter at the first of them.
    other = ApiClient()
    for _ in range(4):
        login(other, password="wrong wrong wrong")
    assert not throttle.is_blocked(rf.get("/"), enrolled_user.email)


def test_end_sessions_keeps_only_the_excepted_key(
    enrolled_user, make_verified_client, make_user, enrolled
):
    first = make_verified_client(enrolled_user)
    second = make_verified_client(enrolled_user, offset=1)
    bystander_user = enrolled(make_user("other@example.com"))
    bystander = make_verified_client(bystander_user)
    keep = first._client.cookies["sessionid"].value

    sessions.end_sessions(enrolled_user, except_key=keep)

    assert first.get("/auth/session").json()["state"] == "verified"
    assert second.get("/auth/session").json()["state"] == "anonymous"
    assert bystander.get("/auth/session").json()["state"] == "verified"
    rows = UserSession.objects.filter(user=enrolled_user)
    assert [row.session_key for row in rows] == [keep]

    sessions.end_sessions(enrolled_user)
    assert first.get("/auth/session").json()["state"] == "anonymous"
    assert not UserSession.objects.filter(user=enrolled_user).exists()


def test_verified_session_of_deactivated_user_is_refused(verified_client, user):
    user.is_active = False
    user.save()
    assert verified_client.get("/auth/session").json()["state"] == "anonymous"


def test_logout_removes_the_session_row(verified_client, user):
    assert UserSession.objects.filter(user=user).count() == 1
    assert verified_client.post("/auth/logout").status_code == 204
    assert not UserSession.objects.filter(user=user).exists()
    assert verified_client.get("/auth/session").json()["state"] == "anonymous"


def test_login_while_verified_starts_a_new_partial_session(verified_client, user):
    r = login(verified_client)
    assert r.status_code == 200 and r.json() == {"next": "verify"}
    assert verified_client.get("/auth/session").json()["state"] == "partial"
    assert not UserSession.objects.filter(user=user).exists()


def test_second_factor_endpoints_refuse_a_verified_session(verified_client):
    for path in ("/auth/verify", "/auth/recovery", "/auth/enrol/confirm"):
        r = verified_client.post(path, {"code": "000000"})
        assert r.status_code == 409 and r.json()["error"]["code"] == "already_verified"
    assert verified_client.post("/auth/enrol/start").status_code == 409


def test_second_factor_stays_partial_while_a_password_change_is_due(
    api_client, make_user, enrolled, code_for
):
    u = enrolled(make_user(must_change=True))
    assert login(api_client).json() == {"next": "verify"}
    r = api_client.post("/auth/verify", {"code": code_for(u)})
    assert r.status_code == 200 and r.json() == {"next": "change_password"}
    body = api_client.get("/auth/session").json()
    assert body["state"] == "partial" and body["next"] == "change_password"
    assert not UserSession.objects.exists()
