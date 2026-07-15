"""add SCADA snapshot availability timestamp

Revision ID: fc39e4f1d6a3
Revises: fb28d3e0c5f2
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "fc39e4f1d6a3"
down_revision: str | None = "fb28d3e0c5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scada_grid_snapshots") as batch_op:
        batch_op.add_column(
            sa.Column("available_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            "idx_scada_grid_snapshots_available_at",
            ["available_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("scada_grid_snapshots") as batch_op:
        batch_op.drop_index("idx_scada_grid_snapshots_available_at")
        batch_op.drop_column("available_at")
