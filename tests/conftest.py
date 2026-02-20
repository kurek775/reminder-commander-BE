import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(scope="session")
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Origin": "http://localhost:4200"},
    ) as ac:
        yield ac
