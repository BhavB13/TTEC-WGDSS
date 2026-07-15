"""add calibration import content hash

Revision ID: d8a5f7c3e1b2
Revises: c7f4e1a2d9b0
"""

from alembic import op
import sqlalchemy as sa


revision = "d8a5f7c3e1b2"
down_revision = "c7f4e1a2d9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("calibration_import_runs") as batch_op:
        batch_op.add_column(sa.Column("source_hash", sa.String(length=64), nullable=True))
        batch_op.create_index(
            "idx_calibration_import_runs_source_hash",
            ["source_hash"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("calibration_import_runs") as batch_op:
        batch_op.drop_index("idx_calibration_import_runs_source_hash")
        batch_op.drop_column("source_hash")
