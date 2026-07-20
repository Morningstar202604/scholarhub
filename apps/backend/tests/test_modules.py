"""Module registry endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient

from app.modules import ENABLED_MODULES


async def test_modules_endpoint_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/modules")
    assert response.status_code == 401


async def test_modules_returns_loaded_modules(client: AsyncClient, test_user: dict) -> None:
    """``/api/modules`` returns all enabled modules."""
    response = await client.get(
        "/api/modules",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(ENABLED_MODULES)
    by_name = {m["name"]: m for m in body}
    assert set(by_name) == set(ENABLED_MODULES)
    for name in ENABLED_MODULES:
        assert by_name[name]["version"] == "0.1.0"
    assert "follow" in by_name["follows"]["description"].lower()
