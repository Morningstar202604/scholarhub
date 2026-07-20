"""Auth flow tests: register / login / refresh / logout / me."""

from __future__ import annotations

from httpx import AsyncClient


async def test_register_creates_user_and_returns_tokens(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "password123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["username"] == "newuser"
    assert data["is_admin"] is False
    # Refresh token cookie should be set.
    assert "scholarhub_refresh" in response.cookies


async def test_register_duplicate_email_returns_201_no_token(
    client: AsyncClient, test_user: dict
) -> None:
    """Anti-enumeration: re-registering an existing email returns 201 with
    the same body shape as success but WITHOUT issuing tokens."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "username": "another",
            "password": "password123",
        },
    )
    assert response.status_code == 201
    body = response.json()
    # No tokens leaked — anti-takeover contract.
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert "message" in body
    # No refresh cookie set on duplicate registration.
    assert "scholarhub_refresh" not in response.cookies


async def test_login_returns_valid_tokens(client: AsyncClient, test_user: dict) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["username"] == "testuser"


async def test_login_rejects_bad_password(client: AsyncClient, test_user: dict) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "wrongpassword"},
    )
    assert response.status_code == 401


async def test_me_requires_token(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


async def test_me_returns_current_user(client: AsyncClient, test_user: dict) -> None:
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "testuser"
    assert body["email"] == "user@example.com"
    assert body["is_admin"] is False


async def test_refresh_via_cookie_issues_new_tokens(
    client: AsyncClient, test_user: dict
) -> None:
    # Cookie was set on the client during register/login, so we do not
    # need to pass it explicitly.
    response = await client.post("/api/auth/refresh")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["username"] == "testuser"


async def test_refresh_rotates_old_refresh_token(
    client: AsyncClient, test_user: dict
) -> None:
    """Refresh token rotation: a refresh token consumed once must not work again."""
    # First refresh: gets new pair, old refresh token (in cookie) is rotated out.
    first = await client.post("/api/auth/refresh")
    assert first.status_code == 200
    first_refresh_token = first.json()["refresh_token"]
    # Client cookie was updated to first_refresh_token after the call.

    # Second refresh using the NEW cookie succeeds and rotates again.
    second = await client.post("/api/auth/refresh")
    assert second.status_code == 200

    # Replay the rotated-out refresh token (first_refresh_token) via the body.
    # Clear the client cookie first so the server reads only the body —
    # otherwise the cookie (which holds the latest, still-valid token)
    # would mask the replay attempt.
    client.cookies.clear()
    replay = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": first_refresh_token},
    )
    assert replay.status_code == 401


async def test_refresh_rejects_after_logout(client: AsyncClient, test_user: dict) -> None:
    logout = await client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {test_user['token']}"},
    )
    assert logout.status_code == 204

    # Old refresh token (cookie) must be invalid because token_version bumped.
    refresh = await client.post("/api/auth/refresh")
    assert refresh.status_code == 401


async def test_logout_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/auth/logout")
    assert response.status_code == 401


async def test_old_access_token_invalid_after_logout(
    client: AsyncClient, test_user: dict
) -> None:
    token = test_user["token"]
    logout = await client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout.status_code == 204

    me = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 401
