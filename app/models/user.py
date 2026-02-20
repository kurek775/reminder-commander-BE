import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    google_id: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    picture_url: Mapped[str | None] = mapped_column(sa.String(2048), nullable=True)
    whatsapp_phone: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    whatsapp_verified: Mapped[bool] = mapped_column(sa.Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True, server_default="true")
