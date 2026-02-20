import enum
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Direction(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class Channel(str, enum.Enum):
    whatsapp = "whatsapp"
    voice = "voice"


class MessageStatus(str, enum.Enum):
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    received = "received"


class InteractionLog(Base):
    __tablename__ = "interaction_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    tracker_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("tracker_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    direction: Mapped[Direction] = mapped_column(
        sa.Enum(Direction, name="direction"), nullable=False
    )
    channel: Mapped[Channel] = mapped_column(
        sa.Enum(Channel, name="channel"), nullable=False
    )
    message_content: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[MessageStatus] = mapped_column(
        sa.Enum(MessageStatus, name="messagestatus"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now(),
    )
