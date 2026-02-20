import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction_log import Channel, Direction, InteractionLog, MessageStatus
from app.models.sheet_integration import SheetIntegration
from app.models.user import User


@pytest.mark.asyncio
async def test_user_create_and_query(db_session: AsyncSession) -> None:
    user = User(
        email="model_test@example.com",
        google_id="google_model_456",
        display_name="Model Test User",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    fetched = await db_session.get(User, user.id)
    assert fetched is not None
    assert fetched.email == "model_test@example.com"
    assert fetched.whatsapp_verified is False
    assert fetched.is_active is True
    assert isinstance(fetched.id, uuid.UUID)


@pytest.mark.asyncio
async def test_sheet_integration_fk(db_session: AsyncSession, test_user: User) -> None:
    integration = SheetIntegration(
        user_id=test_user.id,
        google_sheet_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
        sheet_name="Health Tracker",
        encrypted_access_token="enc_access_token",
        encrypted_refresh_token="enc_refresh_token",
    )
    db_session.add(integration)
    await db_session.flush()
    await db_session.refresh(integration)

    assert integration.id is not None
    assert integration.user_id == test_user.id
    assert integration.is_active is True


@pytest.mark.asyncio
async def test_interaction_log_without_tracker_rule(
    db_session: AsyncSession, test_user: User
) -> None:
    log = InteractionLog(
        user_id=test_user.id,
        tracker_rule_id=None,
        direction=Direction.outbound,
        channel=Channel.whatsapp,
        message_content="Hello, World!",
        status=MessageStatus.sent,
    )
    db_session.add(log)
    await db_session.flush()
    await db_session.refresh(log)

    assert log.id is not None
    assert log.tracker_rule_id is None
    assert log.direction == Direction.outbound
    assert log.status == MessageStatus.sent
