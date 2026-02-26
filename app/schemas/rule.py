import uuid
from datetime import datetime

from croniter import croniter
from pydantic import BaseModel, field_validator

from app.models.tracker_rule import RuleType


def _validate_cron(v: str) -> str:
    if not croniter.is_valid(v):
        raise ValueError(f"Invalid cron expression: {v}")
    return v


class TrackerRuleCreate(BaseModel):
    sheet_integration_id: uuid.UUID
    name: str
    rule_type: RuleType = RuleType.health_tracker
    cron_schedule: str
    target_column: str
    metric_name: str | None = None
    prompt_text: str
    is_active: bool = True

    @field_validator("cron_schedule")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        return _validate_cron(v)


class TrackerRuleUpdate(BaseModel):
    name: str | None = None
    cron_schedule: str | None = None
    prompt_text: str | None = None
    is_active: bool | None = None

    @field_validator("cron_schedule")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_cron(v)
        return v


class TrackerRuleResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    sheet_integration_id: uuid.UUID
    name: str
    rule_type: RuleType
    cron_schedule: str
    target_column: str
    metric_name: str | None = None
    prompt_text: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
