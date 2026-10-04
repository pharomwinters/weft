import json
from typing import Any

import pytest
from accounts import totp
from accounts.models import TotpDevice, User
from django.test import Client
from django_otp.oath import TOTP

PASSWORD = "correct horse battery"


class ApiClient:
    """Test client for the JSON API: prefixes /api/v1 and sends JSON bodies."""

    prefix = "/api/v1"

    def __init__(self) -> None:
        self._client = Client()

    def _request(self, method: str, path: str, json_body: Any = None):
        kwargs: dict[str, Any] = {}
        if json_body is not None:
            kwargs["data"] = json.dumps(json_body)
            kwargs["content_type"] = "application/json"
        return getattr(self._client, method)(f"{self.prefix}{path}", **kwargs)

    def get(self, path: str, json: Any = None):
        return self._request("get", path, json)

    def post(self, path: str, json: Any = None):
        return self._request("post", path, json)

    def patch(self, path: str, json: Any = None):
        return self._request("patch", path, json)

    def put(self, path: str, json: Any = None):
        return self._request("put", path, json)

    def delete(self, path: str, json: Any = None):
        return self._request("delete", path, json)


@pytest.fixture
def api_client() -> ApiClient:
    return ApiClient()


@pytest.fixture
def make_user(db):
    def _make(
        email: str = "u@example.com",
        password: str = "correct horse battery",
        *,
        admin: bool = False,
        must_change: bool = False,
        active: bool = True,
    ) -> User:
        return User.objects.create_user(
            email,
            password,
            is_instance_admin=admin,
            must_change_password=must_change,
            is_active=active,
        )

    return _make


@pytest.fixture
def req(rf):
    return rf.get("/", REMOTE_ADDR="203.0.113.9")


@pytest.fixture
def partial_client(api_client, make_user) -> ApiClient:
    """An api_client that has passed the password step (user u@example.com)."""
    make_user()
    r = api_client.post(
        "/auth/login", {"email": "u@example.com", "password": "correct horse battery"}
    )
    assert r.status_code == 200
    return api_client


@pytest.fixture
def code_for():
    """code_for(user, offset=0, confirmed=True): a valid code for the user's device.

    A code is good once. For a second one in the same test pass offset=1 (the
    next time step, still inside the tolerance) or move the clock.
    """

    def _code(user: User, offset: int = 0, *, confirmed: bool = True) -> str:
        device = TotpDevice.objects.get(user=user, confirmed=confirmed)
        generator = TOTP(
            totp.device_key(device),
            step=totp.STEP_SECONDS,
            digits=totp.DIGITS,
            drift=offset,
        )
        return f"{generator.token():0{totp.DIGITS}d}"

    return _code


@pytest.fixture
def enrolled(db):
    """enrolled(user): gives the user a confirmed device, created directly."""

    def _enrol(user: User) -> User:
        totp.begin_enrolment(user)
        TotpDevice.objects.filter(user=user).update(confirmed=True)
        return user

    return _enrol


@pytest.fixture
def make_verified_client(code_for):
    """make_verified_client(user, password=..., offset=0): through login and verify."""

    def _make(user: User, password: str = PASSWORD, *, offset: int = 0) -> ApiClient:
        client = ApiClient()
        r = client.post("/auth/login", {"email": user.email, "password": password})
        assert r.status_code == 200, r.content
        r = client.post("/auth/verify", {"code": code_for(user, offset)})
        assert r.status_code == 200, r.content
        return client

    return _make


@pytest.fixture
def user(make_user, enrolled) -> User:
    """An enrolled user, u@example.com."""
    return enrolled(make_user())


@pytest.fixture
def verified_client(user, make_verified_client) -> ApiClient:
    """A client with a verified session for the `user` fixture."""
    return make_verified_client(user)


@pytest.fixture
def signed_in(make_user, enrolled, make_verified_client):
    """signed_in(email, admin=False): an enrolled user and their verified client."""

    def _signed_in(email: str, *, admin: bool = False) -> tuple[User, ApiClient]:
        account = enrolled(make_user(email, admin=admin))
        return account, make_verified_client(account)

    return _signed_in
