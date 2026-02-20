from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
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
    sheet_url: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    return {"auth_url": get_sheets_auth_url(str(current_user.id), sheet_url)}


@router.get("/callback")
async def sheets_callback(
    code: str,
    state: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    try:
        await exchange_sheets_code(db, code, state)
        return RedirectResponse(url="http://localhost:4200/sheets", status_code=302)
    except Exception:
        return RedirectResponse(url="http://localhost:4200/sheets?error=true", status_code=302)


@router.get("/", response_model=list[SheetIntegrationResponse])
async def list_sheets(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list:
    return await get_user_integrations(db, current_user.id)
