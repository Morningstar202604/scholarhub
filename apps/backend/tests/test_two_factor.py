"""Integration tests for TOTP two-factor authentication (M2 stack).

Covers the full enrolment + login chain and the ways it can be abused:

- setup issues a Fernet-encrypted secret + 10 backup codes but does NOT
  activate 2FA;
- verify-setup requires a genuine code to flip the switch;
- once enabled, /auth/login stops handing out tokens;
- the pending token is short-lived, type-checked, and tied to
  token_version (password change kills it);
- backup codes work exactly once;
- disabling requires the account password + a fresh code.

The 2FA self-management surface is ``/api/auth/2fa/*`` (M2); the login
ceremony stays ``/auth/login`` → ``/auth/login/2fa``.
"""

from __future__ import annotations

import pyotp
from conftest import auth_headers
from httpx import AsyncClient

from app.core.twofactor import (
    create_two_factor_pending_token,
    decode_two_factor_pending_token,
)


def _code(secret: str) -> str:
    return pyotp.TOTP(secret).now()


async def _setup(client: AsyncClient, user: dict) -> tuple[str, list[str]]:
    """Run setup; returns (secret, backup_codes). 2FA is still OFF."""
    resp = await client.post("/api/auth/2fa/setup", headers=auth_headers(user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    return body["secret"], body["backup_codes"]


async def _enable(client: AsyncClient, user: dict) -> tuple[str, list[str]]:
    """Full enrolment; returns (secret, backup_codes)."""
    secret, backup_codes = await _setup(client, user)
    resp = await client.post(
        "/api/auth/2fa/verify-setup",
        json={"code": _code(secret)},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    return secret, backup_codes


# ---------------------------------------------------------------------------
# Enrolment
# ---------------------------------------------------------------------------


async def test_status_is_disabled_by_default(client: AsyncClient, test_user: dict) -> None:
    """2FA 是 opt-in：新账号默认关闭，且没有备用码。"""
    resp = await client.get("/api/auth/2fa/status", headers=auth_headers(test_user))
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False, "backup_codes_remaining": 0}


async def test_setup_does_not_activate_two_factor(client: AsyncClient, test_user: dict) -> None:
    """只跑 setup 不算启用——否则用户扫码失败就把自己锁在门外了。"""
    await _setup(client, test_user)

    status_resp = await client.get("/api/auth/2fa/status", headers=auth_headers(test_user))
    assert status_resp.json()["enabled"] is False

    # 登录仍然直接发 token
    login = await client.post(
        "/api/auth/login",
        json={"username": test_user["username"], "password": test_user["password"]},
    )
    assert login.status_code == 200
    assert "access_token" in login.json()


async def test_verify_setup_requires_valid_code(client: AsyncClient, test_user: dict) -> None:
    """错误的验证码不能启用 2FA。"""
    await _setup(client, test_user)
    resp = await client.post(
        "/api/auth/2fa/verify-setup",
        json={"code": "000000"},
        headers=auth_headers(test_user),
    )
    assert resp.status_code == 400
    assert "Invalid TOTP code" in resp.json()["detail"]


async def test_verify_setup_without_setup_is_rejected(client: AsyncClient, test_user: dict) -> None:
    """没跑 setup 就 verify → 400，而不是 500。"""
    resp = await client.post(
        "/api/auth/2fa/verify-setup",
        json={"code": "123456"},
        headers=auth_headers(test_user),
    )
    assert resp.status_code == 400
    assert "setup" in resp.json()["detail"].lower()


async def test_enable_returns_backup_codes_and_flips_status(
    client: AsyncClient, test_user: dict
) -> None:
    """setup 一次性返回 10 个备用码；verify-setup 后状态翻转。"""
    _, codes = await _enable(client, test_user)
    assert len(codes) == 10
    assert all("-" in c for c in codes)
    assert len(set(codes)) == 10  # 不重复

    status_resp = await client.get("/api/auth/2fa/status", headers=auth_headers(test_user))
    assert status_resp.json() == {"enabled": True, "backup_codes_remaining": 10}


async def test_setup_again_after_enabled_is_conflict(client: AsyncClient, test_user: dict) -> None:
    """已启用后再 setup → 409，避免误把现有 secret 冲掉。"""
    await _enable(client, test_user)
    resp = await client.post("/api/auth/2fa/setup", headers=auth_headers(test_user))
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------


async def test_login_returns_pending_token_when_enabled(
    client: AsyncClient, test_user: dict
) -> None:
    """启用后，密码正确也拿不到 access token，只有 pending token。"""
    await _enable(client, test_user)
    resp = await client.post(
        "/api/auth/login",
        json={"username": test_user["username"], "password": test_user["password"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["two_factor_required"] is True
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert body["pending_token"]


async def test_wrong_password_still_401_when_2fa_enabled(
    client: AsyncClient, test_user: dict
) -> None:
    """2FA 不能变成密码错误的遮羞布：密码错依然 401，不发 pending token。"""
    await _enable(client, test_user)
    resp = await client.post(
        "/api/auth/login",
        json={"username": test_user["username"], "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_full_two_factor_login_chain(client: AsyncClient, test_user: dict) -> None:
    """完整链路：密码 → pending token → TOTP → 真正的 access token。"""
    secret, _ = await _enable(client, test_user)

    login = await client.post(
        "/api/auth/login",
        json={"username": test_user["username"], "password": test_user["password"]},
    )
    pending = login.json()["pending_token"]

    resp = await client.post(
        "/api/auth/login/2fa",
        json={"pending_token": pending, "code": _code(secret)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["user_id"] == test_user["user_id"]

    # 换来的 token 真的能用
    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200


async def test_wrong_totp_code_is_rejected(client: AsyncClient, test_user: dict) -> None:
    await _enable(client, test_user)
    login = await client.post(
        "/api/auth/login",
        json={"username": test_user["username"], "password": test_user["password"]},
    )
    resp = await client.post(
        "/api/auth/login/2fa",
        json={"pending_token": login.json()["pending_token"], "code": "000000"},
    )
    assert resp.status_code == 401
    assert "Invalid two-factor code" in resp.json()["detail"]


async def test_garbage_pending_token_is_rejected(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/auth/login/2fa",
        json={"pending_token": "not-a-jwt", "code": "123456"},
    )
    assert resp.status_code == 401


async def test_access_token_cannot_be_used_as_pending_token(
    client: AsyncClient, test_user: dict
) -> None:
    """type 校验：普通 access token 不能冒充 pending token 直接换 token。"""
    secret, _ = await _enable(client, test_user)
    resp = await client.post(
        "/api/auth/login/2fa",
        json={"pending_token": test_user["token"], "code": _code(secret)},
    )
    assert resp.status_code == 401


async def test_pending_token_dies_with_token_version(client: AsyncClient, test_user: dict) -> None:
    """改密后 token_version 变了，之前签发的 pending token 立刻失效。"""
    secret, _ = await _enable(client, test_user)
    login = await client.post(
        "/api/auth/login",
        json={"username": test_user["username"], "password": test_user["password"]},
    )
    pending = login.json()["pending_token"]

    change = await client.post(
        "/api/users/me/password",
        json={"old_password": test_user["password"], "new_password": "newpassword456"},
        headers=auth_headers(test_user),
    )
    assert change.status_code == 204

    resp = await client.post(
        "/api/auth/login/2fa",
        json={"pending_token": pending, "code": _code(secret)},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Backup codes
# ---------------------------------------------------------------------------


async def test_backup_code_works_once(client: AsyncClient, test_user: dict) -> None:
    """备用码可以顶替 TOTP 登录，但只能用一次。"""
    _, codes = await _enable(client, test_user)
    backup = codes[0]

    async def _login_with(code: str) -> int:
        login = await client.post(
            "/api/auth/login",
            json={
                "username": test_user["username"],
                "password": test_user["password"],
            },
        )
        resp = await client.post(
            "/api/auth/login/2fa",
            json={"pending_token": login.json()["pending_token"], "code": code},
        )
        return resp.status_code

    assert await _login_with(backup) == 200
    # 第二次同一个码必须失败
    assert await _login_with(backup) == 401

    status_resp = await client.get("/api/auth/2fa/status", headers=auth_headers(test_user))
    assert status_resp.json()["backup_codes_remaining"] == 9


async def test_backup_code_is_case_insensitive(client: AsyncClient, test_user: dict) -> None:
    """备用码是人手抄的，大小写/空格不该成为障碍。"""
    _, codes = await _enable(client, test_user)
    login = await client.post(
        "/api/auth/login",
        json={"username": test_user["username"], "password": test_user["password"]},
    )
    resp = await client.post(
        "/api/auth/login/2fa",
        json={
            "pending_token": login.json()["pending_token"],
            "code": f"  {codes[0].lower()}  ",
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Disable
# ---------------------------------------------------------------------------


async def test_disable_requires_password(client: AsyncClient, test_user: dict) -> None:
    """被劫持的会话不能光凭 cookie 就把第二因子摘掉。"""
    secret, _ = await _enable(client, test_user)
    resp = await client.post(
        "/api/auth/2fa/disable",
        json={"password": "wrong-password", "code": _code(secret)},
        headers=auth_headers(test_user),
    )
    assert resp.status_code == 401

    status_resp = await client.get("/api/auth/2fa/status", headers=auth_headers(test_user))
    assert status_resp.json()["enabled"] is True


async def test_disable_with_password_restores_plain_login(
    client: AsyncClient, test_user: dict
) -> None:
    """关闭 2FA 后登录回到一步式，且备用码被清空。

    关闭会 bump token_version（M2 语义：使所有在途 token 失效），所以
    状态检查要用重新登录换来的新 token。
    """
    secret, _ = await _enable(client, test_user)
    resp = await client.post(
        "/api/auth/2fa/disable",
        json={"password": test_user["password"], "code": _code(secret)},
        headers=auth_headers(test_user),
    )
    assert resp.status_code == 200, resp.text

    login = await client.post(
        "/api/auth/login",
        json={"username": test_user["username"], "password": test_user["password"]},
    )
    assert "access_token" in login.json()

    status_resp = await client.get(
        "/api/auth/2fa/status",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert status_resp.json() == {"enabled": False, "backup_codes_remaining": 0}


async def test_disable_when_not_enabled_is_400(client: AsyncClient, test_user: dict) -> None:
    resp = await client.post(
        "/api/auth/2fa/disable",
        json={"password": test_user["password"], "code": "123456"},
        headers=auth_headers(test_user),
    )
    assert resp.status_code == 400


async def test_two_factor_endpoints_require_auth(client: AsyncClient) -> None:
    """未登录不能碰任何 2FA 自管理端点。"""
    for method, path, body in (
        ("get", "/api/auth/2fa/status", None),
        ("post", "/api/auth/2fa/setup", None),
        ("post", "/api/auth/2fa/verify-setup", {"code": "123456"}),
        ("post", "/api/auth/2fa/disable", {"password": "whatever"}),
    ):
        resp = (
            await getattr(client, method)(path, json=body)
            if body
            else await getattr(client, method)(path)
        )
        assert resp.status_code == 401, f"{method} {path} → {resp.status_code}"


# ---------------------------------------------------------------------------
# Pending token unit-level guards
# ---------------------------------------------------------------------------


def test_pending_token_roundtrip_carries_claims() -> None:
    token = create_two_factor_pending_token(user_id=42, token_version=7)
    claims = decode_two_factor_pending_token(token)
    assert claims is not None
    assert claims["sub"] == "42"
    assert claims["token_version"] == 7
    assert claims["type"] == "2fa_pending"


def test_decode_rejects_tampered_token() -> None:
    token = create_two_factor_pending_token(user_id=1, token_version=0)
    assert decode_two_factor_pending_token(token + "x") is None
