"""Single-use recovery codes, stored hashed."""

import hashlib
import secrets

from django.db import transaction
from django.utils import timezone

from .models import RecoveryCode, User

CODE_COUNT = 10
# 32 symbols, so each character carries 5 bits: 16 characters are 80 bits.
ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
_GROUPS = 4
_GROUP_LENGTH = 4


def _normalise(code: str) -> str:
    return code.replace(" ", "").replace("-", "").lower()


def _hash(code: str) -> str:
    # 80 random bits cannot be guessed offline, so a slow hash adds nothing.
    return hashlib.sha256(_normalise(code).encode()).hexdigest()


def _new_code() -> str:
    return "-".join(
        "".join(secrets.choice(ALPHABET) for _ in range(_GROUP_LENGTH))
        for _ in range(_GROUPS)
    )


def generate(user: User) -> list[str]:
    """Replace the user's codes; the returned plain codes exist nowhere else."""
    codes = [_new_code() for _ in range(CODE_COUNT)]
    with transaction.atomic():
        RecoveryCode.objects.filter(user=user).delete()
        RecoveryCode.objects.bulk_create(
            RecoveryCode(user=user, code_hash=_hash(code)) for code in codes
        )
    return codes


def redeem(user: User, code: str) -> bool:
    """Use up one code. The conditional update lets only one request win."""
    used = RecoveryCode.objects.filter(
        user=user, code_hash=_hash(code), used_at__isnull=True
    ).update(used_at=timezone.now())
    return used == 1
