"""add cutoff-safe SCADA replay forecasts

Revision ID: fd4a5b2c7e19
Revises: fc39e4f1d6a3
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "fd4a5b2c7e19"
down_revision: str | None = "fc39e4f1d6a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scada_replay_forecast_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_cursor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("forecast_demand_mw", sa.Float(), nullable=False),
        sa.Column("forecast_uncertainty_mw", sa.Float(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("baseline_name", sa.String(length=100), nullable=False),
        sa.Column("baseline_forecast_mw", sa.Float(), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("mae", sa.Float(), nullable=False),
        sa.Column("rmse", sa.Float(), nullable=False),
        sa.Column("residual_std", sa.Float(), nullable=False),
        sa.Column("training_rows", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scada_replay_forecast_results_source_cursor_at",
        "scada_replay_forecast_results",
        ["source_cursor_at"],
        unique=False,
    )
    op.create_index(
        "idx_scada_replay_forecast_cursor_horizon",
        "scada_replay_forecast_results",
        ["source_cursor_at", "horizon_hours"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_scada_replay_forecast_cursor_horizon",
        table_name="scada_replay_forecast_results",
    )
    op.drop_index(
        "ix_scada_replay_forecast_results_source_cursor_at",
        table_name="scada_replay_forecast_results",
    )
    op.drop_table("scada_replay_forecast_results")
