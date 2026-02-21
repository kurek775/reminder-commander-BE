import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.user import User
from app.schemas.rule import TrackerRuleCreate, TrackerRuleResponse, TrackerRuleUpdate
from app.services.rules_service import create_rule, delete_rule, get_user_rules, update_rule_prompt

router = APIRouter(prefix="/rules", tags=["rules"])


@router.post("/", response_model=TrackerRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_tracker_rule(
    payload: TrackerRuleCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrackerRuleResponse:
    return await create_rule(db, current_user.id, payload)


@router.get("/", response_model=list[TrackerRuleResponse])
async def list_tracker_rules(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list:
    return await get_user_rules(db, current_user.id)


@router.patch("/{rule_id}", response_model=TrackerRuleResponse)
async def update_tracker_rule(
    rule_id: uuid.UUID,
    payload: TrackerRuleUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrackerRuleResponse:
    rule = await update_rule_prompt(db, rule_id, current_user.id, payload.prompt_text)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tracker_rule(
    rule_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    found = await delete_rule(db, rule_id, current_user.id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
