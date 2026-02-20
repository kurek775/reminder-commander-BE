import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_schema(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    body = response.json()
    assert body["status"] == "ok"
    assert body["message"] == "Hello from Reminder Commander!"
    assert "version" in body


@pytest.mark.asyncio
async def test_health_content_type(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert "application/json" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_health_cors_header(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.headers.get("access-control-allow-origin") == "http://localhost:4200"
