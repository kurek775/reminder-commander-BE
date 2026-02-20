import enum
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RuleType(str, enum.Enum):
    health_tracker = "health_tracker"
    warlord = "warlord"


class TrackerRule(Base, TimestampMixin):
    __tablename__ = "tracker_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    sheet_integration_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("sheet_integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    rule_type: Mapped[RuleType] = mapped_column(
        sa.Enum(RuleType, name="ruletype"), nullable=False
    )
    cron_schedule: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    target_column: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    metric_name: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    prompt_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, server_default="true"
    )
