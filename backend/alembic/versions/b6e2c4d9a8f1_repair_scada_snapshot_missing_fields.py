"""repair legacy SCADA snapshot schema

Revision ID: b6e2c4d9a8f1
Revises: a4d19e7c2b6f
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "b6e2c4d9a8f1"
down_revision = "a4d19e7c2b6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("scada_grid_snapshots"):
        return

    existing = {
        column["name"] for column in inspector.get_columns("scada_grid_snapshots")
    }
    if "missing_fields" not in existing:
        with op.batch_alter_table("scada_grid_snapshots") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "missing_fields",
                    sa.Text(),
                    nullable=False,
                    server_default="",
                )
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("scada_grid_snapshots"):
        return

    existing = {
        column["name"] for column in inspector.get_columns("scada_grid_snapshots")
    }
    if "missing_fields" in existing:
        with op.batch_alter_table("scada_grid_snapshots") as batch_op:
            batch_op.drop_column("missing_fields")
