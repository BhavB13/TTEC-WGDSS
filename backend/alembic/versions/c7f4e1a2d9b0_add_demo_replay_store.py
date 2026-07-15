"""add immutable demo observations and replay state

Revision ID: c7f4e1a2d9b0
Revises: b6e2c4d9a8f1
Create Date: 2026-07-15
"""

from alembic import op
import sqlalchemy as sa


revision = "c7f4e1a2d9b0"
down_revision = "b6e2c4d9a8f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, unique=True),
        sa.Column("demand_mw", sa.Float(), nullable=False),
        sa.Column("generation_mw", sa.Float(), nullable=False),
        sa.Column("spinning_reserve_mw", sa.Float(), nullable=False),
        sa.Column("available_capacity_mw", sa.Float(), nullable=False),
        sa.Column("online_capacity_mw", sa.Float(), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("humidity_percent", sa.Float(), nullable=False),
        sa.Column("rainfall_mm_hr", sa.Float(), nullable=False),
        sa.Column("cloud_cover_percent", sa.Float(), nullable=False),
        sa.Column("wind_speed_kmh", sa.Float(), nullable=False),
        sa.Column("wind_direction_deg", sa.Float(), nullable=False),
        sa.Column("pressure_hpa", sa.Float(), nullable=False),
        sa.Column("quality_status", sa.String(24), nullable=False, server_default="GOOD"),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_demo_observations_timestamp", "demo_observations", ["timestamp"])
    op.create_index("ix_demo_observations_quality", "demo_observations", ["quality_status"])
    op.create_table(
        "demo_replay_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dataset_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replay_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replay_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cursor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_playing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("step_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("speed_multiplier", sa.Float(), nullable=False, server_default="3600"),
        sa.Column("last_wallclock_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("demo_replay_state")
    op.drop_index("ix_demo_observations_quality", table_name="demo_observations")
    op.drop_index("ix_demo_observations_timestamp", table_name="demo_observations")
    op.drop_table("demo_observations")
