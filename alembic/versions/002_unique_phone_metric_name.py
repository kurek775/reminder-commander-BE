"""add unique phone constraint and metric_name column

Revision ID: 002
Revises: 001
Create Date: 2026-02-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deduplicate: for each phone number keep the earliest account, null out the rest
    op.execute("""
        UPDATE users SET whatsapp_phone = NULL
        WHERE id NOT IN (
            SELECT DISTINCT ON (whatsapp_phone) id
            FROM users
            WHERE whatsapp_phone IS NOT NULL
            ORDER BY whatsapp_phone, created_at
        )
        AND whatsapp_phone IS NOT NULL
    """)
    op.create_unique_constraint("uq_users_whatsapp_phone", "users", ["whatsapp_phone"])
    op.add_column("tracker_rules", sa.Column("metric_name", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("tracker_rules", "metric_name")
    op.drop_constraint("uq_users_whatsapp_phone", "users", type_="unique")
