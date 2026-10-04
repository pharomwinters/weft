"""TOTP devices: enrolment, verification and replay protection.

django-otp supplies the algorithm only. The state lives in our own models so
the secret is encrypted at rest and an accepted code cannot be used twice.
"""

import base64
import secrets
import time
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django_otp.oath import TOTP

from . import recovery
from .models import RecoveryCode, TotpDevice, User

STEP_SECONDS = 30
DIGITS = 6
TOLERANCE = 1  # steps accepted either side of the current one
_SECRET_BYTES = 20
# Shown by authenticator apps beside the account.
ISSUER = "Weft"


def _fernet() -> Fernet:
    return Fernet(settings.TOTP_ENCRYPTION_KEY)


def device_key(device: TotpDevice) -> bytes:
    return _fernet().decrypt(device.secret_encrypted.encode())


def normalise_code(code: str) -> str:
    return code.replace(" ", "").replace("-", "")


def _accepted_step(device: TotpDevice, code: str) -> int | None:
    """The time step the code is valid for, or None.

    Steps at or before the device's last accepted step never match.
    """
    code = normalise_code(code)
    if len(code) != DIGITS or not (code.isascii() and code.isdigit()):
        return None
    totp = TOTP(device_key(device), step=STEP_SECONDS, digits=DIGITS)
    totp.time = time.time()
    min_t = None if device.last_step is None else device.last_step + 1
    if not totp.verify(int(code), tolerance=TOLERANCE, min_t=min_t):
        return None
    return totp.t()


def _accept(user: User, code: str, *, confirmed: bool) -> TotpDevice | None:
    """Check the code against the user's device and burn its time step.

    The row is locked, so two requests carrying the same code cannot both win.
    Must run inside a transaction.
    """
    device = (
        TotpDevice.objects.select_for_update()
        .filter(user=user, confirmed=confirmed)
        .first()
    )
    if device is None:
        return None
    step = _accepted_step(device, code)
    if step is None:
        return None
    device.last_step = step
    device.save(update_fields=["last_step"])
    return device


def begin_enrolment(user: User) -> tuple[str, str]:
    """Create a pending device; returns (base32 secret, otpauth URI)."""
    key = secrets.token_bytes(_SECRET_BYTES)
    with transaction.atomic():
        TotpDevice.objects.filter(user=user, confirmed=False).delete()
        TotpDevice.objects.create(
            user=user, secret_encrypted=_fernet().encrypt(key).decode()
        )
    secret = base64.b32encode(key).decode()
    label = quote(f"{ISSUER}:{user.email}")
    query = urlencode(
        {
            "secret": secret,
            "issuer": ISSUER,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": STEP_SECONDS,
        }
    )
    return secret, f"otpauth://totp/{label}?{query}"


def confirm_enrolment(user: User, code: str) -> bool:
    """Confirm the pending device, replacing any previously confirmed one."""
    with transaction.atomic():
        device = _accept(user, code, confirmed=False)
        if device is None:
            return False
        TotpDevice.objects.filter(user=user, confirmed=True).delete()
        device.confirmed = True
        device.save(update_fields=["confirmed"])
    return True


def confirm_with_recovery_codes(user: User, code: str) -> list[str] | None:
    """Confirm the pending device and issue its recovery codes, as one step.

    None if the code is wrong. A device is never left confirmed without codes.
    """
    with transaction.atomic():
        if not confirm_enrolment(user, code):
            return None
        return recovery.generate(user)


def verify(user: User, code: str) -> bool:
    with transaction.atomic():
        return _accept(user, code, confirmed=True) is not None


def has_confirmed_device(user: User) -> bool:
    return TotpDevice.objects.filter(user=user, confirmed=True).exists()


def clear(user: User) -> None:
    TotpDevice.objects.filter(user=user).delete()
    RecoveryCode.objects.filter(user=user).delete()
