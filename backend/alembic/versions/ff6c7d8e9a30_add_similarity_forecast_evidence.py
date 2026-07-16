"""add similarity forecast features and evidence

Revision ID: ff6c7d8e9a30
Revises: fe5b6c3d8a20
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "ff6c7d8e9a30"
down_revision: str | None = "fe5b6c3d8a20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TRAINING_COLUMNS = (
    "lag_48h_demand_mw",
    "lag_168h_demand_mw",
    "rolling_12h_demand_mw",
    "rolling_168h_demand_mw",
    "same_hour_7d_average_mw",
    "demand_volatility_6h_mw",
)

RESULT_TABLES = (
    "demand_forecast_results",
    "scada_replay_forecast_results",
)


def upgrade() -> None:
    with op.batch_alter_table("forecast_training_rows") as batch_op:
        for column_name in TRAINING_COLUMNS:
            batch_op.add_column(sa.Column(column_name, sa.Float(), nullable=True))

    for table_name in RESULT_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "confidence_lower_mw",
                    sa.Float(),
                    nullable=False,
                    server_default="0",
                )
            )
            batch_op.add_column(
                sa.Column(
                    "confidence_upper_mw",
                    sa.Float(),
                    nullable=False,
                    server_default="0",
                )
            )
            batch_op.add_column(
                sa.Column(
                    "confidence_level",
                    sa.Float(),
                    nullable=False,
                    server_default="0.9",
                )
            )
            batch_op.add_column(
                sa.Column("temperature_load_correlation", sa.Float(), nullable=True)
            )
            batch_op.add_column(
                sa.Column("similar_period_forecast_mw", sa.Float(), nullable=True)
            )
            batch_op.add_column(
                sa.Column(
                    "similar_examples",
                    sa.Text(),
                    nullable=False,
                    server_default="[]",
                )
            )
            batch_op.add_column(
                sa.Column(
                    "contributing_factors",
                    sa.Text(),
                    nullable=False,
                    server_default="[]",
                )
            )

        op.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET confidence_lower_mw = CASE
                        WHEN forecast_demand_mw - (1.6448536269514722 * forecast_uncertainty_mw) > 0
                        THEN forecast_demand_mw - (1.6448536269514722 * forecast_uncertainty_mw)
                        ELSE 0
                    END,
                    confidence_upper_mw = forecast_demand_mw + (1.6448536269514722 * forecast_uncertainty_mw)
                """
            )
        )


def downgrade() -> None:
    for table_name in reversed(RESULT_TABLES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("contributing_factors")
            batch_op.drop_column("similar_examples")
            batch_op.drop_column("similar_period_forecast_mw")
            batch_op.drop_column("temperature_load_correlation")
            batch_op.drop_column("confidence_level")
            batch_op.drop_column("confidence_upper_mw")
            batch_op.drop_column("confidence_lower_mw")

    with op.batch_alter_table("forecast_training_rows") as batch_op:
        for column_name in reversed(TRAINING_COLUMNS):
            batch_op.drop_column(column_name)
