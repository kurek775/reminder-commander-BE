import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sheet_integration import SheetIntegration
from app.models.tracker_rule import TrackerRule
from app.models.user import User


@pytest.mark.asyncio
async def test_dashboard_summary_requires_auth(db_client: AsyncClient):
    resp = await db_client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dashboard_summary_empty(
    db_client: AsyncClient,
    auth_headers: dict,
):
    resp = await db_client.get("/api/v1/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["health_rules_active"] == 0
    assert data["warlord_rules_active"] == 0
    assert data["sheets_connected"] == 0
    assert data["has_whatsapp"] is False
    assert data["recent_interactions"] == 0


@pytest.mark.asyncio
async def test_dashboard_summary_with_data(
    db_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict,
):
    # Create a sheet
    sheet = SheetIntegration(
        user_id=test_user.id,
        google_sheet_id="abc123",
        sheet_name="Test Sheet",
        encrypted_access_token="enc",
        encrypted_refresh_token="enc",
        is_active=True,
    )
    db_session.add(sheet)
    await db_session.flush()

    # Create rules
    rule_ht = TrackerRule(
        user_id=test_user.id,
        sheet_integration_id=sheet.id,
        name="Health Rule",
        rule_type="health_tracker",
        cron_schedule="0 8 * * *",
        target_column="B",
        metric_name="Weight",
        prompt_text="How are you?",
        is_active=True,
    )
    rule_w = TrackerRule(
        user_id=test_user.id,
        sheet_integration_id=sheet.id,
        name="Warlord Rule",
        rule_type="warlord",
        cron_schedule="0 9 * * *",
        target_column="A",
        prompt_text="Call about task",
        is_active=True,
    )
    db_session.add_all([rule_ht, rule_w])
    await db_session.flush()

    # Link WhatsApp
    test_user.whatsapp_phone = "+48123456789"
    await db_session.flush()

    resp = await db_client.get("/api/v1/dashboard/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["health_rules_active"] == 1
    assert data["warlord_rules_active"] == 1
    assert data["sheets_connected"] == 1
    assert data["has_whatsapp"] is True
