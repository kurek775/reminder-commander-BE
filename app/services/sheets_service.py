import base64
import hashlib
import hmac
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.config import settings
from app.core.encryption import decrypt, encrypt
from app.models.sheet_integration import SheetIntegration
from app.models.tracker_rule import TrackerRule

logger = logging.getLogger(__name__)

# HTTP timeout for Google API calls (M6)
_HTTP_TIMEOUT = 30.0


def _sign_state(payload: str) -> str:
    """HMAC-sign a state payload and return base64(payload|signature)."""
    sig = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    combined = json.dumps({"payload": payload, "sig": sig})
    return base64.urlsafe_b64encode(combined.encode()).decode()


def _verify_state(state: str) -> dict:
    """Verify HMAC-signed state and return the decoded payload dict."""
    combined = json.loads(base64.urlsafe_b64decode(state).decode())
    payload = combined["payload"]
    sig = combined["sig"]
    expected = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Invalid OAuth state signature")
    return json.loads(payload)


def _build_oauth_url(state: str) -> str:
    """Build the Google OAuth URL with the given signed state."""
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


def get_sheets_auth_url(user_id: str, sheet_url: str) -> str:
    payload = json.dumps({"user_id": user_id, "sheet_url": sheet_url, "action": "connect"})
    return _build_oauth_url(_sign_state(payload))


def get_create_sheet_auth_url(user_id: str, title: str) -> str:
    payload = json.dumps({"user_id": user_id, "title": title, "action": "create"})
    return _build_oauth_url(_sign_state(payload))


async def _exchange_tokens(code: str) -> dict:
    """Exchange an authorization code for tokens."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
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
        return response.json()


async def create_sheet_via_api(
    db: AsyncSession,
    user_id: str,
    title: str,
    access_token: str,
    refresh_token: str,
    token_expires_at: datetime,
) -> SheetIntegration:
    """Create a new Google Sheet via the Sheets API and store the integration."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.post(
            "https://sheets.googleapis.com/v4/spreadsheets",
            json={"properties": {"title": title}},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        data = r.json()

    spreadsheet_id = data["spreadsheetId"]
    sheet_name = data.get("properties", {}).get("title", title)

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


async def exchange_sheets_code(db: AsyncSession, code: str, state: str) -> SheetIntegration:
    decoded = _verify_state(state)
    user_id: str = decoded["user_id"]
    action: str = decoded.get("action", "connect")

    tokens = await _exchange_tokens(code)
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 3600)
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if action == "create":
        title: str = decoded["title"]
        return await create_sheet_via_api(
            db, user_id, title, access_token, refresh_token, token_expires_at
        )

    # Default: connect existing sheet
    sheet_url: str = decoded.get("sheet_url", "")
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", sheet_url)
    spreadsheet_id = match.group(1) if match else ""

    sheet_name = spreadsheet_id
    if spreadsheet_id and access_token:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
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
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
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
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
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


@dataclass
class WarlordTask:
    row_index: int
    task_name: str
    deadline: date


async def get_warlord_tasks(
    db: AsyncSession,
    integration: SheetIntegration,
) -> list[WarlordTask]:
    """Return sheet rows where deadline < today and done != TRUE.

    Expected sheet layout (row 1 = headers, skipped):
      Col A: task name
      Col B: deadline date (YYYY-MM-DD)
      Col C: done (TRUE / FALSE checkbox)
    """
    access_token = await _refresh_token_if_needed(db, integration)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{integration.google_sheet_id}/values/A:C"
    )
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        data = r.json()

    rows = data.get("values", [])
    today = date.today()
    missed: list[WarlordTask] = []

    for i, row in enumerate(rows[1:], start=2):  # skip header, 1-indexed
        task_name = row[0].strip() if len(row) > 0 else ""
        deadline_str = row[1].strip() if len(row) > 1 else ""
        done = row[2].strip() if len(row) > 2 else "FALSE"

        if not task_name or not deadline_str:
            continue

        try:
            deadline = date.fromisoformat(deadline_str)
        except ValueError:
            continue

        if deadline < today and done.upper() != "TRUE":
            missed.append(WarlordTask(row_index=i, task_name=task_name, deadline=deadline))

    return missed


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
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.post(
            url,
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": [[value]]},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()


# --- Phase 2: Disconnect Sheet ---


async def get_sheet_rule_count(db: AsyncSession, integration_id: uuid.UUID) -> int:
    """Count TrackerRules referencing this sheet integration."""
    result = await db.execute(
        select(func.count()).where(TrackerRule.sheet_integration_id == integration_id)
    )
    return result.scalar_one()


async def disconnect_sheet(
    db: AsyncSession, integration_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Soft-delete a sheet integration. Returns True if found and deactivated."""
    integration = await db.get(SheetIntegration, integration_id)
    if not integration or integration.user_id != user_id:
        return False
    integration.is_active = False
    await db.flush()
    return True


# --- Phase 3: Sheet Preview ---


async def get_sheet_preview(
    db: AsyncSession,
    integration: SheetIntegration,
    max_rows: int = 5,
    max_cols: int = 10,
) -> dict:
    """Read a small preview of the sheet: headers + first N data rows."""
    access_token = await _refresh_token_if_needed(db, integration)
    last_col = _col_idx_to_letter(max_cols - 1)
    range_notation = f"A1:{last_col}{max_rows + 1}"
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{integration.google_sheet_id}/values/{range_notation}"
    )
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        data = r.json()

    all_rows = data.get("values", [])
    headers = all_rows[0] if all_rows else []
    rows = all_rows[1:] if len(all_rows) > 1 else []

    # Get total row count from sheet metadata
    meta_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{integration.google_sheet_id}"
    )
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        r = await client.get(
            meta_url,
            params={"fields": "sheets.properties.gridProperties.rowCount"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        meta = r.json()

    sheets = meta.get("sheets", [])
    total_rows = sheets[0]["properties"]["gridProperties"]["rowCount"] if sheets else 0

    return {"headers": headers, "rows": rows, "total_rows": total_rows}


# --- Phase 4: Rename Sheet (Display Name) ---


async def update_sheet_integration(
    db: AsyncSession,
    integration_id: uuid.UUID,
    user_id: uuid.UUID,
    display_name: str | None,
) -> SheetIntegration | None:
    """Update display_name of a sheet integration. Returns None if not found."""
    integration = await db.get(SheetIntegration, integration_id)
    if not integration or integration.user_id != user_id:
        return None
    integration.display_name = display_name
    await db.flush()
    await db.refresh(integration)
    return integration
