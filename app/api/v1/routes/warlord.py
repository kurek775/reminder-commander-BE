import uuid
from datetime import date
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.db.base import get_db
from app.models.tracker_rule import RuleType, TrackerRule
from app.models.sheet_integration import SheetIntegration
from app.models.user import User
from app.services.sheets_service import _refresh_token_if_needed, get_warlord_tasks

router = APIRouter(prefix="/warlord", tags=["warlord"])


@router.post("/trigger", status_code=200)
@limiter.limit("5/minute")
async def trigger_warlord_scan(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Immediately queue the warlord sheet scanner Celery task."""
    from app.worker.tasks import scan_warlord_sheets  # lazy: celery not available in tests

    scan_warlord_sheets.delay(True)
    return {"status": "triggered"}


@router.get("/debug/{rule_id}")
async def debug_warlord_rule(
    rule_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return raw sheet rows and parsed missed tasks for a warlord rule."""
    result = await db.execute(
        select(TrackerRule, SheetIntegration)
        .join(SheetIntegration, TrackerRule.sheet_integration_id == SheetIntegration.id)
        .where(TrackerRule.id == rule_id, TrackerRule.user_id == current_user.id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule, integration = row

    access_token = await _refresh_token_if_needed(db, integration)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/"
        f"{integration.google_sheet_id}/values/A:C"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
        raw = r.json()

    missed = await get_warlord_tasks(db, integration)
    today = date.today()

    return {
        "today": str(today),
        "raw_rows": raw.get("values", []),
        "missed_tasks": [
            {"row": t.row_index, "task": t.task_name, "deadline": str(t.deadline)}
            for t in missed
        ],
    }
