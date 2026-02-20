import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.tracker_rule import RuleType


class TrackerRuleCreate(BaseModel):
    sheet_integration_id: uuid.UUID
    name: str
    rule_type: RuleType = RuleType.health_tracker
    cron_schedule: str
    target_column: str
    metric_name: str | None = None
    prompt_text: str
    is_active: bool = True


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
