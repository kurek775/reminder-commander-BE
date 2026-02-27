from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.interaction_log import Channel, InteractionLog
from app.models.user import User
from app.schemas.interaction import InteractionLogResponse

router = APIRouter(prefix="/interactions", tags=["interactions"])


@router.get("/", response_model=list[InteractionLogResponse])
async def list_interactions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    channel: Channel | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list:
    query = select(InteractionLog).where(InteractionLog.user_id == current_user.id)
    if channel:
        query = query.where(InteractionLog.channel == channel)
    query = query.order_by(InteractionLog.created_at.desc()).offset(skip).limit(min(limit, 200))
    result = await db.execute(query)
    return [InteractionLogResponse.model_validate(row) for row in result.scalars().all()]
