import base64
import json

import pytest
from httpx import AsyncClient

SHEET_URL = "https://docs.google.com/spreadsheets/d/abc123XYZ/edit"


@pytest.mark.asyncio
async def test_sheets_connect_requires_auth(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/sheets/connect?sheet_url={SHEET_URL}")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sheets_connect_returns_url(db_client: AsyncClient, auth_headers: dict) -> None:
    response = await db_client.get(
        f"/api/v1/sheets/connect?sheet_url={SHEET_URL}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "auth_url" in data
    assert "accounts.google.com" in data["auth_url"]

    # Verify state encodes the sheet_url
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(data["auth_url"])
    state = parse_qs(parsed.query)["state"][0]
    decoded = json.loads(base64.b64decode(state).decode())
    assert decoded["sheet_url"] == SHEET_URL


@pytest.mark.asyncio
async def test_sheets_list_empty(db_client: AsyncClient, auth_headers: dict) -> None:
    response = await db_client.get("/api/v1/sheets/", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []
