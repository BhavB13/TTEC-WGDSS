"""add replay clock alignment marker

Revision ID: e9b6a8d4f2c3
Revises: d8a5f7c3e1b2
"""

from alembic import op
import sqlalchemy as sa


revision = "e9b6a8d4f2c3"
down_revision = "d8a5f7c3e1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("demo_replay_state") as batch_op:
        batch_op.add_column(
            sa.Column(
                "clock_aligned",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("demo_replay_state") as batch_op:
        batch_op.drop_column("clock_aligned")
