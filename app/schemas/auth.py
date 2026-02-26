import re
import uuid
from typing import Optional

from pydantic import BaseModel, field_validator

_E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    picture_url: Optional[str] = None
    whatsapp_phone: Optional[str] = None
    whatsapp_verified: bool
    is_active: bool

    model_config = {"from_attributes": True}


class WhatsappLinkRequest(BaseModel):
    phone: str  # E.164 format, e.g. "+48123456789"

    @field_validator("phone")
    @classmethod
    def validate_e164(cls, v: str) -> str:
        if not _E164_PATTERN.match(v):
            raise ValueError("Phone number must be in E.164 format (e.g. +48123456789)")
        return v
