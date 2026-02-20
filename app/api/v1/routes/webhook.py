import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.interaction_log import (
    Channel,
    Direction,
    InteractionLog,
    MessageStatus,
)
from app.models.tracker_rule import TrackerRule
from app.models.user import User
from app.services.sheets_service import append_to_sheet
from app.models.sheet_integration import SheetIntegration

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response/>'


@router.post("/twilio")
async def twilio_webhook(
    from_field: Annotated[str, Form(alias="From")],
    body: Annotated[str, Form(alias="Body")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    phone = from_field.replace("whatsapp:", "").strip()

    # 1. Find most recent outbound log for any user with this phone number
    log_result = await db.execute(
        select(InteractionLog)
        .join(User, InteractionLog.user_id == User.id)
        .where(
            User.whatsapp_phone == phone,
            User.is_active.is_(True),
            InteractionLog.direction == Direction.outbound,
            InteractionLog.tracker_rule_id.is_not(None),
        )
        .order_by(InteractionLog.created_at.desc())
        .limit(1)
    )
    outbound_log = log_result.scalar_one_or_none()
    if outbound_log is None:
        logger.info("Twilio webhook: no outbound log for phone %s", phone)
        return Response(content=EMPTY_TWIML, media_type="application/xml")

    # 1b. Check if this outbound has already been answered
    already_answered = await db.execute(
        select(InteractionLog).where(
            InteractionLog.tracker_rule_id == outbound_log.tracker_rule_id,
            InteractionLog.user_id == outbound_log.user_id,
            InteractionLog.direction == Direction.inbound,
            InteractionLog.created_at > outbound_log.created_at,
        ).limit(1)
    )
    if already_answered.scalar_one_or_none() is not None:
        logger.info(
            "Twilio webhook: already answered reminder for rule %s, ignoring",
            outbound_log.tracker_rule_id,
        )
        return Response(content=EMPTY_TWIML, media_type="application/xml")

    # 2. Load the user who owns this log
    user_result = await db.execute(
        select(User).where(User.id == outbound_log.user_id)
    )
    user = user_result.scalar_one()

    # 3. Load TrackerRule
    rule_result = await db.execute(
        select(TrackerRule).where(TrackerRule.id == outbound_log.tracker_rule_id)
    )
    rule = rule_result.scalar_one_or_none()

    # 4. Create inbound InteractionLog
    inbound_log = InteractionLog(
        user_id=user.id,
        tracker_rule_id=outbound_log.tracker_rule_id,
        direction=Direction.inbound,
        channel=Channel.whatsapp,
        message_content=body,
        status=MessageStatus.received,
    )
    db.add(inbound_log)
    await db.flush()

    # 5. Append to sheet (soft errors — log but don't fail)
    if rule is not None:
        try:
            integration_result = await db.execute(
                select(SheetIntegration).where(
                    SheetIntegration.id == rule.sheet_integration_id
                )
            )
            integration = integration_result.scalar_one_or_none()
            if integration is not None:
                await append_to_sheet(db, integration, rule.target_column, body)
        except Exception:
            logger.exception("Failed to append to sheet for user %s", user.id)

    return Response(content=EMPTY_TWIML, media_type="application/xml")
