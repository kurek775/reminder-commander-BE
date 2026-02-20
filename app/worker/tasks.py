import asyncio
import logging
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.interaction_log import (
    Channel,
    Direction,
    InteractionLog,
    MessageStatus,
)
from app.models.tracker_rule import TrackerRule
from app.models.user import User
from app.services.twilio_service import send_whatsapp
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="ping")
def ping() -> str:
    logger.info("Ping task executed")
    return "pong"


@celery_app.task(name="check_and_send_reminders")
def check_and_send_reminders() -> None:
    asyncio.run(_async_check_and_send())


async def _async_check_and_send() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await _process_rules(session)
            await session.commit()
    finally:
        await engine.dispose()


async def _process_rules(session) -> None:
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(TrackerRule, User)
        .join(User, TrackerRule.user_id == User.id)
        .where(
            TrackerRule.is_active.is_(True),
            User.is_active.is_(True),
            User.whatsapp_phone.is_not(None),
        )
    )
    rows = result.all()

    for rule, user in rows:
        if not croniter.match(rule.cron_schedule, now):
            continue

        loop = asyncio.get_event_loop()
        try:
            sid = await loop.run_in_executor(
                None, send_whatsapp, user.whatsapp_phone, rule.prompt_text
            )
            logger.info("Sent WhatsApp to %s, sid=%s", user.whatsapp_phone, sid)
            msg_status = MessageStatus.sent
        except Exception:
            logger.exception("Failed to send WhatsApp to %s", user.whatsapp_phone)
            msg_status = MessageStatus.failed

        session.add(
            InteractionLog(
                user_id=user.id,
                tracker_rule_id=rule.id,
                direction=Direction.outbound,
                channel=Channel.whatsapp,
                message_content=rule.prompt_text,
                status=msg_status,
            )
        )
        await session.flush()
