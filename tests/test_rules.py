import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt
from app.models.sheet_integration import SheetIntegration
from app.models.user import User


@pytest.fixture
async def sheet_integration(db_session: AsyncSession, test_user: User) -> SheetIntegration:
    integration = SheetIntegration(
        user_id=test_user.id,
        google_sheet_id="test_sheet_id",
        sheet_name="Test Sheet",
        encrypted_access_token=encrypt("access"),
        encrypted_refresh_token=encrypt("refresh"),
    )
    db_session.add(integration)
    await db_session.flush()
    await db_session.refresh(integration)
    return integration


RULE_PAYLOAD = {
    "name": "Morning Check-in",
    "rule_type": "health_tracker",
    "cron_schedule": "0 8 * * *",
    "target_column": "B",
    "metric_name": "Weight (kg)",
    "prompt_text": "How are you feeling today?",
    "is_active": True,
}


@pytest.mark.asyncio
async def test_create_rule_requires_auth(db_client: AsyncClient, sheet_integration: SheetIntegration) -> None:
    payload = {**RULE_PAYLOAD, "sheet_integration_id": str(sheet_integration.id)}
    response = await db_client.post("/api/v1/rules/", json=payload)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_rule(
    db_client: AsyncClient,
    auth_headers: dict,
    sheet_integration: SheetIntegration,
) -> None:
    payload = {**RULE_PAYLOAD, "sheet_integration_id": str(sheet_integration.id)}
    response = await db_client.post("/api/v1/rules/", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Morning Check-in"
    assert data["cron_schedule"] == "0 8 * * *"
    assert data["target_column"] == "B"
    assert data["metric_name"] == "Weight (kg)"
    assert data["prompt_text"] == "How are you feeling today?"
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_list_rules_empty(
    db_client: AsyncClient,
    auth_headers: dict,
) -> None:
    response = await db_client.get("/api/v1/rules/", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_rules(
    db_client: AsyncClient,
    auth_headers: dict,
    sheet_integration: SheetIntegration,
) -> None:
    payload = {**RULE_PAYLOAD, "sheet_integration_id": str(sheet_integration.id)}
    await db_client.post("/api/v1/rules/", json=payload, headers=auth_headers)

    response = await db_client.get("/api/v1/rules/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(r["name"] == "Morning Check-in" for r in data)


@pytest.mark.asyncio
async def test_delete_rule(
    db_client: AsyncClient,
    auth_headers: dict,
    sheet_integration: SheetIntegration,
) -> None:
    payload = {**RULE_PAYLOAD, "sheet_integration_id": str(sheet_integration.id)}
    create_resp = await db_client.post("/api/v1/rules/", json=payload, headers=auth_headers)
    rule_id = create_resp.json()["id"]

    delete_resp = await db_client.delete(f"/api/v1/rules/{rule_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    list_resp = await db_client.get("/api/v1/rules/", headers=auth_headers)
    assert all(r["id"] != rule_id for r in list_resp.json())


@pytest.mark.asyncio
async def test_delete_rule_not_found(
    db_client: AsyncClient,
    auth_headers: dict,
) -> None:
    random_id = str(uuid.uuid4())
    response = await db_client.delete(f"/api/v1/rules/{random_id}", headers=auth_headers)
    assert response.status_code == 404
