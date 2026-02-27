"""add index and unique constraint to sheet_integrations

Revision ID: 003
Revises: 002
Create Date: 2026-02-27 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_sheet_integrations_user_id", "sheet_integrations", ["user_id"])
    # Deduplicate before adding unique constraint
    op.execute("""
        DELETE FROM sheet_integrations
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id, google_sheet_id) id
            FROM sheet_integrations
            ORDER BY user_id, google_sheet_id, created_at
        )
    """)
    op.create_unique_constraint(
        "uq_sheet_user_sheet", "sheet_integrations", ["user_id", "google_sheet_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_sheet_user_sheet", "sheet_integrations", type_="unique")
    op.drop_index("ix_sheet_integrations_user_id", table_name="sheet_integrations")
