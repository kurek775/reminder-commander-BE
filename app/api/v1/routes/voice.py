import asyncio
import json
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Form, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.core.config import settings
from app.core.redis import get_redis
from app.core.twilio_auth import verify_twilio_signature
from app.db.base import get_db
from app.models.interaction_log import Channel, Direction, InteractionLog, MessageStatus
from app.services.twilio_service import send_whatsapp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


@router.api_route("/twiml/{call_uuid}", methods=["GET", "POST"], dependencies=[Depends(verify_twilio_signature)])
async def get_twiml(
    call_uuid: str,
    r: aioredis.Redis = Depends(get_redis),
) -> Response:
    """Return TwiML: <Play> ElevenLabs audio if available, else <Say> the text."""
    gather_url = f"{settings.backend_url}/api/v1/voice/gather/{call_uuid}"

    response = VoiceResponse()
    gather = Gather(num_digits="1", action=gather_url, method="POST")

    try:
        has_audio = await r.exists(f"voice_audio:{call_uuid}")
        if has_audio:
            audio_url = f"{settings.backend_url}/api/v1/voice/audio/{call_uuid}"
            gather.play(audio_url)
        else:
            ctx_raw = await r.get(f"voice_ctx:{call_uuid}")
            text = "You have a missed task. Please acknowledge."
            if ctx_raw:
                ctx = json.loads(ctx_raw)
                task_name = ctx.get("task_name", "")
                text = f"{ctx.get('message', task_name + ' is overdue. Please acknowledge.')}"
            gather.say(text)
    except aioredis.RedisError:
        logger.exception("Redis error in get_twiml for %s", call_uuid)
        gather.say("You have a missed task. Please acknowledge.")

    response.append(gather)
    return Response(content=str(response), media_type="application/xml")


@router.get("/audio/{call_uuid}")
async def get_audio(
    call_uuid: str,
    r: aioredis.Redis = Depends(get_redis),
) -> Response:
    """Return the MP3 audio clip for the given call UUID from Redis."""
    data = await r.get(f"voice_audio:{call_uuid}")
    if not data:
        raise HTTPException(status_code=404, detail="Audio not found")
    return Response(content=bytes(data), media_type="audio/mpeg")


@router.post("/gather/{call_uuid}", dependencies=[Depends(verify_twilio_signature)])
async def handle_gather(
    call_uuid: str,
    Digits: str = Form(default=""),
    r: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Twilio posts the key pressed by the caller; log it as an inbound voice interaction."""
    twiml = VoiceResponse()

    try:
        ctx_raw = await r.get(f"voice_ctx:{call_uuid}")
    except aioredis.RedisError:
        logger.exception("Redis error in handle_gather for %s", call_uuid)
        twiml.say("An error occurred. Goodbye.")
        return Response(content=str(twiml), media_type="application/xml")

    if ctx_raw:
        ctx = json.loads(ctx_raw)
        log = InteractionLog(
            user_id=uuid.UUID(ctx["user_id"]),
            tracker_rule_id=uuid.UUID(ctx["tracker_rule_id"]) if ctx.get("tracker_rule_id") else None,
            direction=Direction.inbound,
            channel=Channel.voice,
            message_content=f"Key pressed: {Digits}",
            status=MessageStatus.received,
        )
        db.add(log)
        await db.flush()
        twiml.say("Thank you. Goodbye.")

    return Response(content=str(twiml), media_type="application/xml")


@router.post("/status/{call_uuid}", dependencies=[Depends(verify_twilio_signature)])
async def handle_status(
    call_uuid: str,
    CallStatus: str = Form(default=""),
    r: aioredis.Redis = Depends(get_redis),
) -> Response:
    """Twilio posts call status updates; send WhatsApp fallback on failure."""
    if CallStatus in ("failed", "busy", "no-answer"):
        try:
            ctx_raw = await r.get(f"voice_ctx:{call_uuid}")
        except aioredis.RedisError:
            logger.exception("Redis error in handle_status for %s", call_uuid)
            return Response(content=str(VoiceResponse()), media_type="application/xml")

        if ctx_raw:
            ctx = json.loads(ctx_raw)
            phone = ctx.get("whatsapp_phone")
            task_name = ctx.get("task_name", "")
            if phone:
                loop = asyncio.get_running_loop()
                try:
                    await loop.run_in_executor(
                        None,
                        send_whatsapp,
                        phone,
                        f"Missed task: {task_name}",
                    )
                    logger.info("WhatsApp fallback sent for call %s", call_uuid)
                except Exception:
                    logger.exception("WhatsApp fallback failed for call %s", call_uuid)

    return Response(content=str(VoiceResponse()), media_type="application/xml")
