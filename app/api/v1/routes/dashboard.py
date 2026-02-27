from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.interaction_log import InteractionLog
from app.models.sheet_integration import SheetIntegration
from app.models.tracker_rule import RuleType, TrackerRule
from app.models.user import User
from app.schemas.dashboard import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardSummary:
    # Combine health + warlord rule counts in a single query
    rule_counts = await db.execute(
        select(
            func.count(case((TrackerRule.rule_type == RuleType.health_tracker, 1))),
            func.count(case((TrackerRule.rule_type == RuleType.warlord, 1))),
        )
        .select_from(TrackerRule)
        .where(
            TrackerRule.user_id == current_user.id,
            TrackerRule.is_active.is_(True),
        )
    )
    health_count, warlord_count = rule_counts.one()

    sheets = await db.execute(
        select(func.count())
        .select_from(SheetIntegration)
        .where(
            SheetIntegration.user_id == current_user.id,
            SheetIntegration.is_active.is_(True),
        )
    )
    interactions = await db.execute(
        select(func.count())
        .select_from(InteractionLog)
        .where(InteractionLog.user_id == current_user.id)
    )

    return DashboardSummary(
        health_rules_active=health_count,
        warlord_rules_active=warlord_count,
        sheets_connected=sheets.scalar_one(),
        has_whatsapp=bool(current_user.whatsapp_phone),
        recent_interactions=interactions.scalar_one(),
    )
