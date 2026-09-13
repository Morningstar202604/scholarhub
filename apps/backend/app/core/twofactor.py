"""Short-lived "2FA pending" session tokens for the two-step login.

When a 2FA-enabled user passes the password check, the server does NOT
issue access/refresh tokens. It returns a short-lived signed
"2fa_pending" JWT; the client exchanges it plus a TOTP (or backup)
code at ``/auth/login/2fa`` (which now verifies via the Fernet-
encrypted M2 secret, see ``app.core.totp``).

The pending token carries ``token_version`` so a password change or
logout-everywhere invalidates it like any other token.

TOTP setup/management lives in the M2 stack: ``/api/auth/2fa/*``
(``app.api.two_factor``) with secrets encrypted at rest via
``app.core.totp``. This file only owns the pending-token ceremony.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from jwt import PyJWTError

from app.core.config import settings

TWO_FACTOR_PENDING_TOKEN_TYPE: Literal["2fa_pending"] = "2fa_pending"
# Exchange window: long enough to fish the phone out of a pocket,
# short enough that an intercepted pending token is near-useless.
PENDING_TOKEN_TTL_MINUTES = 5


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


__all__ = [
    "PENDING_TOKEN_TTL_MINUTES",
    "TWO_FACTOR_PENDING_TOKEN_TYPE",
    "create_two_factor_pending_token",
    "decode_two_factor_pending_token",
]
