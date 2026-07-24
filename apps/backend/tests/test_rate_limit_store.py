"""Tests for the rate-limiter store abstraction (M4 hardening).

Covers:
- ``MemoryRateLimiterStore`` sliding-window semantics: under the
  limit, at the limit (last hit denied), over the limit (denied),
  recovery after the window slides forward.
- The store exposes the same interface to the middleware regardless
  of backend (memory vs. Redis).
- Redis backend is selected when ``settings.redis_url`` is set.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.rate_limit_store import (
    MemoryRateLimiterStore,
    RateLimiterStore,
    RedisRateLimiterStore,
    get_rate_limiter_store,
)


@pytest.fixture
def memory_store() -> MemoryRateLimiterStore:
    return MemoryRateLimiterStore()


async def test_allows_under_limit(memory_store):
    for _ in range(5):
        allowed, depth = await memory_store.hit_and_check(
            bucket_key="ip1|/api/auth/login",
            limit=10,
            window_seconds=60.0,
        )
        assert allowed is True
    # Final depth is 5.
    allowed, depth = await memory_store.hit_and_check(
        bucket_key="ip1|/api/auth/login",
        limit=10,
        window_seconds=60.0,
    )
    assert allowed is True
    assert depth == 6


async def test_denies_over_limit(memory_store):
    # Fill up to the limit (5 hits, all allowed, depth 5).
    for _ in range(5):
        allowed, _ = await memory_store.hit_and_check(
            bucket_key="ip1|/api/auth/login",
            limit=5,
            window_seconds=60.0,
        )
        assert allowed is True
    # 6th hit: bucket is full, must be denied, depth still 5.
    allowed, depth = await memory_store.hit_and_check(
        bucket_key="ip1|/api/auth/login",
        limit=5,
        window_seconds=60.0,
    )
    assert allowed is False
    assert depth == 5


async def test_window_recovery(memory_store):
    """After the window slides forward, denied hits become allowed again."""
    # Window of 1 second, fill it up.
    for _ in range(3):
        allowed, _ = await memory_store.hit_and_check(
            bucket_key="ip1|x",
            limit=3,
            window_seconds=1.0,
        )
        assert allowed is True
    allowed, _ = await memory_store.hit_and_check(
        bucket_key="ip1|x", limit=3, window_seconds=1.0
    )
    assert allowed is False

    # Wait out the window.
    await asyncio.sleep(1.1)

    allowed, depth = await memory_store.hit_and_check(
        bucket_key="ip1|x", limit=3, window_seconds=1.0
    )
    assert allowed is True
    assert depth == 1  # only the new hit is in the fresh window


async def test_independent_buckets(memory_store):
    """Two distinct bucket_keys must not share counters."""
    for _ in range(3):
        allowed, _ = await memory_store.hit_and_check(
            bucket_key="ip1|a", limit=3, window_seconds=60.0
        )
        assert allowed is True
    # ip1|a is now full.
    allowed_a, _ = await memory_store.hit_and_check(
        bucket_key="ip1|a", limit=3, window_seconds=60.0
    )
    assert allowed_a is False

    # ip1|b is independent.
    allowed_b, _ = await memory_store.hit_and_check(
        bucket_key="ip1|b", limit=3, window_seconds=60.0
    )
    assert allowed_b is True


async def test_store_factory_returns_memory_when_no_redis(monkeypatch):
    from app.core import rate_limit_store as mod

    # Reset cached singleton so the factory re-runs.
    mod._store = None

    from app.core.config import settings

    monkeypatch.setattr(settings, "redis_url", "")
    store = get_rate_limiter_store()
    assert isinstance(store, MemoryRateLimiterStore)
    assert isinstance(store, RateLimiterStore)


async def test_store_factory_returns_redis_when_url_set(monkeypatch):
    from app.core import rate_limit_store as mod

    mod._store = None

    from app.core.config import settings

    monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0")
    store = get_rate_limiter_store()
    assert isinstance(store, RedisRateLimiterStore)
    # Reset for other tests
    mod._store = None
    monkeypatch.setattr(settings, "redis_url", "")