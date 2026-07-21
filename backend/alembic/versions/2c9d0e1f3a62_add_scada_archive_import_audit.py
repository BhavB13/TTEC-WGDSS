"""add SCADA archive import audit records

Revision ID: 2c9d0e1f3a62
Revises: 1b8c9d0e2f51
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "2c9d0e1f3a62"
down_revision: str | None = "1b8c9d0e2f51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "scada_archive_import_runs" not in inspector.get_table_names():
        op.create_table(
            "scada_archive_import_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_filename", sa.String(length=255), nullable=False),
            sa.Column("source_path", sa.String(length=500), nullable=False),
            sa.Column("source_hash", sa.String(length=64), nullable=False),
            sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source_row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("normalized_row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duplicate_row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("out_of_period_row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("import_status", sa.String(length=32), nullable=False, server_default="PENDING"),
            sa.Column("data_start_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("data_end_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("validation_report", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_hash"),
        )
        op.create_index(
            "idx_scada_archive_import_runs_source_hash",
            "scada_archive_import_runs",
            ["source_hash"],
            unique=False,
        )
        op.create_index(
            "idx_scada_archive_import_runs_imported_at",
            "scada_archive_import_runs",
            ["imported_at"],
            unique=False,
        )
    import_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("scada_import_runs")
    }
    if "archive_import_run_id" not in import_columns:
        with op.batch_alter_table("scada_import_runs") as batch_op:
            batch_op.add_column(
                sa.Column("archive_import_run_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_scada_import_runs_archive_import_run",
                "scada_archive_import_runs",
                ["archive_import_run_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index(
                "idx_scada_import_runs_archive",
                ["archive_import_run_id"],
                unique=False,
            )


def downgrade() -> None:
    with op.batch_alter_table("scada_import_runs") as batch_op:
        batch_op.drop_index("idx_scada_import_runs_archive")
        batch_op.drop_constraint(
            "fk_scada_import_runs_archive_import_run", type_="foreignkey"
        )
        batch_op.drop_column("archive_import_run_id")
    op.drop_index(
        "idx_scada_archive_import_runs_imported_at",
        table_name="scada_archive_import_runs",
    )
    op.drop_index(
        "idx_scada_archive_import_runs_source_hash",
        table_name="scada_archive_import_runs",
    )
    op.drop_table("scada_archive_import_runs")
