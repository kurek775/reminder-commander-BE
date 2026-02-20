import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


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
