import asyncio
import json
import logging
import uuid
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
from app.models.sheet_integration import SheetIntegration
from app.models.tracker_rule import RuleType, TrackerRule
from app.models.user import User
from app.services.twilio_service import send_whatsapp
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# M8: Module-level engine reused across tasks instead of creating per-task
_engine = None
_factory = None


def _get_session_factory():
    global _engine, _factory
    if _engine is None:
        _engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
        _factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _factory


@celery_app.task(name="ping")
def ping() -> str:
    logger.info("Ping task executed")
    return "pong"


@celery_app.task(
    name="check_and_send_reminders",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def check_and_send_reminders() -> None:
    asyncio.run(_async_check_and_send())


async def _async_check_and_send() -> None:
    factory = _get_session_factory()
    async with factory() as session:
        await _process_rules(session)
        await session.commit()


async def _process_rules(session) -> None:
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(TrackerRule, User)
        .join(User, TrackerRule.user_id == User.id)
        .where(
            TrackerRule.is_active.is_(True),
            TrackerRule.rule_type == RuleType.health_tracker,
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


@celery_app.task(
    name="scan_warlord_sheets",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def scan_warlord_sheets(force: bool = False) -> None:
    asyncio.run(_async_scan_warlord(force=force))


async def _async_scan_warlord(force: bool = False) -> None:
    factory = _get_session_factory()
    async with factory() as session:
        await _process_warlord_rules(session, force=force)
        await session.commit()


async def _process_warlord_rules(session, force: bool = False) -> None:
    from app.core.redis import _create_redis
    from app.services.elevenlabs_service import generate_audio
    from app.services.sheets_service import get_warlord_tasks
    from app.services.twilio_service import make_voice_call

    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(TrackerRule, User, SheetIntegration)
        .join(User, TrackerRule.user_id == User.id)
        .join(SheetIntegration, TrackerRule.sheet_integration_id == SheetIntegration.id)
        .where(
            TrackerRule.is_active.is_(True),
            TrackerRule.rule_type == RuleType.warlord,
            User.is_active.is_(True),
            User.whatsapp_phone.is_not(None),
        )
    )
    rows = result.all()

    r = _create_redis()
    try:
        for rule, user, integration in rows:
            if not force and not croniter.match(rule.cron_schedule, now):
                continue

            try:
                tasks = await get_warlord_tasks(session, integration)
            except Exception:
                logger.exception("Failed to fetch warlord tasks for rule %s", rule.id)
                continue

            for task in tasks:
                call_uuid = str(uuid.uuid4())
                if rule.prompt_text:
                    msg = (
                        rule.prompt_text
                        .replace("{task_name}", task.task_name)
                        .replace("{deadline}", str(task.deadline))
                    )
                else:
                    msg = f"{task.task_name} was due on {task.deadline}. Complete it now."

                try:
                    audio_bytes = await generate_audio(msg)
                except Exception:
                    logger.exception("ElevenLabs TTS failed for task %s", task.task_name)
                    audio_bytes = None

                log = InteractionLog(
                    user_id=user.id,
                    tracker_rule_id=rule.id,
                    direction=Direction.outbound,
                    channel=Channel.voice,
                    message_content=msg,
                    status=MessageStatus.sent,
                )
                session.add(log)
                await session.flush()
                await session.refresh(log)

                loop = asyncio.get_event_loop()

                ctx = {
                    "user_id": str(user.id),
                    "tracker_rule_id": str(rule.id),
                    "task_name": task.task_name,
                    "message": msg,
                    "interaction_log_id": str(log.id),
                    "whatsapp_phone": user.whatsapp_phone,
                }
                await r.setex(f"voice_ctx:{call_uuid}", 3600, json.dumps(ctx))

                if audio_bytes:
                    await r.setex(f"voice_audio:{call_uuid}", 3600, audio_bytes)

                twiml_url = f"{settings.backend_url}/api/v1/voice/twiml/{call_uuid}"
                status_url = f"{settings.backend_url}/api/v1/voice/status/{call_uuid}"
                try:
                    call_sid = await loop.run_in_executor(
                        None, make_voice_call, user.whatsapp_phone, twiml_url, status_url
                    )
                    logger.info(
                        "Voice call initiated: sid=%s for task %s",
                        call_sid,
                        task.task_name,
                    )
                except Exception:
                    logger.exception(
                        "Voice call failed for task %s, sending WhatsApp fallback",
                        task.task_name,
                    )
                    try:
                        await loop.run_in_executor(
                            None,
                            send_whatsapp,
                            user.whatsapp_phone,
                            f"Missed task: {task.task_name}",
                        )
                    except Exception:
                        logger.exception(
                            "WhatsApp fallback also failed for task %s", task.task_name
                        )
    finally:
        await r.aclose()
