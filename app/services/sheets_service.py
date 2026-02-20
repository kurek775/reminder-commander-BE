import base64
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.encryption import decrypt, encrypt
from app.models.sheet_integration import SheetIntegration


def get_sheets_auth_url(user_id: str, sheet_url: str) -> str:
    state = base64.b64encode(
        json.dumps({"user_id": user_id, "sheet_url": sheet_url}).encode()
    ).decode()
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
        "state": state,
    }
    return f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"


async def exchange_sheets_code(db: AsyncSession, code: str, state: str) -> SheetIntegration:
    decoded = json.loads(base64.b64decode(state).decode())
    user_id: str = decoded["user_id"]
    sheet_url: str = decoded["sheet_url"]

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheet_url)
    spreadsheet_id = match.group(1) if match else ""

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

    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    sheet_name = spreadsheet_id
    if spreadsheet_id and access_token:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}",
                params={"fields": "properties.title"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            sheet_name = r.json().get("properties", {}).get("title", spreadsheet_id)

    integration = SheetIntegration(
        user_id=uuid.UUID(user_id),
        google_sheet_id=spreadsheet_id,
        sheet_name=sheet_name,
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
