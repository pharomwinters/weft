import importlib
import sys
from pathlib import Path

import pytest
from config.env import EXAMPLE_VALUES, ConfigError, load_config
from cryptography.fernet import Fernet

REPO_ROOT = Path(__file__).resolve().parents[2]

VALID = {
    "DATABASE_URL": "postgres://u:p@h/db",
    "SECRET_KEY": "k" * 50,
    "TOTP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "PUBLIC_URL": "https://grid.example.com",
}


def test_valid_config_defaults():
    cfg = load_config(VALID)
    assert cfg.trusted_proxy_count == 0
    assert cfg.initial_admin_email is None and cfg.initial_admin_password is None


@pytest.mark.parametrize("key", list(VALID))
def test_missing_or_empty_required_value_refused(key):
    for bad in ({k: v for k, v in VALID.items() if k != key}, {**VALID, key: ""}):
        with pytest.raises(ConfigError, match=key):
            load_config(bad)


@pytest.mark.parametrize("key", list(VALID))
def test_example_value_refused(key):
    with pytest.raises(ConfigError, match=key):
        load_config({**VALID, key: EXAMPLE_VALUES[key]})


def test_example_values_match_env_example_file():
    text = (REPO_ROOT / ".env.example").read_text()
    for key, value in EXAMPLE_VALUES.items():
        assert f"{key}={value}" in text


def test_short_secret_key_refused():
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        load_config({**VALID, "SECRET_KEY": "k" * 31})
    assert load_config({**VALID, "SECRET_KEY": "k" * 32}).secret_key == "k" * 32


def test_invalid_fernet_key_refused():
    with pytest.raises(ConfigError, match="TOTP_ENCRYPTION_KEY"):
        load_config({**VALID, "TOTP_ENCRYPTION_KEY": "not-a-fernet-key"})


@pytest.mark.parametrize(
    "url", ["ftp://grid.example.com", "grid.example.com", "https://"]
)
def test_public_url_must_be_http_or_https(url):
    with pytest.raises(ConfigError, match="PUBLIC_URL"):
        load_config({**VALID, "PUBLIC_URL": url})
    assert load_config({**VALID, "PUBLIC_URL": "http://localhost:8000"})


def test_trusted_proxy_count_parsed_and_validated():
    assert load_config({**VALID, "TRUSTED_PROXY_COUNT": "2"}).trusted_proxy_count == 2
    for bad in ("x", "-1"):
        with pytest.raises(ConfigError, match="TRUSTED_PROXY_COUNT"):
            load_config({**VALID, "TRUSTED_PROXY_COUNT": bad})


def test_empty_initial_admin_password_is_none():
    cfg = load_config(
        {**VALID, "INITIAL_ADMIN_EMAIL": "a@b.co", "INITIAL_ADMIN_PASSWORD": ""}
    )
    assert cfg.initial_admin_email == "a@b.co"
    assert cfg.initial_admin_password is None


def test_production_settings_hard_code_debug_false(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "1")
    monkeypatch.delitem(sys.modules, "config.settings", raising=False)
    settings = importlib.import_module("config.settings")
    assert settings.DEBUG is False
