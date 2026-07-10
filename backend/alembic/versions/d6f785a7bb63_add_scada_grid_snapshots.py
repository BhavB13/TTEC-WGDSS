"""add normalized SCADA grid snapshots

Revision ID: d6f785a7bb63
Revises: c28f0a6d1b6e
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa


revision = "d6f785a7bb63"
down_revision = "c28f0a6d1b6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("scada_grid_snapshots"):
        op.create_table(
            "scada_grid_snapshots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("current_demand_mw", sa.Float(), nullable=True),
            sa.Column("temperature_c", sa.Float(), nullable=True),
            sa.Column("spinning_reserve_mw", sa.Float(), nullable=True),
            sa.Column("available_capacity_mw", sa.Float(), nullable=True),
            sa.Column("online_capacity_mw", sa.Float(), nullable=True),
            sa.Column("reserve_margin_mw", sa.Float(), nullable=True),
            sa.Column("reserve_margin_percent", sa.Float(), nullable=True),
            sa.Column("online_spare_mw", sa.Float(), nullable=True),
            sa.Column("quality_status", sa.String(length=32), nullable=False),
            sa.Column("missing_fields", sa.Text(), nullable=False, server_default=""),
            sa.Column("source", sa.String(length=500), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("timestamp"),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(
        inspector,
        "idx_scada_grid_snapshots_timestamp",
        "scada_grid_snapshots",
        ["timestamp"],
    )
    _create_index_if_missing(
        inspector,
        "idx_scada_grid_snapshots_quality",
        "scada_grid_snapshots",
        ["quality_status"],
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("scada_grid_snapshots"):
        _drop_index_if_present(
            inspector,
            "idx_scada_grid_snapshots_quality",
            "scada_grid_snapshots",
        )
        _drop_index_if_present(
            inspector,
            "idx_scada_grid_snapshots_timestamp",
            "scada_grid_snapshots",
        )
        op.drop_table("scada_grid_snapshots")


def _create_index_if_missing(
    inspector: sa.Inspector,
    index_name: str,
    table_name: str,
    columns: list[str],
) -> None:
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=False)


def _drop_index_if_present(
    inspector: sa.Inspector,
    index_name: str,
    table_name: str,
) -> None:
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)
