"""add SCADA readiness and audit fields

Revision ID: b318a8cf1210
Revises: 87c46bdfdad4
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa


revision = "b318a8cf1210"
down_revision = "87c46bdfdad4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("weather_observations", sa.Column("snapshot_id", sa.String(36), nullable=True))
    op.create_index("ix_weather_observations_snapshot_id", "weather_observations", ["snapshot_id"])

    op.add_column("grid_data", sa.Column("snapshot_id", sa.String(36), nullable=True))
    op.add_column("grid_data", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "grid_data",
        sa.Column("quality_status", sa.String(16), nullable=False, server_default="GOOD"),
    )
    op.create_index("ix_grid_data_snapshot_id", "grid_data", ["snapshot_id"])

    op.add_column("generation_units", sa.Column("snapshot_id", sa.String(36), nullable=True))
    op.add_column("generation_units", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "generation_units",
        sa.Column("quality_status", sa.String(16), nullable=False, server_default="GOOD"),
    )
    op.add_column("generation_units", sa.Column("source_tag", sa.String(255), nullable=True))
    op.create_index("ix_generation_units_snapshot_id", "generation_units", ["snapshot_id"])

    op.add_column("probability_results", sa.Column("snapshot_id", sa.String(36), nullable=True))
    op.add_column(
        "probability_results",
        sa.Column("engine_version", sa.String(32), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "probability_results",
        sa.Column("weather_observed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "probability_results",
        sa.Column("grid_observed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("probability_results", sa.Column("weather_source", sa.String(100), nullable=True))
    op.add_column("probability_results", sa.Column("grid_source", sa.String(100), nullable=True))
    op.add_column(
        "probability_results",
        sa.Column("input_quality_status", sa.String(16), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column(
        "probability_results",
        sa.Column("calibration_scenario", sa.String(128), nullable=True),
    )
    op.create_index("ix_probability_results_snapshot_id", "probability_results", ["snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_probability_results_snapshot_id", table_name="probability_results")
    op.drop_column("probability_results", "calibration_scenario")
    op.drop_column("probability_results", "input_quality_status")
    op.drop_column("probability_results", "grid_source")
    op.drop_column("probability_results", "weather_source")
    op.drop_column("probability_results", "grid_observed_at")
    op.drop_column("probability_results", "weather_observed_at")
    op.drop_column("probability_results", "engine_version")
    op.drop_column("probability_results", "snapshot_id")

    op.drop_index("ix_generation_units_snapshot_id", table_name="generation_units")
    op.drop_column("generation_units", "source_tag")
    op.drop_column("generation_units", "quality_status")
    op.drop_column("generation_units", "observed_at")
    op.drop_column("generation_units", "snapshot_id")

    op.drop_index("ix_grid_data_snapshot_id", table_name="grid_data")
    op.drop_column("grid_data", "quality_status")
    op.drop_column("grid_data", "received_at")
    op.drop_column("grid_data", "snapshot_id")

    op.drop_index("ix_weather_observations_snapshot_id", table_name="weather_observations")
    op.drop_column("weather_observations", "snapshot_id")
