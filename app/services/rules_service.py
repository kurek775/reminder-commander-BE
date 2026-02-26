import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tracker_rule import RuleType, TrackerRule
from app.schemas.rule import TrackerRuleCreate, TrackerRuleUpdate


async def create_rule(
    db: AsyncSession, user_id: uuid.UUID, data: TrackerRuleCreate
) -> TrackerRule:
    rule = TrackerRule(
        user_id=user_id,
        sheet_integration_id=data.sheet_integration_id,
        name=data.name,
        rule_type=data.rule_type,
        cron_schedule=data.cron_schedule,
        target_column=data.target_column,
        metric_name=data.metric_name,
        prompt_text=data.prompt_text,
        is_active=data.is_active,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


async def get_user_rules(
    db: AsyncSession,
    user_id: uuid.UUID,
    rule_type: RuleType | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[TrackerRule]:
    query = select(TrackerRule).where(TrackerRule.user_id == user_id)
    if rule_type is not None:
        query = query.where(TrackerRule.rule_type == rule_type)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_rule(
    db: AsyncSession, rule_id: uuid.UUID, user_id: uuid.UUID, data: TrackerRuleUpdate
) -> TrackerRule | None:
    result = await db.execute(
        select(TrackerRule).where(
            TrackerRule.id == rule_id,
            TrackerRule.user_id == user_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    await db.flush()
    await db.refresh(rule)
    return rule


async def delete_rule(
    db: AsyncSession, rule_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(TrackerRule).where(
            TrackerRule.id == rule_id,
            TrackerRule.user_id == user_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return False
    await db.delete(rule)
    await db.flush()
    return True
