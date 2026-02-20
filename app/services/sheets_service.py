import uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.encryption import decrypt, encrypt
from app.models.sheet_integration import SheetIntegration


def get_sheets_auth_url(user_id: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_sheets_redirect_uri,
        "response_type": "code",
        "scope": (
            "https://www.googleapis.com/auth/spreadsheets "
            "https://www.googleapis.com/auth/drive.readonly"
        ),
        "access_type": "offline",
        "prompt": "consent",
        "state": user_id,
    }
    return f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"


async def exchange_sheets_code(db: AsyncSession, code: str, state: str) -> SheetIntegration:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_sheets_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        tokens = response.json()

    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)

    token_expires_at = datetime.now(timezone.utc).replace(microsecond=0)
    token_expires_at = token_expires_at.replace(
        second=token_expires_at.second + expires_in
    )

    integration = SheetIntegration(
        user_id=uuid.UUID(state),
        google_sheet_id="",
        sheet_name="My Sheet",
        encrypted_access_token=encrypt(access_token),
        encrypted_refresh_token=encrypt(refresh_token) if refresh_token else encrypt(""),
        token_expires_at=token_expires_at,
    )
    db.add(integration)
    await db.flush()
    await db.refresh(integration)
    return integration


async def get_user_integrations(db: AsyncSession, user_id: uuid.UUID) -> list[SheetIntegration]:
    result = await db.execute(
        select(SheetIntegration).where(
            SheetIntegration.user_id == user_id,
            SheetIntegration.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


def get_credentials(sheet_integration: SheetIntegration) -> dict:
    return {
        "access_token": decrypt(sheet_integration.encrypted_access_token),
        "refresh_token": decrypt(sheet_integration.encrypted_refresh_token),
        "token_expires_at": sheet_integration.token_expires_at,
    }
