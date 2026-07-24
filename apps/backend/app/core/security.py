"""Password hashing + JWT issuing/decoding.

Tokens carry ``sub`` (user id) and ``token_version``. The user table stores
``token_version``; bumping it on logout/password change invalidates every
previously-issued token without a denylist.

Refresh tokens additionally carry ``rtv`` (refresh_token_version) — a
counter independent from ``token_version``. Each ``/auth/refresh`` call
bumps it on the User row, so the consumed refresh token (and any older
ones) become invalid the next time they are presented. This is OAuth2-
standard refresh token rotation; access tokens and the user's other
devices are NOT affected.

Signing key rotation (M3 hardening): JWT signing + verification lives
in ``app.core.key_rotation``. ``encode_jwt`` always signs with the
*current* key (``settings.secret_key``); ``decode_jwt`` tries the
current key then every entry in ``settings.previous_secret_keys``.
Operators rotate by setting a new ``SCHOLARHUB_SECRET_KEY`` and the
old one in ``SCHOLARHUB_PREVIOUS_SECRET_KEYS`` (comma-separated,
newest first) and then calling ``POST /api/admin/security/reload``
or ``app.core.key_rotation.reload_settings()``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict

import bcrypt

from app.core.key_rotation import decode_jwt, encode_jwt


class TokenClaims(TypedDict):
    sub: str
    token_version: int
    type: Literal["access", "refresh"]
    exp: datetime


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))


def _create_token(data: dict[str, Any], expires_delta: timedelta, token_type: Literal["access", "refresh"]) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + expires_delta
    to_encode.update({"exp": expire, "type": token_type})
    return encode_jwt(to_encode)


def create_access_token(data: dict[str, Any]) -> str:
    return _create_token(
        data,
        timedelta(minutes=_get_access_token_expire_minutes()),
        "access",
    )


def create_refresh_token(data: dict[str, Any]) -> str:
    return _create_token(
        data,
        timedelta(days=_get_refresh_token_expire_days()),
        "refresh",
    )


def _get_access_token_expire_minutes() -> int:
    """Read access-token TTL from settings at call time (so a hot reload
    picks up the new TTL without restarting the process)."""
    from app.core.config import get_settings

    return get_settings().access_token_expire_minutes


def _get_refresh_token_expire_days() -> int:
    """Read refresh-token TTL from settings at call time."""
    from app.core.config import get_settings

    return get_settings().refresh_token_expire_days


# Short-lived (5 min) JWT that proves the holder has just completed the
# password step of /auth/login for a 2FA-enabled account. The token carries
# only ``sub`` (user id) and ``type: 2fa_pending``; it carries no scopes
# and is rejected by every other endpoint that needs auth.
_2FA_PENDING_TTL_MINUTES = 5


def create_2fa_pending_token(user_id: int) -> str:
    """Issue a short-lived token proving password step is done.

    Used by the login flow when the account has 2FA enabled. The token
    is consumed once by ``POST /auth/2fa/authenticate`` and is not a
    bearer token for any other endpoint.
    """
    return _create_token(
        {"sub": str(user_id)},
        timedelta(minutes=_2FA_PENDING_TTL_MINUTES),
        "2fa_pending",
    )


def decode_2fa_pending_token(token: str) -> int | None:
    """Return the user id from a 2fa_pending token, or None on any error.

    We deliberately return None on every failure mode (expired,
    malformed, wrong type, signature mismatch) so the caller can
    surface a single generic 'verification failed' error to the
    client without leaking which check failed.
    """
    payload = decode_jwt(token, expected_type="2fa_pending")
    if payload is None:
        return None
    sub = payload.get("sub")
    try:
        return int(sub)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def token_version_matches(payload: dict[str, Any] | None, expected_version: int) -> bool:
    """Return True if the access-token payload carries the expected ``token_version``."""
    if payload is None:
        return False
    return payload.get("token_version") == expected_version


def refresh_token_version_matches(payload: dict[str, Any] | None, expected_version: int) -> bool:
    """Return True if the refresh-token payload carries the expected ``rtv``.

    ``rtv`` (refresh_token_version) is independent from ``token_version``
    so refresh rotation does not invalidate outstanding access tokens.
    """
    if payload is None:
        return False
    return payload.get("rtv") == expected_version


def decode_token(token: str, expected_type: Literal["access", "refresh"] | None = None) -> dict[str, Any] | None:
    return decode_jwt(token, expected_type=expected_type)


def decode_access_token(token: str) -> dict[str, Any] | None:
    return decode_token(token, expected_type="access")


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    return decode_token(token, expected_type="refresh")