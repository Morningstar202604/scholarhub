"""Per-IP rate limiting middleware.

Memory-only sliding window: no Redis dependency, suitable for single-node
deployments. For multi-node deployments swap the store for Redis (the
interface is just ``_buckets`` dict access — easy to replace with a
Redis-backed INCR + EXPIRE).

Sensitive auth endpoints get a stricter limit than the global default.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings

# Per-endpoint stricter limits: path -> max requests per minute
STRICT_PATHS: dict[str, int] = {
    # 2FA 码只有 6 位数字：code 交换端点要比 /login 更紧，否则第二因子
    # 会在 pending token 的 5 分钟窗口内被暴力穷举。10 次/分 × 5 分 = 50 次
    # 尝试 vs 100 万组合，风险可接受。
    "/api/auth/login/2fa": 10,
    "/api/auth/login": 10,
    "/api/auth/register": 5,
    "/api/auth/verify-email": 10,
    "/api/auth/resend-verification": 5,
    "/api/auth/forgot-password": 5,
    "/api/auth/reset-password": 10,
    "/api/auth/refresh": 30,
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed by client IP + path."""

    def __init__(self, app: ASGIApp, default_per_minute: int) -> None:
        super().__init__(app)
        self._default = default_per_minute
        # key = (ip, path_prefix) -> list of request timestamps
        self._buckets: dict[tuple[str, str], list[float]] = defaultdict(list)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Test env: skip entirely. Single-IP sliding window would starve
        # the test client which reuses one connection for many requests.
        if settings.is_test or request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        limit = self._limit_for(path)
        if limit <= 0:
            return await call_next(request)

        ip = self._client_ip(request)
        now = time.monotonic()
        bucket_key = (ip, self._path_key(path))
        bucket = self._buckets[bucket_key]
        # Sliding window: drop timestamps older than 60s
        cutoff = now - 60.0
        self._buckets[bucket_key] = [ts for ts in bucket if ts > cutoff]
        bucket = self._buckets[bucket_key]

        if len(bucket) >= limit:
            retry_after = int(60 - (now - bucket[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)
        response = await call_next(request)
        return response

    def _limit_for(self, path: str) -> int:
        for strict_path, limit in STRICT_PATHS.items():
            if path == strict_path:
                return limit
        return self._default

    def _path_key(self, path: str) -> str:
        # Collapse exact strict paths to their key; everything else shares
        # a global bucket so one IP cannot bypass per-path limits by
        # hitting many distinct resource_id URLs.
        for strict_path in STRICT_PATHS:
            if path == strict_path:
                return strict_path
        return "_global"

    def _client_ip(self, request: Request) -> str:
        # Trust X-Forwarded-For only when trusted_proxies_count is set.
        # XFF format: client, proxy1, proxy2... — pick the Nth-from-the-right
        # entry (N = trusted_proxies_count), which is the IP the last trusted
        # proxy actually saw as the client.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded and settings.trusted_proxies_count > 0:
            parts = [p.strip() for p in forwarded.split(",")]
            idx = max(0, len(parts) - settings.trusted_proxies_count)
            return parts[idx]
        if request.client:
            return request.client.host
        return "unknown"
