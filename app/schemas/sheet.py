import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SheetsAuthUrlResponse(BaseModel):
    auth_url: str


class SheetIntegrationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    google_sheet_id: str
    sheet_name: str
    is_active: bool
    token_expires_at: Optional[datetime] = None
    display_name: Optional[str] = None

    model_config = {"from_attributes": True}


class SheetIntegrationUpdate(BaseModel):
    display_name: Optional[str] = None
