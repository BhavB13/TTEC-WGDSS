"""add leakage-safe horizon features and model audit metadata

Revision ID: fb28d3e0c5f2
Revises: fa17c2d9b4e1
"""

from alembic import op
import sqlalchemy as sa


revision = "fb28d3e0c5f2"
down_revision = "fa17c2d9b4e1"
branch_labels = None
depends_on = None


TRAINING_FLOAT_COLUMNS = (
    "lag_3h_demand_mw",
    "lag_6h_demand_mw",
    "rolling_24h_demand_mw",
    "demand_rate_1h_mw",
    "demand_rate_3h_mw",
    "demand_rate_6h_mw",
    "spinning_reserve_lag_1h_mw",
    "available_capacity_lag_1h_mw",
    "online_capacity_lag_1h_mw",
    "spinning_reserve_rate_1h_mw",
    "available_capacity_rate_1h_mw",
    "online_capacity_rate_1h_mw",
    "scada_temperature_c",
    "temperature_lag_1h_c",
    "rolling_3h_temperature_c",
    "temperature_rate_1h_c",
)


def upgrade() -> None:
    with op.batch_alter_table("forecast_training_rows") as batch_op:
        for column_name in TRAINING_FLOAT_COLUMNS:
            batch_op.add_column(sa.Column(column_name, sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("forecast_weather_source", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("forecast_weather_issued_at", sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table("demand_forecast_results") as batch_op:
        batch_op.add_column(
            sa.Column(
                "feature_profile",
                sa.String(length=64),
                nullable=False,
                server_default="demand_weather_v2",
            )
        )
        batch_op.add_column(
            sa.Column(
                "validation_status",
                sa.String(length=32),
                nullable=False,
                server_default="PROTOTYPE",
            )
        )
        batch_op.add_column(
            sa.Column("training_span_hours", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("train_row_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("test_row_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("candidate_metrics", sa.Text(), nullable=False, server_default="{}")
        )


def downgrade() -> None:
    with op.batch_alter_table("demand_forecast_results") as batch_op:
        batch_op.drop_column("candidate_metrics")
        batch_op.drop_column("test_row_count")
        batch_op.drop_column("train_row_count")
        batch_op.drop_column("training_span_hours")
        batch_op.drop_column("validation_status")
        batch_op.drop_column("feature_profile")

    with op.batch_alter_table("forecast_training_rows") as batch_op:
        batch_op.drop_column("forecast_weather_issued_at")
        batch_op.drop_column("forecast_weather_source")
        for column_name in reversed(TRAINING_FLOAT_COLUMNS):
            batch_op.drop_column(column_name)

