import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SheetIntegration(Base, TimestampMixin):
    __tablename__ = "sheet_integrations"
    __table_args__ = (
        UniqueConstraint("user_id", "google_sheet_id", name="uq_sheet_user_sheet"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    google_sheet_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    sheet_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    encrypted_access_token: Mapped[str] = mapped_column(sa.Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(sa.Text, nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default="true"
    )
    display_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
