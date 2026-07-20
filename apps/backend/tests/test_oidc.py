"""OIDC SSO route tests.

We don't run a full OIDC round-trip in tests (would need a fake IdP).
The behaviors that matter for the API contract are:

- When OIDC is disabled (the default), routes return 503.
- When configured provider ≠ path provider, routes return 404.
- When OIDC is configured + provider matches + state is bad, callback 400.

These three cover the negative paths. The happy path is exercised by the
integration test in CI against a real Keycloak container.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def oidc_enabled_client(client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Enable OIDC + configure a fake provider for the duration of the test.

    Mutates the cached ``settings`` because it's an ``lru_cache`` singleton
    in production. Restores the previous values on teardown so other tests
    see the default disabled state.
    """
    from app.core.config import settings

    prev = {
        "oidc_enabled": settings.oidc_enabled,
        "oidc_provider": settings.oidc_provider,
        "oidc_client_id": settings.oidc_client_id,
        "oidc_client_secret": settings.oidc_client_secret,
        "oidc_authorize_url": settings.oidc_authorize_url,
        "oidc_token_url": settings.oidc_token_url,
        "oidc_userinfo_url": settings.oidc_userinfo_url,
        "oidc_redirect_url": settings.oidc_redirect_url,
    }
    settings.oidc_enabled = True
    settings.oidc_provider = "google"
    settings.oidc_client_id = "test-client-id"
    settings.oidc_client_secret = "test-client-secret"
    settings.oidc_authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    settings.oidc_token_url = "https://oauth2.googleapis.com/token"
    settings.oidc_userinfo_url = "https://openidconnect.googleapis.com/v1/userinfo"
    settings.oidc_redirect_url = "http://localhost:5173/auth/oidc/callback"
    try:
        yield client
    finally:
        for key, val in prev.items():
            setattr(settings, key, val)


async def test_oidc_login_disabled_returns_503(client: AsyncClient) -> None:
    response = await client.get("/api/auth/oidc/google/login")
    assert response.status_code == 503


async def test_oidc_callback_disabled_returns_503(client: AsyncClient) -> None:
    response = await client.get(
        "/api/auth/oidc/google/callback",
        params={"code": "fake-code", "state": "fake-state"},
    )
    assert response.status_code == 503


async def test_oidc_login_wrong_provider_404(
    oidc_enabled_client: AsyncClient,
) -> None:
    response = await oidc_enabled_client.get("/api/auth/oidc/github/login")
    assert response.status_code == 404


async def test_oidc_login_redirects_to_provider(
    oidc_enabled_client: AsyncClient,
) -> None:
    response = await oidc_enabled_client.get(
        "/api/auth/oidc/google/login", follow_redirects=False
    )
    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert "accounts.google.com" in location
    assert "client_id=test-client-id" in location
    assert "state=" in location  # signed JWT state token attached


async def test_oidc_callback_bad_state_400(
    oidc_enabled_client: AsyncClient,
) -> None:
    response = await oidc_enabled_client.get(
        "/api/auth/oidc/google/callback",
        params={"code": "fake-code", "state": "garbage"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired OIDC state"
