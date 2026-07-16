"""add corrected spinning reserve to persisted grid snapshots

Revision ID: 0a7b8c9d1e40
Revises: ff6c7d8e9a30
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0a7b8c9d1e40"
down_revision: str | None = "ff6c7d8e9a30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("grid_data") as batch_op:
        batch_op.add_column(
            sa.Column("spinning_reserve_mw", sa.Float(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("spinning_reserve_source", sa.String(length=100), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("grid_data") as batch_op:
        batch_op.drop_column("spinning_reserve_source")
        batch_op.drop_column("spinning_reserve_mw")
