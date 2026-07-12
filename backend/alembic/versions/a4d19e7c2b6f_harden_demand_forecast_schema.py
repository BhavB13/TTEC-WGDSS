"""harden demand forecast schema for ML operating context

Revision ID: a4d19e7c2b6f
Revises: f3a7b8c9d0e1
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "a4d19e7c2b6f"
down_revision = "f3a7b8c9d0e1"
branch_labels = None
depends_on = None


TRAINING_COLUMNS = (
    ("spinning_reserve_mw", sa.Float()),
    ("available_capacity_mw", sa.Float()),
    ("online_capacity_mw", sa.Float()),
    ("reserve_margin_mw", sa.Float()),
    ("online_spare_mw", sa.Float()),
)

RESULT_COLUMNS = (
    ("mae", sa.Float(), "0"),
    ("rmse", sa.Float(), "0"),
    ("mape", sa.Float(), "0"),
    ("residual_std", sa.Float(), "0"),
    ("ml_beats_baseline", sa.Boolean(), "0"),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("forecast_training_rows"):
        existing = {
            column["name"]
            for column in inspector.get_columns("forecast_training_rows")
        }
        with op.batch_alter_table("forecast_training_rows") as batch_op:
            for name, column_type in TRAINING_COLUMNS:
                if name not in existing:
                    batch_op.add_column(sa.Column(name, column_type, nullable=True))

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("demand_forecast_results"):
        existing = {
            column["name"]
            for column in inspector.get_columns("demand_forecast_results")
        }
        with op.batch_alter_table("demand_forecast_results") as batch_op:
            for name, column_type, default in RESULT_COLUMNS:
                if name not in existing:
                    batch_op.add_column(
                        sa.Column(
                            name,
                            column_type,
                            nullable=False,
                            server_default=sa.text(default),
                        )
                    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("demand_forecast_results"):
        existing = {
            column["name"]
            for column in inspector.get_columns("demand_forecast_results")
        }
        with op.batch_alter_table("demand_forecast_results") as batch_op:
            for name, _, _ in reversed(RESULT_COLUMNS):
                if name in existing:
                    batch_op.drop_column(name)

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("forecast_training_rows"):
        existing = {
            column["name"]
            for column in inspector.get_columns("forecast_training_rows")
        }
        with op.batch_alter_table("forecast_training_rows") as batch_op:
            for name, _ in reversed(TRAINING_COLUMNS):
                if name in existing:
                    batch_op.drop_column(name)
