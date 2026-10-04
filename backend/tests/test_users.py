import importlib
import sys

import pytest
from accounts.models import User, normalize_email
from accounts.passwords import (
    MAX_EMAIL_LENGTH,
    MAX_PASSWORD_LENGTH,
    validate_new_password,
)
from api.errors import ApiError
from django.db import IntegrityError, transaction


def test_email_normalised_on_create(db):
    u = User.objects.create_user(" Adam@Example.COM ", "correct horse battery")
    assert u.email == "adam@example.com"
    assert normalize_email(" X@Y.Co ") == "x@y.co"


def test_user_defaults(make_user):
    u = make_user()
    assert u.is_instance_admin is False
    assert u.must_change_password is False
    assert u.is_active is True
    assert u.created_at is not None
    assert u.check_password("correct horse battery")
    assert u.password != "correct horse battery"


def test_email_unique_case_insensitive(db, make_user):
    make_user("a@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_user("A@Example.com")


def test_database_constraint_is_case_insensitive(make_user):
    make_user("a@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.bulk_create([User(email="A@EXAMPLE.COM")])


def test_overlong_email_refused(db):
    local = "a" * (MAX_EMAIL_LENGTH - len("@example.com") + 1)
    with pytest.raises(ValueError):
        User.objects.create_user(f"{local}@example.com", "correct horse battery")


def test_password_minimum_length_12():
    with pytest.raises(ApiError) as e:
        validate_new_password("short1234567"[:11])
    assert e.value.status == 400
    assert e.value.code == "validation"
    assert e.value.details["password"]
    validate_new_password("x9!kq-Plm2#w")  # 12 characters, passes


def test_common_password_rejected():
    with pytest.raises(ApiError) as e:
        validate_new_password("password123456")
    assert e.value.status == 400
    assert any("common" in m for m in e.value.details["password"])


def test_password_similar_to_email_rejected(make_user):
    user = make_user("adamsmith@example.com")
    with pytest.raises(ApiError) as e:
        validate_new_password("adamsmith2026", user)
    assert any("similar" in m for m in e.value.details["password"])


def test_oversized_password_rejected_without_hashing(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("hashing must not run")

    monkeypatch.setattr("django.contrib.auth.hashers.make_password", boom)
    with pytest.raises(ApiError) as e:
        validate_new_password("a" * 1_000_000)
    assert e.value.status == 400
    assert str(MAX_PASSWORD_LENGTH) in e.value.details["password"][0]
    # exactly at the ceiling is not rejected for length
    validate_new_password(("x9!kq-Plm2#w" * 90)[:MAX_PASSWORD_LENGTH])


def test_production_hasher_is_argon2(monkeypatch):
    monkeypatch.delitem(sys.modules, "config.settings", raising=False)
    prod_settings = importlib.import_module("config.settings")
    assert prod_settings.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")
