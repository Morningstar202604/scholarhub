"""TOTP two-factor authentication helpers (RFC 6238 via pyotp).

Design notes:

- The TOTP secret is stored in plaintext on the User row — this is
  inherent to TOTP (the server must compute the same HMAC the phone
  does), and standard practice (GitHub/GitLab do the same). Defense
  is at the DB layer (RLS + access control), not encryption at rest
  of this one column.

- Recovery codes are high-entropy random strings, so a fast SHA-256
  digest is sufficient (bcrypt is for low-entropy human passwords).
  Codes are single-use: verifying one removes it from the stored list.

- Two-step login: when a 2FA-enabled user passes the password check,
  the server does NOT issue access/refresh tokens. It returns a
  short-lived signed "2fa_pending" JWT instead; the client exchanges
  it plus a TOTP (or recovery) code at ``/auth/login/2fa``. The
  pending token carries ``token_version`` so a password change or
  logout-everywhere invalidates it like any other token.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
import pyotp
from jwt import PyJWTError

from app.core.config import settings

TWO_FACTOR_PENDING_TOKEN_TYPE: Literal["2fa_pending"] = "2fa_pending"
# Exchange window: long enough to fish the phone out of a pocket,
# short enough that an intercepted pending token is near-useless.
PENDING_TOKEN_TTL_MINUTES = 5
RECOVERY_CODE_COUNT = 8

ISSUER = "ScholarHUB"


def generate_totp_secret() -> str:
    """Fresh base32 secret for the authenticator app."""
    return pyotp.random_base32()


def build_otpauth_uri(secret: str, account_name: str) -> str:
    """otpauth:// URI the frontend renders as a QR code."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=ISSUER)


def verify_totp_code(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code.

    ``valid_window=1`` accepts the previous/next 30s step to absorb
    clock skew between server and phone.
    """
    if not code or not code.strip():
        return False
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


def generate_recovery_codes() -> list[str]:
    """Human-typable single-use recovery codes, e.g. ``a3f9-c27e-b810``."""
    codes: list[str] = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(6)  # 48 bits entropy
        codes.append(f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}")
    return codes


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode("utf-8")).hexdigest()


def consume_recovery_code(stored_hashes: list[str], code: str) -> list[str] | None:
    """If ``code`` matches a stored hash, return the list WITHOUT it
    (single use). Return ``None`` when the code doesn't match."""
    digest = hash_recovery_code(code)
    if digest not in stored_hashes:
        return None
    return [h for h in stored_hashes if h != digest]


def create_two_factor_pending_token(user_id: int, token_version: int) -> str:
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "token_version": token_version,
        "type": TWO_FACTOR_PENDING_TOKEN_TYPE,
        "exp": datetime.now(UTC) + timedelta(minutes=PENDING_TOKEN_TTL_MINUTES),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_two_factor_pending_token(token: str) -> dict[str, Any] | None:
    """Decode + type-check a pending token; ``None`` on any failure."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except PyJWTError:
        return None
    if payload.get("type") != TWO_FACTOR_PENDING_TOKEN_TYPE:
        return None
    return payload
