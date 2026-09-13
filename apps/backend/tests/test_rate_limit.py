"""Rate limit middleware tests.

The middleware is disabled in test env via ``settings.is_test``. We test
the core logic directly against a middleware instance wrapping a stub
ASGI app, without booting the real FastAPI stack.
"""

from __future__ import annotations

import os

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import Receive, Scope, Send

os.environ.setdefault("SCHOLARHUB_ENVIRONMENT", "test")
os.environ.setdefault("SCHOLARHUB_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.core import config as config_module
from app.middleware.rate_limit import RateLimitMiddleware


async def _stub_app(scope: Scope, receive: Receive, send: Send) -> None:
    """Minimal ASGI app that always returns 200 OK."""
    response: Response = JSONResponse({"ok": True})
    await response(scope, receive, send)


def _make_request(
    path: str,
    method: str = "POST",
    client_host: str = "1.2.3.4",
    body: bytes | None = None,
    content_type: str | None = None,
) -> Request:
    """Build a Starlette Request with a fake client + path."""
    headers: list[tuple[bytes, bytes]] = []
    if content_type is not None:
        headers.append((b"content-type", content_type.encode()))
    if body is not None:
        headers.append((b"content-length", str(len(body)).encode()))
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": (client_host, 12345),
        "scheme": "http",
        "server": ("test", 80),
        "root_path": "",
        "app": None,
    }
    request = Request(scope)
    if body is not None:
        request._body = body
    return request


@pytest.fixture
def rate_limiter_with_strict_env(monkeypatch):
    """Build a fresh middleware with rate limiting enabled (is_test=False)."""
    monkeypatch.setattr(type(config_module.settings), "is_test", property(lambda self: False))
    mw = RateLimitMiddleware(_stub_app, default_per_minute=120)
    yield mw
    monkeypatch.setattr(
        type(config_module.settings),
        "is_test",
        property(lambda self: self.environment == "test"),
    )


@pytest.mark.asyncio
async def test_blocks_after_threshold(rate_limiter_with_strict_env) -> None:
    """After exceeding the strict limit, dispatch returns 429."""
    mw = rate_limiter_with_strict_env
    # login limit is 10/min
    for i in range(10):
        resp = await mw.dispatch(_make_request("/api/auth/login"), lambda req: _ok())
        assert resp.status_code == 200, f"req {i} blocked early"
    blocked = await mw.dispatch(_make_request("/api/auth/login"), lambda req: _ok())
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


@pytest.mark.asyncio
async def test_global_limit_uses_default(rate_limiter_with_strict_env) -> None:
    """Non-strict paths use the default per-minute limit."""
    mw = rate_limiter_with_strict_env
    # default is 120 — 5 requests should all pass
    for _ in range(5):
        resp = await mw.dispatch(_make_request("/api/health", method="GET"), lambda req: _ok())
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_options_bypasses(rate_limiter_with_strict_env) -> None:
    """OPTIONS requests (CORS preflight) are not counted."""
    mw = rate_limiter_with_strict_env
    for _ in range(30):
        resp = await mw.dispatch(
            _make_request("/api/auth/login", method="OPTIONS"), lambda req: _ok()
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_test_env_skipped(client) -> None:
    """In test env, the real app skips rate limiting entirely."""
    for _ in range(15):
        r = await client.post(
            "/api/auth/login",
            json={"username": "x", "password": "wrongpass"},
        )
        assert r.status_code in (401, 422)


@pytest.mark.asyncio
async def test_account_keyed_blocks_distributed_ip_brute_force(
    rate_limiter_with_strict_env,
) -> None:
    """Even from distinct IPs, 6 attempts against the same username get 429.

    This verifies the account-keyed bucket: the IP buckets all have room
    (one hit each) but the username bucket exceeds its 5/min cap.
    """
    mw = rate_limiter_with_strict_env
    # Each request comes from a different IP so the IP bucket never
    # accumulates more than 1 hit per bucket.
    login_body = b'{"username": "victim", "password": "x"}'
    for i in range(5):
        req = _make_request(
            "/api/auth/login",
            client_host=f"10.0.0.{i}",
            body=login_body,
            content_type="application/json",
        )
        resp = await mw.dispatch(req, lambda r: _ok())
        assert resp.status_code == 200, f"attempt {i} blocked early"
    # 6th attempt: account bucket is full → 429.
    req = _make_request(
        "/api/auth/login",
        client_host="10.0.0.99",
        body=login_body,
        content_type="application/json",
    )
    resp = await mw.dispatch(req, lambda r: _ok())
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


@pytest.mark.asyncio
async def test_account_keyed_different_user_not_affected(
    rate_limiter_with_strict_env,
) -> None:
    """Exhausting the account bucket for user A does not block user B."""
    mw = rate_limiter_with_strict_env
    body_a = b'{"username": "user_a", "password": "x"}'
    body_b = b'{"username": "user_b", "password": "x"}'
    for i in range(6):
        req = _make_request(
            "/api/auth/login",
            client_host=f"10.1.0.{i}",
            body=body_a,
            content_type="application/json",
        )
        await mw.dispatch(req, lambda r: _ok())
    # user_b from the same IP range is unaffected.
    req = _make_request(
        "/api/auth/login",
        client_host="10.1.0.99",
        body=body_b,
        content_type="application/json",
    )
    resp = await mw.dispatch(req, lambda r: _ok())
    assert resp.status_code == 200


async def _ok() -> Response:
    return JSONResponse({"ok": True})
