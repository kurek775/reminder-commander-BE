from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import create_access_token, decode_token
from app.db.base import get_db
from app.models.user import User
from app.schemas.auth import RefreshRequest, TokenResponse, UserResponse, WhatsappLinkRequest
from app.services.auth_service import (
    exchange_google_code,
    get_google_auth_url,
    issue_tokens,
    upsert_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/google")
async def google_login() -> dict:
    return {"auth_url": get_google_auth_url()}


@router.get("/google/callback")
async def google_callback(
    code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    try:
        google_data = await exchange_google_code(code)
        user = await upsert_user(db, google_data)
        tokens = issue_tokens(user)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authentication failed: {exc}",
        )

    access_token = tokens["access_token"]
    return RedirectResponse(
        url=f"http://localhost:4200/auth/callback?token={access_token}",
        status_code=302,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    try:
        payload = decode_token(body.refresh_token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    import uuid

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = await db.get(User, uuid.UUID(user_id_str))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return issue_tokens(user)


@router.patch("/whatsapp/link")
async def link_whatsapp(
    body: WhatsappLinkRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if body.phone != current_user.whatsapp_phone:
        existing = await db.execute(
            select(User).where(
                User.whatsapp_phone == body.phone,
                User.id != current_user.id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Phone number already in use")
    current_user.whatsapp_phone = body.phone
    db.add(current_user)
    return {"message": "WhatsApp phone linked", "phone": body.phone}
