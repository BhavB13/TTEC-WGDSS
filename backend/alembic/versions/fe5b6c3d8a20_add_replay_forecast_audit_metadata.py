"""add replay forecast audit metadata

Revision ID: fe5b6c3d8a20
Revises: fd4a5b2c7e19
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "fe5b6c3d8a20"
down_revision: str | None = "fd4a5b2c7e19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scada_replay_forecast_results") as batch_op:
        batch_op.add_column(sa.Column("mape", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("baseline_mae", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "ml_beats_baseline",
                sa.Boolean(),
                nullable=True,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("feature_profile", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("validation_status", sa.String(32), nullable=True))
        batch_op.add_column(sa.Column("training_span_hours", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("train_row_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("test_row_count", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "candidate_metrics",
                sa.Text(),
                nullable=True,
                server_default="{}",
            )
        )

    op.execute(
        """
        UPDATE scada_replay_forecast_results
        SET mape = 0,
            baseline_mae = mae,
            feature_profile = 'demand_weather_v2',
            validation_status = 'PROTOTYPE',
            training_span_hours = 0,
            train_row_count = training_rows,
            test_row_count = 0,
            candidate_metrics = '{}'
        WHERE mape IS NULL
        """
    )

    with op.batch_alter_table("scada_replay_forecast_results") as batch_op:
        batch_op.alter_column("mape", existing_type=sa.Float(), nullable=False)
        batch_op.alter_column("baseline_mae", existing_type=sa.Float(), nullable=False)
        batch_op.alter_column(
            "ml_beats_baseline",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=None,
        )
        batch_op.alter_column(
            "feature_profile",
            existing_type=sa.String(64),
            nullable=False,
        )
        batch_op.alter_column(
            "validation_status",
            existing_type=sa.String(32),
            nullable=False,
        )
        batch_op.alter_column(
            "training_span_hours",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "train_row_count",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "test_row_count",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "candidate_metrics",
            existing_type=sa.Text(),
            nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("scada_replay_forecast_results") as batch_op:
        batch_op.drop_column("candidate_metrics")
        batch_op.drop_column("test_row_count")
        batch_op.drop_column("train_row_count")
        batch_op.drop_column("training_span_hours")
        batch_op.drop_column("validation_status")
        batch_op.drop_column("feature_profile")
        batch_op.drop_column("ml_beats_baseline")
        batch_op.drop_column("baseline_mae")
        batch_op.drop_column("mape")
