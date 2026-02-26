import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.core.encryption import encrypt
from app.main import app
from app.models.interaction_log import Channel, Direction, InteractionLog
from app.models.sheet_integration import SheetIntegration
from app.models.tracker_rule import RuleType, TrackerRule
from app.models.user import User

CALL_UUID = str(uuid.uuid4())
AUDIO_BYTES = b"FAKE_MP3_BYTES"


class MockRedis:
    def __init__(self, store: dict | None = None):
        self.store = store or {}

    async def get(self, key: str):
        return self.store.get(key)

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    async def aclose(self):
        pass


@pytest.fixture
async def warlord_user(db_session: AsyncSession) -> User:
    user = User(
        email="warlord@example.com",
        google_id="google_warlord_123",
        display_name="Warlord User",
        whatsapp_phone="+48111222333",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def warlord_integration(db_session: AsyncSession, warlord_user: User) -> SheetIntegration:
    integration = SheetIntegration(
        user_id=warlord_user.id,
        google_sheet_id="warlord_sheet_id",
        sheet_name="Warlord Sheet",
        encrypted_access_token=encrypt("access"),
        encrypted_refresh_token=encrypt("refresh"),
    )
    db_session.add(integration)
    await db_session.flush()
    await db_session.refresh(integration)
    return integration


@pytest.fixture
async def warlord_rule(
    db_session: AsyncSession,
    warlord_user: User,
    warlord_integration: SheetIntegration,
) -> TrackerRule:
    rule = TrackerRule(
        user_id=warlord_user.id,
        sheet_integration_id=warlord_integration.id,
        name="Warlord Rule",
        rule_type=RuleType.warlord,
        cron_schedule="* * * * *",
        target_column="A",
        prompt_text="Complete your tasks!",
    )
    db_session.add(rule)
    await db_session.flush()
    await db_session.refresh(rule)
    return rule


@pytest.mark.asyncio
async def test_voice_twiml_returns_xml(db_client: AsyncClient) -> None:
    # Mock Redis: audio present → expect <Play>
    mock_store = {f"voice_audio:{CALL_UUID}": b"1", f"voice_ctx:{CALL_UUID}": b"{}"}

    class MockRedisWithExists(MockRedis):
        async def exists(self, key: str) -> int:
            return 1 if key in self.store else 0

    async def mock_get_redis():
        yield MockRedisWithExists(mock_store)

    app.dependency_overrides[get_redis] = mock_get_redis
    try:
        response = await db_client.post(f"/api/v1/voice/twiml/{CALL_UUID}")
        assert response.status_code == 200
        assert "<Play>" in response.text
        assert "<Gather" in response.text
    finally:
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_voice_audio_returns_mp3(db_client: AsyncClient) -> None:
    mock_store = {f"voice_audio:{CALL_UUID}": AUDIO_BYTES}

    async def mock_get_redis():
        yield MockRedis(mock_store)

    app.dependency_overrides[get_redis] = mock_get_redis
    try:
        response = await db_client.get(f"/api/v1/voice/audio/{CALL_UUID}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.content == AUDIO_BYTES
    finally:
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_voice_audio_not_found(db_client: AsyncClient) -> None:
    async def mock_get_redis():
        yield MockRedis({})

    app.dependency_overrides[get_redis] = mock_get_redis
    try:
        response = await db_client.get(f"/api/v1/voice/audio/bad-uuid")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_voice_gather_logs_inbound(
    db_client: AsyncClient,
    db_session: AsyncSession,
    warlord_user: User,
    warlord_rule: TrackerRule,
) -> None:
    ctx = {
        "user_id": str(warlord_user.id),
        "tracker_rule_id": str(warlord_rule.id),
        "task_name": "Exercise",
        "interaction_log_id": str(uuid.uuid4()),
        "whatsapp_phone": warlord_user.whatsapp_phone,
    }
    mock_store = {f"voice_ctx:{CALL_UUID}": json.dumps(ctx).encode()}

    async def mock_get_redis():
        yield MockRedis(mock_store)

    app.dependency_overrides[get_redis] = mock_get_redis
    try:
        response = await db_client.post(
            f"/api/v1/voice/gather/{CALL_UUID}",
            data={"Digits": "1"},
        )
        assert response.status_code == 200
        assert "xml" in response.headers["content-type"]

        result = await db_session.execute(
            select(InteractionLog).where(
                InteractionLog.user_id == warlord_user.id,
                InteractionLog.direction == Direction.inbound,
                InteractionLog.channel == Channel.voice,
            )
        )
        logs = result.scalars().all()
        assert len(logs) >= 1
        assert "1" in logs[-1].message_content
    finally:
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_voice_status_no_answer_sends_whatsapp(
    db_client: AsyncClient,
    warlord_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.v1.routes.voice as voice_module

    ctx = {
        "user_id": str(warlord_user.id),
        "tracker_rule_id": None,
        "task_name": "Exercise",
        "interaction_log_id": str(uuid.uuid4()),
        "whatsapp_phone": warlord_user.whatsapp_phone,
    }
    mock_store = {f"voice_ctx:{CALL_UUID}": json.dumps(ctx).encode()}

    async def mock_get_redis():
        yield MockRedis(mock_store)

    called: list[tuple] = []

    def mock_send_whatsapp(to: str, body: str) -> str:
        called.append((to, body))
        return "mock_sid"

    monkeypatch.setattr(voice_module, "send_whatsapp", mock_send_whatsapp)
    app.dependency_overrides[get_redis] = mock_get_redis
    try:
        response = await db_client.post(
            f"/api/v1/voice/status/{CALL_UUID}",
            data={"CallStatus": "no-answer"},
        )
        assert response.status_code == 200
        assert len(called) == 1
        assert called[0][0] == warlord_user.whatsapp_phone
    finally:
        app.dependency_overrides.pop(get_redis, None)


@pytest.mark.asyncio
async def test_voice_status_completed_no_fallback(
    db_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.api.v1.routes.voice as voice_module

    ctx = {
        "user_id": str(uuid.uuid4()),
        "task_name": "Exercise",
        "whatsapp_phone": "+48000000000",
    }
    mock_store = {f"voice_ctx:{CALL_UUID}": json.dumps(ctx).encode()}

    async def mock_get_redis():
        yield MockRedis(mock_store)

    called: list[tuple] = []

    def mock_send_whatsapp(to: str, body: str) -> str:
        called.append((to, body))
        return "mock_sid"

    monkeypatch.setattr(voice_module, "send_whatsapp", mock_send_whatsapp)
    app.dependency_overrides[get_redis] = mock_get_redis
    try:
        response = await db_client.post(
            f"/api/v1/voice/status/{CALL_UUID}",
            data={"CallStatus": "completed"},
        )
        assert response.status_code == 200
        assert len(called) == 0
    finally:
        app.dependency_overrides.pop(get_redis, None)
