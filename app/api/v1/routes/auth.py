import json
import logging
import uuid
import uuid as uuid_mod
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.core.redis import get_redis
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_CODE_TTL = 60  # seconds


@router.get("/google")
async def google_login() -> dict:
    return {"auth_url": get_google_auth_url()}


@router.get("/google/callback")
async def google_callback(
    code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    r: aioredis.Redis = Depends(get_redis),
) -> RedirectResponse:
    try:
        google_data = await exchange_google_code(code)
        user = await upsert_user(db, google_data)
        tokens = issue_tokens(user)
    except Exception:
        logger.exception("Google authentication failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google authentication failed",
        )

    # H9: Store tokens behind a short-lived auth code instead of putting JWT in URL
    auth_code = str(uuid_mod.uuid4())
    await r.setex(f"auth_code:{auth_code}", AUTH_CODE_TTL, json.dumps(tokens))

    return RedirectResponse(
        url=f"{settings.frontend_url}/auth/callback?code={auth_code}",
        status_code=302,
    )


class ExchangeRequest(BaseModel):
    code: str


@router.post("/exchange", response_model=TokenResponse)
async def exchange_auth_code(
    body: ExchangeRequest,
    r: aioredis.Redis = Depends(get_redis),
) -> dict:
    """H9: Exchange a short-lived auth code for JWT tokens."""
    raw = await r.getdel(f"auth_code:{body.code}")
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired auth code",
        )
    return json.loads(raw)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
async def refresh_token(
    request: Request,
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

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = await db.get(User, uuid.UUID(user_id_str))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return issue_tokens(user)


@router.patch("/whatsapp/link")
@limiter.limit("10/minute")
async def link_whatsapp(
    request: Request,
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
