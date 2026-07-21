"""add forecast quantiles and model evidence

Revision ID: 3d0e1f2a4b73
Revises: 2c9d0e1f3a62
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "3d0e1f2a4b73"
down_revision: str | None = "2c9d0e1f3a62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(sa.Column("p10_demand_mw", sa.Float(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("p50_demand_mw", sa.Float(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("p90_demand_mw", sa.Float(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("training_start_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("training_end_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("feature_importance", sa.Text(), nullable=False, server_default="{}"))
        batch_op.add_column(sa.Column("fallback_reason", sa.Text(), nullable=True))
        batch_op.alter_column(
            "confidence_level",
            existing_type=sa.Float(),
            nullable=False,
            server_default="0.8",
        )


def _drop_columns(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            "confidence_level",
            existing_type=sa.Float(),
            nullable=False,
            server_default="0.9",
        )
        batch_op.drop_column("fallback_reason")
        batch_op.drop_column("feature_importance")
        batch_op.drop_column("training_end_at")
        batch_op.drop_column("training_start_at")
        batch_op.drop_column("p90_demand_mw")
        batch_op.drop_column("p50_demand_mw")
        batch_op.drop_column("p10_demand_mw")


def upgrade() -> None:
    _add_columns("demand_forecast_results")
    _add_columns("scada_replay_forecast_results")


def downgrade() -> None:
    _drop_columns("scada_replay_forecast_results")
    _drop_columns("demand_forecast_results")
