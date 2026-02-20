from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.v1.routes.webhook as webhook_module
from app.core.encryption import encrypt
from app.models.interaction_log import (
    Channel,
    Direction,
    InteractionLog,
    MessageStatus,
)
from app.models.sheet_integration import SheetIntegration
from app.models.tracker_rule import RuleType, TrackerRule
from app.models.user import User


@pytest.fixture
async def webhook_user(db_session: AsyncSession) -> User:
    user = User(
        email="webhook@example.com",
        google_id="google_webhook_123",
        display_name="Webhook User",
        whatsapp_phone="+48999888777",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def webhook_integration(
    db_session: AsyncSession, webhook_user: User
) -> SheetIntegration:
    integration = SheetIntegration(
        user_id=webhook_user.id,
        google_sheet_id="webhook_sheet_id",
        sheet_name="Webhook Sheet",
        encrypted_access_token=encrypt("access"),
        encrypted_refresh_token=encrypt("refresh"),
    )
    db_session.add(integration)
    await db_session.flush()
    await db_session.refresh(integration)
    return integration


@pytest.fixture
async def webhook_rule(
    db_session: AsyncSession,
    webhook_user: User,
    webhook_integration: SheetIntegration,
) -> TrackerRule:
    rule = TrackerRule(
        user_id=webhook_user.id,
        sheet_integration_id=webhook_integration.id,
        name="Daily Check",
        rule_type=RuleType.health_tracker,
        cron_schedule="0 8 * * *",
        target_column="B",
        prompt_text="How do you feel?",
    )
    db_session.add(rule)
    await db_session.flush()
    await db_session.refresh(rule)
    return rule


@pytest.fixture
async def outbound_log(
    db_session: AsyncSession,
    webhook_user: User,
    webhook_rule: TrackerRule,
) -> InteractionLog:
    log = InteractionLog(
        user_id=webhook_user.id,
        tracker_rule_id=webhook_rule.id,
        direction=Direction.outbound,
        channel=Channel.whatsapp,
        message_content="How do you feel?",
        status=MessageStatus.sent,
    )
    db_session.add(log)
    await db_session.flush()
    await db_session.refresh(log)
    return log


@pytest.mark.asyncio
async def test_webhook_unknown_phone(db_client: AsyncClient) -> None:
    response = await db_client.post(
        "/api/v1/webhook/twilio",
        data={"From": "whatsapp:+10000000000", "Body": "hello"},
    )
    assert response.status_code == 200
    assert "<Response/>" in response.text


@pytest.mark.asyncio
async def test_webhook_inbound_appends_to_sheet(
    db_client: AsyncClient,
    db_session: AsyncSession,
    webhook_user: User,
    outbound_log: InteractionLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appended: list[tuple] = []

    async def mock_append(db, integration, target_column, value):
        appended.append((target_column, value))

    monkeypatch.setattr(webhook_module, "append_to_sheet", mock_append)

    response = await db_client.post(
        "/api/v1/webhook/twilio",
        data={"From": f"whatsapp:{webhook_user.whatsapp_phone}", "Body": "Feeling great!"},
    )
    assert response.status_code == 200
    assert "<Response/>" in response.text

    # Verify inbound log was created
    from sqlalchemy import select
    result = await db_session.execute(
        select(InteractionLog).where(
            InteractionLog.user_id == webhook_user.id,
            InteractionLog.direction == Direction.inbound,
        )
    )
    inbound_logs = result.scalars().all()
    assert len(inbound_logs) >= 1
    assert inbound_logs[-1].message_content == "Feeling great!"

    # Verify append was called
    assert len(appended) == 1
    assert appended[0] == ("B", "Feeling great!")


@pytest.mark.asyncio
async def test_webhook_no_outbound_log(
    db_client: AsyncClient,
    webhook_user: User,
) -> None:
    # webhook_user exists but has no outbound logs
    response = await db_client.post(
        "/api/v1/webhook/twilio",
        data={"From": f"whatsapp:{webhook_user.whatsapp_phone}", "Body": "reply"},
    )
    assert response.status_code == 200
    assert "<Response/>" in response.text


@pytest.mark.asyncio
async def test_webhook_second_message_ignored(
    db_client: AsyncClient,
    db_session: AsyncSession,
    webhook_user: User,
    outbound_log: InteractionLog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate the user having already replied once (first reply after reminder)
    first_reply = InteractionLog(
        user_id=webhook_user.id,
        tracker_rule_id=outbound_log.tracker_rule_id,
        direction=Direction.inbound,
        channel=Channel.whatsapp,
        message_content="First reply",
        status=MessageStatus.received,
        created_at=outbound_log.created_at + timedelta(seconds=1),
    )
    db_session.add(first_reply)
    await db_session.flush()

    appended: list[tuple] = []

    async def mock_append(db, integration, target_column, value):
        appended.append((target_column, value))

    monkeypatch.setattr(webhook_module, "append_to_sheet", mock_append)

    # Send a second message — should be ignored
    response = await db_client.post(
        "/api/v1/webhook/twilio",
        data={"From": f"whatsapp:{webhook_user.whatsapp_phone}", "Body": "Second message"},
    )
    assert response.status_code == 200
    assert "<Response/>" in response.text

    # Verify append was NOT called for the second message
    assert len(appended) == 0
