"""add target-relative demand history features

Revision ID: 4e1f2a3b5c84
Revises: 3d0e1f2a4b73
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "4e1f2a3b5c84"
down_revision: str | None = "3d0e1f2a4b73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TARGET_HISTORY_COLUMNS = (
    "target_lag_24h_demand_mw",
    "target_lag_48h_demand_mw",
    "target_lag_168h_demand_mw",
    "target_same_hour_7d_average_mw",
)


def upgrade() -> None:
    with op.batch_alter_table("forecast_training_rows") as batch_op:
        for column_name in TARGET_HISTORY_COLUMNS:
            batch_op.add_column(sa.Column(column_name, sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("forecast_training_rows") as batch_op:
        for column_name in reversed(TARGET_HISTORY_COLUMNS):
            batch_op.drop_column(column_name)
