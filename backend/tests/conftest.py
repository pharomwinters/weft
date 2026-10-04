import json
from typing import Any

import pytest
from django.test import Client


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
