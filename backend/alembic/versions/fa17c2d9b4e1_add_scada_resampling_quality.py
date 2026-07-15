"""add SCADA resampling quality metadata

Revision ID: fa17c2d9b4e1
Revises: e9b6a8d4f2c3
"""

from alembic import op
import sqlalchemy as sa


revision = "fa17c2d9b4e1"
down_revision = "e9b6a8d4f2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("scada_grid_snapshots") as batch_op:
        batch_op.add_column(
            sa.Column(
                "coverage_percent",
                sa.Float(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "quality_notes",
                sa.Text(),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "resampling_method",
                sa.String(length=64),
                nullable=False,
                server_default="interval_overlap_hourly",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("scada_grid_snapshots") as batch_op:
        batch_op.drop_column("resampling_method")
        batch_op.drop_column("quality_notes")
        batch_op.drop_column("coverage_percent")

