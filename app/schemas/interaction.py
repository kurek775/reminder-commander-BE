import uuid

from pydantic import BaseModel

from app.models.interaction_log import InteractionLog


class InteractionLogResponse(BaseModel):
    id: uuid.UUID
    tracker_rule_id: uuid.UUID | None
    direction: str
    channel: str
    message_content: str | None
    status: str
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj: InteractionLog) -> "InteractionLogResponse":
        return cls(
            id=obj.id,
            tracker_rule_id=obj.tracker_rule_id,
            direction=obj.direction.value,
            channel=obj.channel.value,
            message_content=obj.message_content,
            status=obj.status.value,
            created_at=obj.created_at.isoformat(),
        )
