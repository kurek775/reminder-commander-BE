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


async def _refresh_token_if_needed(
    db: AsyncSession, integration: SheetIntegration
) -> str:
    """Return a valid access token, refreshing via Google if within 60s of expiry."""
    now = datetime.now(timezone.utc)
    expires_at = integration.token_expires_at
    if expires_at is None or (expires_at - now).total_seconds() < 60:
        refresh_token = decrypt(integration.encrypted_refresh_token)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            tokens = response.json()

        new_access_token = tokens.get("access_token", "")
        expires_in = tokens.get("expires_in", 3600)
        integration.encrypted_access_token = encrypt(new_access_token)
        integration.token_expires_at = now + timedelta(seconds=expires_in)
        await db.flush()
        return new_access_token

    return decrypt(integration.encrypted_access_token)


def _col_idx_to_letter(idx: int) -> str:
    """Convert 0-based column index to letter (0→A, 1→B, 25→Z, 26→AA)."""
    result = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        result = chr(ord("A") + rem) + result
    return result


async def get_sheet_headers(
    db: AsyncSession,
    integration: SheetIntegration,
) -> list[dict]:
    """Read row 1 of the sheet and return non-empty column headers with their letter."""
    access_token = await _refresh_token_if_needed(db, integration)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{integration.google_sheet_id}/values/1:1"
    )
    async with httpx.AsyncClient() as client:
        r = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        data = r.json()

    row = data.get("values", [[]])[0] if data.get("values") else []
    headers = []
    for idx, cell in enumerate(row):
        if cell and str(cell).strip():
            headers.append({"column": _col_idx_to_letter(idx), "name": str(cell).strip()})
    return headers


async def append_to_sheet(
    db: AsyncSession,
    integration: SheetIntegration,
    target_column: str,
    value: str,
) -> None:
    """Append a value to the specified column of the Google Sheet."""
    access_token = await _refresh_token_if_needed(db, integration)
    range_notation = f"{target_column}:{target_column}"
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{integration.google_sheet_id}/values/{range_notation}:append"
    )
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": [[value]]},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
