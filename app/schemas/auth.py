import uuid
from typing import Optional

from pydantic import BaseModel


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
