"""add SCADA CSV import foundation

Revision ID: c28f0a6d1b6e
Revises: b318a8cf1210
Create Date: 2026-07-09
"""

from alembic import op
import sqlalchemy as sa


revision = "c28f0a6d1b6e"
down_revision = "b318a8cf1210"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("scada_import_runs"):
        op.create_table(
            "scada_import_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_filename", sa.String(length=255), nullable=False),
            sa.Column("source_path", sa.String(length=500), nullable=False),
            sa.Column("source_hash", sa.String(length=64), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("import_status", sa.String(length=32), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column(
                "imported_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_hash"),
        )
    _create_index_if_missing(
        inspector,
        "idx_scada_import_runs_imported_at",
        "scada_import_runs",
        ["imported_at"],
    )
    _create_index_if_missing(
        inspector,
        "idx_scada_import_runs_source_hash",
        "scada_import_runs",
        ["source_hash"],
    )

    inspector = sa.inspect(bind)
    if not inspector.has_table("scada_raw_measurements"):
        op.create_table(
            "scada_raw_measurements",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("import_run_id", sa.Integer(), nullable=False),
            sa.Column("pen_index", sa.Integer(), nullable=False),
            sa.Column("tag_name", sa.String(length=255), nullable=False),
            sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("min_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("min_value", sa.Float(), nullable=True),
            sa.Column("max_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("max_value", sa.Float(), nullable=True),
            sa.Column("avg_value", sa.Float(), nullable=False),
            sa.Column("quality", sa.String(length=64), nullable=False),
            sa.Column("source_filename", sa.String(length=255), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["import_run_id"],
                ["scada_import_runs.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    inspector = sa.inspect(bind)
    _create_index_if_missing(
        inspector,
        "idx_scada_raw_measurements_import_run",
        "scada_raw_measurements",
        ["import_run_id"],
    )
    _create_index_if_missing(
        inspector,
        "idx_scada_raw_measurements_quality",
        "scada_raw_measurements",
        ["quality"],
    )
    _create_index_if_missing(
        inspector,
        "idx_scada_raw_measurements_tag_start",
        "scada_raw_measurements",
        ["tag_name", "start_time"],
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("scada_raw_measurements"):
        _drop_index_if_present(
            inspector,
            "idx_scada_raw_measurements_tag_start",
            "scada_raw_measurements",
        )
        _drop_index_if_present(
            inspector,
            "idx_scada_raw_measurements_quality",
            "scada_raw_measurements",
        )
        _drop_index_if_present(
            inspector,
            "idx_scada_raw_measurements_import_run",
            "scada_raw_measurements",
        )
        op.drop_table("scada_raw_measurements")

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("scada_import_runs"):
        _drop_index_if_present(
            inspector,
            "idx_scada_import_runs_source_hash",
            "scada_import_runs",
        )
        _drop_index_if_present(
            inspector,
            "idx_scada_import_runs_imported_at",
            "scada_import_runs",
        )
        op.drop_table("scada_import_runs")


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
