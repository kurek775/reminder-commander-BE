import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.base import get_db
from app.models.sheet_integration import SheetIntegration
from app.models.user import User
from app.schemas.sheet import (
    SheetIntegrationResponse,
    SheetIntegrationUpdate,
    SheetsAuthUrlResponse,
)
from app.services.sheets_service import (
    disconnect_sheet,
    exchange_sheets_code,
    get_create_sheet_auth_url,
    get_sheet_headers,
    get_sheet_preview,
    get_sheet_rule_count,
    get_sheets_auth_url,
    get_user_integrations,
    update_sheet_integration,
)

router = APIRouter(prefix="/sheets", tags=["sheets"])


@router.get("/connect", response_model=SheetsAuthUrlResponse)
async def connect_sheet(
    sheet_url: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    return {"auth_url": get_sheets_auth_url(str(current_user.id), sheet_url)}


@router.get("/create", response_model=SheetsAuthUrlResponse)
async def create_sheet(
    title: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title must not be empty")
    return {"auth_url": get_create_sheet_auth_url(str(current_user.id), title.strip())}


@router.get("/callback")
async def sheets_callback(
    code: str,
    state: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    try:
        await exchange_sheets_code(db, code, state)
        return RedirectResponse(url=f"{settings.frontend_url}/sheets", status_code=302)
    except Exception:
        return RedirectResponse(url=f"{settings.frontend_url}/sheets?error=true", status_code=302)


@router.get("/", response_model=list[SheetIntegrationResponse])
async def list_sheets(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list:
    return await get_user_integrations(db, current_user.id)


@router.get("/{integration_id}/headers")
async def get_integration_headers(
    integration_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    integration = await db.get(SheetIntegration, integration_id)
    if not integration or integration.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sheet integration not found")
    return await get_sheet_headers(db, integration)


@router.get("/{integration_id}/rule-count")
async def get_rule_count(
    integration_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    integration = await db.get(SheetIntegration, integration_id)
    if not integration or integration.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sheet integration not found")
    count = await get_sheet_rule_count(db, integration_id)
    return {"count": count}


@router.get("/{integration_id}/preview")
async def preview_sheet(
    integration_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    integration = await db.get(SheetIntegration, integration_id)
    if not integration or integration.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sheet integration not found")
    return await get_sheet_preview(db, integration)


@router.patch("/{integration_id}", response_model=SheetIntegrationResponse)
async def patch_sheet(
    integration_id: uuid.UUID,
    body: SheetIntegrationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SheetIntegration:
    result = await update_sheet_integration(
        db, integration_id, current_user.id, body.display_name
    )
    if not result:
        raise HTTPException(status_code=404, detail="Sheet integration not found")
    return result


@router.delete("/{integration_id}", status_code=204)
async def delete_sheet(
    integration_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    success = await disconnect_sheet(db, integration_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Sheet integration not found")
