import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tracker_rule import TrackerRule
from app.schemas.rule import TrackerRuleCreate


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


async def get_user_rules(db: AsyncSession, user_id: uuid.UUID) -> list[TrackerRule]:
    result = await db.execute(
        select(TrackerRule).where(TrackerRule.user_id == user_id)
    )
    return list(result.scalars().all())


async def update_rule_prompt(
    db: AsyncSession, rule_id: uuid.UUID, user_id: uuid.UUID, prompt_text: str
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
    rule.prompt_text = prompt_text
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
