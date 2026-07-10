"""add SCADA weather forecast training dataset

Revision ID: e2bc4a71df90
Revises: d6f785a7bb63
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa


revision = "e2bc4a71df90"
down_revision = "d6f785a7bb63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("forecast_training_rows"):
        op.create_table(
            "forecast_training_rows",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("feature_timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("horizon_hours", sa.Integer(), nullable=False),
            sa.Column("target_timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("target_demand_mw", sa.Float(), nullable=False),
            sa.Column("current_demand_mw", sa.Float(), nullable=False),
            sa.Column("lag_1h_demand_mw", sa.Float(), nullable=True),
            sa.Column("lag_2h_demand_mw", sa.Float(), nullable=True),
            sa.Column("lag_24h_demand_mw", sa.Float(), nullable=True),
            sa.Column("rolling_3h_demand_mw", sa.Float(), nullable=True),
            sa.Column("rolling_6h_demand_mw", sa.Float(), nullable=True),
            sa.Column("hour_of_day", sa.Integer(), nullable=False),
            sa.Column("day_of_week", sa.Integer(), nullable=False),
            sa.Column("temperature_c", sa.Float(), nullable=True),
            sa.Column("humidity_percent", sa.Float(), nullable=True),
            sa.Column("rainfall_mm_hr", sa.Float(), nullable=True),
            sa.Column("cloud_cover_percent", sa.Float(), nullable=True),
            sa.Column("wind_speed_kmh", sa.Float(), nullable=True),
            sa.Column("forecast_temperature_c", sa.Float(), nullable=True),
            sa.Column("forecast_rainfall_mm_hr", sa.Float(), nullable=True),
            sa.Column("forecast_cloud_cover_percent", sa.Float(), nullable=True),
            sa.Column(
                "source_quality_status",
                sa.String(length=32),
                nullable=False,
                server_default="UNKNOWN",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(
        inspector,
        "idx_forecast_training_rows_feature_horizon",
        "forecast_training_rows",
        ["feature_timestamp", "horizon_hours"],
        unique=True,
    )
    _create_index_if_missing(
        inspector,
        "idx_forecast_training_rows_horizon",
        "forecast_training_rows",
        ["horizon_hours"],
    )
    _create_index_if_missing(
        inspector,
        "idx_forecast_training_rows_quality",
        "forecast_training_rows",
        ["source_quality_status"],
    )
    _create_index_if_missing(
        inspector,
        "ix_forecast_training_rows_feature_timestamp",
        "forecast_training_rows",
        ["feature_timestamp"],
    )
    _create_index_if_missing(
        inspector,
        "ix_forecast_training_rows_target_timestamp",
        "forecast_training_rows",
        ["target_timestamp"],
    )

    inspector = sa.inspect(bind)
    if not inspector.has_table("demand_forecast_results"):
        op.create_table(
            "demand_forecast_results",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("forecast_timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("horizon_hours", sa.Integer(), nullable=False),
            sa.Column("forecast_demand_mw", sa.Float(), nullable=False),
            sa.Column("forecast_uncertainty_mw", sa.Float(), nullable=False),
            sa.Column("model_name", sa.String(length=100), nullable=False),
            sa.Column("model_version", sa.String(length=64), nullable=False),
            sa.Column("baseline_name", sa.String(length=100), nullable=False),
            sa.Column("baseline_forecast_mw", sa.Float(), nullable=False),
            sa.Column("mae", sa.Float(), nullable=False),
            sa.Column("rmse", sa.Float(), nullable=False),
            sa.Column("mape", sa.Float(), nullable=False),
            sa.Column("residual_std", sa.Float(), nullable=False),
            sa.Column("ml_beats_baseline", sa.Boolean(), nullable=False),
            sa.Column("quality_status", sa.String(length=32), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(
        inspector,
        "idx_demand_forecast_results_timestamp_horizon",
        "demand_forecast_results",
        ["forecast_timestamp", "horizon_hours"],
    )
    _create_index_if_missing(
        inspector,
        "idx_demand_forecast_results_quality",
        "demand_forecast_results",
        ["quality_status"],
    )
    _create_index_if_missing(
        inspector,
        "ix_demand_forecast_results_forecast_timestamp",
        "demand_forecast_results",
        ["forecast_timestamp"],
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("demand_forecast_results"):
        _drop_index_if_present(
            inspector,
            "ix_demand_forecast_results_forecast_timestamp",
            "demand_forecast_results",
        )
        _drop_index_if_present(
            inspector,
            "idx_demand_forecast_results_quality",
            "demand_forecast_results",
        )
        _drop_index_if_present(
            inspector,
            "idx_demand_forecast_results_timestamp_horizon",
            "demand_forecast_results",
        )
        op.drop_table("demand_forecast_results")

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("forecast_training_rows"):
        _drop_index_if_present(
            inspector,
            "ix_forecast_training_rows_target_timestamp",
            "forecast_training_rows",
        )
        _drop_index_if_present(
            inspector,
            "ix_forecast_training_rows_feature_timestamp",
            "forecast_training_rows",
        )
        _drop_index_if_present(
            inspector,
            "idx_forecast_training_rows_quality",
            "forecast_training_rows",
        )
        _drop_index_if_present(
            inspector,
            "idx_forecast_training_rows_horizon",
            "forecast_training_rows",
        )
        _drop_index_if_present(
            inspector,
            "idx_forecast_training_rows_feature_horizon",
            "forecast_training_rows",
        )
        op.drop_table("forecast_training_rows")


def _create_index_if_missing(
    inspector: sa.Inspector,
    index_name: str,
    table_name: str,
    columns: list[str],
    unique: bool = False,
) -> None:
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=unique)


def _drop_index_if_present(
    inspector: sa.Inspector,
    index_name: str,
    table_name: str,
) -> None:
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)
