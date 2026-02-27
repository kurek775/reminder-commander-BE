"""add display_name to sheet_integrations

Revision ID: 004
Revises: 003
Create Date: 2026-02-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sheet_integrations", sa.Column("display_name", sa.String(255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("sheet_integrations", "display_name")
