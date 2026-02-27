import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.main import app
from app.models.user import User
from tests.conftest import MockRedis


@pytest.mark.asyncio
async def test_google_auth_url(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/google")
    assert response.status_code == 200
    data = response.json()
    assert "auth_url" in data
    assert "accounts.google.com" in data["auth_url"]


@pytest.mark.asyncio
async def test_me_without_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_me_with_auth(db_client: AsyncClient, auth_headers: dict) -> None:
    response = await db_client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["display_name"] == "Test User"
    assert data["whatsapp_verified"] is False


@pytest.mark.asyncio
async def test_whatsapp_link(db_client: AsyncClient, auth_headers: dict) -> None:
    response = await db_client.patch(
        "/api/v1/auth/whatsapp/link",
        json={"phone": "+48123456789"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["phone"] == "+48123456789"


@pytest.mark.asyncio
async def test_whatsapp_link_duplicate(
    db_client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
) -> None:
    other_user = User(
        email="other@example.com",
        google_id="google_other_456",
        display_name="Other User",
        whatsapp_phone="+48999999999",
    )
    db_session.add(other_user)
    await db_session.flush()

    response = await db_client.patch(
        "/api/v1/auth/whatsapp/link",
        json={"phone": "+48999999999"},
        headers=auth_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_whatsapp_link_same_user_ok(
    db_client: AsyncClient,
    auth_headers: dict,
    test_user: User,
    db_session: AsyncSession,
) -> None:
    test_user.whatsapp_phone = "+48111111111"
    await db_session.flush()

    response = await db_client.patch(
        "/api/v1/auth/whatsapp/link",
        json={"phone": "+48111111111"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["phone"] == "+48111111111"


@pytest.mark.asyncio
async def test_exchange_valid_code(db_client: AsyncClient) -> None:
    """H9: Exchange a valid auth code for tokens."""
    tokens = {"access_token": "test-jwt", "refresh_token": "test-refresh", "token_type": "bearer"}
    mock_store = {"auth_code:test-code-123": json.dumps(tokens)}

    async def mock_get_redis():
        yield MockRedis(mock_store)

    app.dependency_overrides[get_redis] = mock_get_redis
    try:
        response = await db_client.post(
            "/api/v1/auth/exchange",
            json={"code": "test-code-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "test-jwt"
        assert data["refresh_token"] == "test-refresh"
        # Code should be consumed (one-time use)
        assert "auth_code:test-code-123" not in mock_store
    finally:
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_exchange_invalid_code(db_client: AsyncClient) -> None:
    """H9: Invalid auth code returns 400."""
    async def mock_get_redis():
        yield MockRedis({})

    app.dependency_overrides[get_redis] = mock_get_redis
    try:
        response = await db_client.post(
            "/api/v1/auth/exchange",
            json={"code": "invalid-code"},
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_refresh_token(db_client: AsyncClient, test_user: User) -> None:
    """M14: Refresh token returns new tokens."""
    from app.core.security import create_refresh_token

    refresh = create_refresh_token({"sub": str(test_user.id), "email": test_user.email})
    response = await db_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
