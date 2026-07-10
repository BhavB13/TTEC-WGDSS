"""add forecast weather model features

Revision ID: f3a7b8c9d0e1
Revises: e2bc4a71df90
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "f3a7b8c9d0e1"
down_revision = "e2bc4a71df90"
branch_labels = None
depends_on = None


FEATURE_COLUMNS = (
    ("pressure_hpa", sa.Float()),
    ("forecast_humidity_percent", sa.Float()),
    ("forecast_wind_speed_kmh", sa.Float()),
    ("forecast_precipitation_probability_percent", sa.Float()),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("forecast_training_rows"):
        return
    existing = {
        column["name"] for column in inspector.get_columns("forecast_training_rows")
    }
    with op.batch_alter_table("forecast_training_rows") as batch_op:
        for name, column_type in FEATURE_COLUMNS:
            if name not in existing:
                batch_op.add_column(sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("forecast_training_rows"):
        return
    existing = {
        column["name"] for column in inspector.get_columns("forecast_training_rows")
    }
    with op.batch_alter_table("forecast_training_rows") as batch_op:
        for name, _ in reversed(FEATURE_COLUMNS):
            if name in existing:
                batch_op.drop_column(name)
