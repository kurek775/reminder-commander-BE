import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.interaction_log import InteractionLog
from app.models.user import User

router = APIRouter(prefix="/interactions", tags=["interactions"])


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


@router.get("/", response_model=list[InteractionLogResponse])
async def list_interactions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    channel: str | None = None,
) -> list:
    query = select(InteractionLog).where(InteractionLog.user_id == current_user.id)
    if channel:
        query = query.where(InteractionLog.channel == channel)
    query = query.order_by(InteractionLog.created_at.desc()).limit(50)
    result = await db.execute(query)
    return [InteractionLogResponse.from_orm(row) for row in result.scalars().all()]
