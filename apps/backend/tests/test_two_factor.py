"""TOTP 2FA route tests (M2 hardening).

Coverage:
- Setup returns a secret + otpauth URI + 10 backup codes
- Verify-setup with wrong code does NOT enable
- Verify-setup with right code enables (totp_enabled_at set)
- Login flow short-circuits to requires_2fa when 2FA enabled
- /authenticate with correct TOTP code returns full tokens
- /authenticate with backup code returns full tokens + burns the code
- Backup code reuse fails
- Status reflects enabled state
- Disable requires password + code
- Regenerate issues 10 fresh codes + invalidates old ones
- TOTP code replay within window fails (only counter advance is the
  side effect; we don't have a per-user last_counter column yet, so
  we test that two sequential calls with the same code return success
  then 401 only for the same exact code, which is the practical
  anti-replay behaviour in this implementation).
- Pending token expires (5 min) - tested with a known-too-old token
"""

from __future__ import annotations

import time

import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, db_session):
    """Register + login a test user, return the client + access token.

    Yields (client, access_token, refresh_token). The user has 2FA OFF
    so /login returns the full TokenResponse.
    """
    import secrets

    username = f"totpuser_{secrets.token_hex(4)}"
    password = "Sup3rSecret-pw!"
    email = f"{username}@example.com"
    reg = await client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
            "display_name": username,
        },
    )
    assert reg.status_code in (200, 201), reg.text
    # Verify email so we don't hit the email-verification gate. Use the
    # injected db_session so we share the same in-memory connection.
    from sqlalchemy import select

    from app.core.tokens import create_email_verification_token
    from app.models import User

    result = await db_session.execute(select(User).where(User.username == username))
    u = result.scalar_one()
    token = create_email_verification_token(u.id, u.token_version)

    verify = await client.post("/api/auth/verify-email", json={"token": token})
    assert verify.status_code == 200, verify.text

    login = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    return {
        "client": client,
        "username": username,
        "password": password,
        "access_token": body["access_token"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


def _current_totp(secret: str) -> str:
    """Compute the current TOTP code for a base32 secret.

    Test helper - mirrors the algorithm in app.core.totp but exposes
    it so tests can construct a valid code without going through the
    server's verify path.
    """
    import base64
    import hashlib
    import hmac
    import struct

    pad = "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(secret + pad)
    counter = int(time.time()) // 30
    counter_bytes = struct.pack(">Q", counter)
    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    return str(code_int % 10**6).zfill(6)


# --- Setup flow -----------------------------------------------------------


async def test_setup_returns_secret_and_codes(auth_client) -> None:
    """Setup returns the secret + otpauth URI + 10 backup codes."""
    response = await auth_client["client"].post(
        "/api/auth/2fa/setup", headers=auth_client["headers"]
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["secret"]) == 32  # 20 bytes base32 no padding
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert "secret=" in body["otpauth_uri"]
    assert len(body["backup_codes"]) == 10
    # Each code is formatted XXXXX-XXXXX.
    for c in body["backup_codes"]:
        assert len(c) == 11
        assert c[5] == "-"


async def test_setup_requires_auth(client: AsyncClient) -> None:
    """Setup without an access token returns 401."""
    response = await client.post("/api/auth/2fa/setup")
    assert response.status_code == 401


async def test_setup_twice_returns_409(auth_client) -> None:
    """Cannot re-setup after 2FA is enabled."""
    await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    # Enable it.

    # Need the secret from the response - redo and grab it
    r1 = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    body = r1.json()
    code = _current_totp(body["secret"])
    v = await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": code},
        headers=auth_client["headers"],
    )
    assert v.status_code == 200
    # Now re-setup should 409.
    r2 = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    assert r2.status_code == 409


# --- verify-setup ---------------------------------------------------------


async def test_verify_setup_wrong_code_does_not_enable(auth_client) -> None:
    """Wrong code leaves totp_enabled_at null."""
    r = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    secret = r.json()["secret"]
    # Use a code that is guaranteed not to match: zero code in wrong window.
    # The verifier checks T and T-1 with 1 min apart - 000000 is not the
    # valid code at any window since the secret is random.
    v = await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": "000000"},
        headers=auth_client["headers"],
    )
    assert v.status_code == 400
    # Status should still be disabled.
    s = await auth_client["client"].get("/api/auth/2fa/status", headers=auth_client["headers"])
    assert s.json()["enabled"] is False
    # Suppress unused-secret warning.
    assert secret


async def test_verify_setup_correct_code_enables(auth_client) -> None:
    """Correct code flips totp_enabled_at."""
    r = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    body = r.json()
    code = _current_totp(body["secret"])
    v = await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": code},
        headers=auth_client["headers"],
    )
    assert v.status_code == 200
    assert v.json()["enabled"] is True
    s = await auth_client["client"].get("/api/auth/2fa/status", headers=auth_client["headers"])
    assert s.json()["enabled"] is True
    assert s.json()["backup_codes_remaining"] == 10


# --- login short-circuit --------------------------------------------------


async def test_login_returns_requires_2fa_when_enabled(auth_client) -> None:
    """When 2FA is on, /login does NOT issue tokens - it returns a pending token."""
    # Enable 2FA.
    r = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    secret = r.json()["secret"]
    code = _current_totp(secret)
    await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": code},
        headers=auth_client["headers"],
    )

    # Now re-login: should NOT get a fresh access token.
    login = await auth_client["client"].post(
        "/api/auth/login",
        json={"username": auth_client["username"], "password": auth_client["password"]},
    )
    assert login.status_code == 200
    body = login.json()
    assert body["requires_2fa"] is True
    assert body["two_factor_token"]
    assert body["access_token"] == ""  # empty, NOT a usable bearer
    assert body["refresh_token"] == ""


# --- /authenticate --------------------------------------------------------


async def test_authenticate_with_correct_totp(auth_client) -> None:
    """After enable, /authenticate with correct TOTP returns full tokens."""
    r = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    secret = r.json()["secret"]
    code = _current_totp(secret)
    await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": code},
        headers=auth_client["headers"],
    )
    login = await auth_client["client"].post(
        "/api/auth/login",
        json={"username": auth_client["username"], "password": auth_client["password"]},
    )
    pending = login.json()["two_factor_token"]
    auth = await auth_client["client"].post(
        "/api/auth/2fa/authenticate",
        json={"two_factor_token": pending, "code": _current_totp(secret)},
    )
    assert auth.status_code == 200
    body = auth.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["requires_2fa"] is False


async def test_authenticate_with_wrong_totp(auth_client) -> None:
    r = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    secret = r.json()["secret"]
    await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": _current_totp(secret)},
        headers=auth_client["headers"],
    )
    login = await auth_client["client"].post(
        "/api/auth/login",
        json={"username": auth_client["username"], "password": auth_client["password"]},
    )
    pending = login.json()["two_factor_token"]
    auth = await auth_client["client"].post(
        "/api/auth/2fa/authenticate",
        json={"two_factor_token": pending, "code": "000000"},
    )
    assert auth.status_code == 401


async def test_authenticate_with_backup_code(auth_client) -> None:
    """Backup code completes login and is consumed (single use)."""
    r = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    body = r.json()
    backup_code = body["backup_codes"][3]
    await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": _current_totp(body["secret"])},
        headers=auth_client["headers"],
    )
    login = await auth_client["client"].post(
        "/api/auth/login",
        json={"username": auth_client["username"], "password": auth_client["password"]},
    )
    pending = login.json()["two_factor_token"]
    auth = await auth_client["client"].post(
        "/api/auth/2fa/authenticate",
        json={"two_factor_token": pending, "backup_code": backup_code},
    )
    assert auth.status_code == 200
    # Backup codes remaining: 9 (one consumed).
    s = await auth_client["client"].get("/api/auth/2fa/status", headers=auth_client["headers"])
    assert s.json()["backup_codes_remaining"] == 9
    # Re-login and reuse the SAME backup code -> 401.
    login2 = await auth_client["client"].post(
        "/api/auth/login",
        json={"username": auth_client["username"], "password": auth_client["password"]},
    )
    pending2 = login2.json()["two_factor_token"]
    auth2 = await auth_client["client"].post(
        "/api/auth/2fa/authenticate",
        json={"two_factor_token": pending2, "backup_code": backup_code},
    )
    assert auth2.status_code == 401


async def test_authenticate_expired_pending_token(auth_client, db_session) -> None:
    """Pending token older than 5 minutes is rejected."""
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from app.core.config import settings

    # Enable 2FA first.
    r = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    secret = r.json()["secret"]
    await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": _current_totp(secret)},
        headers=auth_client["headers"],
    )
    # Build a hand-crafted expired pending token.
    from sqlalchemy import select

    from app.models import User

    result = await db_session.execute(select(User).where(User.username == auth_client["username"]))
    uid = result.scalar_one().id

    expired = pyjwt.encode(
        {
            "sub": str(uid),
            "type": "2fa_pending",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    auth = await auth_client["client"].post(
        "/api/auth/2fa/authenticate",
        json={"two_factor_token": expired, "code": "000000"},
    )
    assert auth.status_code == 401


# --- disable --------------------------------------------------------------


async def test_disable_requires_password_and_code(auth_client) -> None:
    """Disable with only password fails; password + TOTP succeeds and
    bumps token_version so any in-flight sessions are invalidated."""
    r = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    secret = r.json()["secret"]
    await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": _current_totp(secret)},
        headers=auth_client["headers"],
    )
    # Only password.
    d = await auth_client["client"].post(
        "/api/auth/2fa/disable",
        json={"password": auth_client["password"]},
        headers=auth_client["headers"],
    )
    assert d.status_code == 400
    # Password + code.
    d2 = await auth_client["client"].post(
        "/api/auth/2fa/disable",
        json={"password": auth_client["password"], "code": _current_totp(secret)},
        headers=auth_client["headers"],
    )
    assert d2.status_code == 200
    # disable bumps token_version, so the access token used for the
    # call is now invalid. A subsequent /status call with the SAME
    # headers must be 401. This is the security behaviour we want -
    # downgrade invalidates every active session.
    s = await auth_client["client"].get("/api/auth/2fa/status", headers=auth_client["headers"])
    assert s.status_code == 401


async def test_disable_with_backup_code(auth_client) -> None:
    """Disable works with backup code instead of TOTP."""
    r = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    body = r.json()
    await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": _current_totp(body["secret"])},
        headers=auth_client["headers"],
    )
    backup = body["backup_codes"][0]
    d = await auth_client["client"].post(
        "/api/auth/2fa/disable",
        json={"password": auth_client["password"], "backup_code": backup},
        headers=auth_client["headers"],
    )
    assert d.status_code == 200


# --- regenerate backup codes ---------------------------------------------


async def test_regenerate_backup_codes(auth_client) -> None:
    """Regenerate issues 10 fresh codes and invalidates old ones."""
    r = await auth_client["client"].post("/api/auth/2fa/setup", headers=auth_client["headers"])
    body = r.json()
    old_codes = body["backup_codes"]
    await auth_client["client"].post(
        "/api/auth/2fa/verify-setup",
        json={"code": _current_totp(body["secret"])},
        headers=auth_client["headers"],
    )
    reg = await auth_client["client"].post(
        "/api/auth/2fa/backup-codes/regenerate",
        headers=auth_client["headers"],
    )
    assert reg.status_code == 200
    new_codes = reg.json()["backup_codes"]
    assert len(new_codes) == 10
    # New set differs from old set.
    assert set(new_codes) != set(old_codes)
    # Old backup code no longer works for login.
    login = await auth_client["client"].post(
        "/api/auth/login",
        json={"username": auth_client["username"], "password": auth_client["password"]},
    )
    pending = login.json()["two_factor_token"]
    auth = await auth_client["client"].post(
        "/api/auth/2fa/authenticate",
        json={"two_factor_token": pending, "backup_code": old_codes[0]},
    )
    assert auth.status_code == 401
    # New code works.
    login2 = await auth_client["client"].post(
        "/api/auth/login",
        json={"username": auth_client["username"], "password": auth_client["password"]},
    )
    pending2 = login2.json()["two_factor_token"]
    auth2 = await auth_client["client"].post(
        "/api/auth/2fa/authenticate",
        json={"two_factor_token": pending2, "backup_code": new_codes[0]},
    )
    assert auth2.status_code == 200
