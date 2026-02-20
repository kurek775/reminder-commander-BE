from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.user import User
from app.schemas.sheet import SheetIntegrationResponse, SheetsAuthUrlResponse
from app.services.sheets_service import (
    exchange_sheets_code,
    get_sheets_auth_url,
    get_user_integrations,
)

router = APIRouter(prefix="/sheets", tags=["sheets"])


@router.get("/connect", response_model=SheetsAuthUrlResponse)
async def connect_sheet(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    return {"auth_url": get_sheets_auth_url(str(current_user.id))}


@router.get("/callback")
async def sheets_callback(
    code: str,
    state: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    await exchange_sheets_code(db, code, state)
    return {"message": "Sheet connected successfully"}


@router.get("/", response_model=list[SheetIntegrationResponse])
async def list_sheets(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list:
    return await get_user_integrations(db, current_user.id)
