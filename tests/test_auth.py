import pytest
from httpx import AsyncClient


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
