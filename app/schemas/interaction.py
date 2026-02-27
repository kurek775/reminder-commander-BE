import uuid

from pydantic import BaseModel


class InteractionLogResponse(BaseModel):
    id: uuid.UUID
    tracker_rule_id: uuid.UUID | None
    direction: str
    channel: str
    message_content: str | None
    status: str
    created_at: str

    model_config = {"from_attributes": True}
