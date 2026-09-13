"""TOTP (RFC 6238) helpers for the M2 hardening milestone.

The HOTP core comes from ``pyotp`` (already a dependency — the old
"deny list" rationale was wrong: pyotp has no transitive deps). The
project-specific parts are kept: 160-bit secrets, replay protection
via the last-used counter, T-1 clock-skew tolerance, Fernet at-rest
encryption of the secret, and single-use hashed backup codes.

Design choices:

- Secrets are 160 bits of CSPRNG output, base32-encoded without
  padding (RFC 4226 section 4 recommended parameters).
- The HOTP counter is the number of 30-second windows since the Unix
  epoch. Replay protection comes from tracking the last successfully
  verified counter in the user record (a code within the current or
  previous window is accepted at most once).
- Constant-time comparison via ``hmac.compare_digest`` so timing side
  channels cannot leak which digit was wrong.
- Drift tolerance: the previous window (T-1) is accepted when the
  current window fails. T+1 is NOT accepted — a code from a
  slightly-future client clock must not be usable.

Encryption-at-rest: the cleartext secret is encrypted with Fernet
before being persisted to ``User.totp_secret_encrypted``. The
encryption/decryption boundary lives here, not in the route, so
every code path that touches the secret is funneled through one
place.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Final

import pyotp
from cryptography.fernet import Fernet, InvalidToken

# RFC 4226 section 4: 160-bit secret, 6-digit code, SHA-1 HMAC.
_TOTP_DIGITS: Final = 6
_TOTP_PERIOD: Final = 30
_TOTP_WINDOW: Final = 1  # accept T-1 in addition to T for clock skew
_BACKUP_CODE_COUNT: Final = 10
_BACKUP_CODE_LENGTH: Final = 10  # 10 chars, base32 alphabet


def generate_secret() -> str:
    """Return a 20-byte base32 secret (no padding) for a new user."""
    return pyotp.random_base32()


def _hotp(secret_b32: str, counter: int) -> str:
    """HOTP per RFC 4226 (implemented by pyotp), zero-padded 6 digits."""
    return pyotp.HOTP(secret_b32).at(counter).zfill(_TOTP_DIGITS)


def verify_totp(secret_b32: str, code: str, last_counter: int = -1) -> int | None:
    """Verify a 6-digit TOTP code against a secret.

    Returns the counter value that successfully verified (for replay
    protection) or ``None`` if the code is invalid. ``last_counter``
    is the highest counter we have already accepted for this user;
    any counter <= ``last_counter`` is rejected.
    """
    if not code or len(code) != _TOTP_DIGITS or not code.isdigit():
        return None
    current = int(time.time()) // _TOTP_PERIOD
    for delta in range(_TOTP_WINDOW + 1):
        candidate = current - delta
        if candidate <= last_counter:
            continue
        expected = _hotp(secret_b32, candidate)
        if hmac.compare_digest(expected, code):
            return candidate
    return None


# --- Backup codes ----------------------------------------------------------

_BACKUP_ALPHABET: Final = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # Crockford-ish


def generate_backup_codes() -> list[str]:
    """Return ``_BACKUP_CODE_COUNT`` single-use backup codes.

    Uses a 31-char unambiguous alphabet so users transcribe them
    reliably. Each code is shown to the user ONCE at enrollment /
    regeneration and is never stored in cleartext on the server.
    """
    codes: list[str] = []
    for _ in range(_BACKUP_CODE_COUNT):
        n = secrets.randbelow(len(_BACKUP_ALPHABET) ** _BACKUP_CODE_LENGTH)
        chars: list[str] = []
        for _ in range(_BACKUP_CODE_LENGTH):
            n, r = divmod(n, len(_BACKUP_ALPHABET))
            chars.append(_BACKUP_ALPHABET[r])
        # Group as XXXXX-XXXXX so users don't misread it.
        code = "".join(chars)
        codes.append(f"{code[:5]}-{code[5:]}")
    return codes


def hash_backup_code(code: str) -> str:
    """SHA-256 the normalized backup code.

    Backup codes have low entropy (~52 bits for 10 chars from a 31-char
    alphabet) and are one-shot, so SHA-256 with a constant prefix is
    fine. We do NOT use bcrypt here because (a) it would slow every
    verify noticeably, and (b) the threat model for a backup code is
    DB exfiltration, not online guessing.
    """
    normalized = code.replace("-", "").strip().upper()
    return hashlib.sha256(b"scholarhub:backup:" + normalized.encode("ascii")).hexdigest()


def normalize_backup_code(code: str) -> str:
    """Normalize a user-entered backup code for hashing/lookup."""
    return code.replace("-", "").strip().upper()


# --- Fernet at-rest encryption --------------------------------------------


def _fernet() -> Fernet:
    """Build a Fernet instance from the active settings.

    Imports ``settings`` lazily so that test conftest can mutate the
    key before any encryption happens.
    """
    from app.core.config import settings

    return Fernet(settings.fernet_key.encode("utf-8"))


def encrypt_secret(secret_b32: str) -> str:
    """Encrypt a TOTP secret for at-rest storage."""
    return _fernet().encrypt(secret_b32.encode("ascii")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Decrypt a TOTP secret read from storage.

    Raises ``ValueError`` if the token is undecryptable (e.g. the key
    was rotated and the row was encrypted with the previous key). The
    caller should treat this as a recoverable per-user error, not a
    500 - it just means this particular user needs to re-enroll 2FA.
    """
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("ascii")
    except InvalidToken as exc:
        raise ValueError("TOTP secret cannot be decrypted with the current key") from exc


def otpauth_uri(secret_b32: str, account: str, issuer: str) -> str:
    """Build an otpauth:// URI for QR code generation on the client side.

    The user scans this with Google Authenticator / 1Password / etc.
    """
    from urllib.parse import quote

    label = quote(f"{issuer}:{account}", safe="")
    params = (
        f"secret={quote(secret_b32, safe='')}"
        f"&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1"
        f"&digits={_TOTP_DIGITS}"
        f"&period={_TOTP_PERIOD}"
    )
    return f"otpauth://totp/{label}?{params}"


__all__ = [
    "decrypt_secret",
    "encrypt_secret",
    "generate_backup_codes",
    "generate_secret",
    "hash_backup_code",
    "normalize_backup_code",
    "otpauth_uri",
    "verify_totp",
]
