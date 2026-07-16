"""add SCADA interval provenance and forecast timing audit fields

Revision ID: 1b8c9d0e2f51
Revises: 0a7b8c9d1e40
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "1b8c9d0e2f51"
down_revision: str | None = "0a7b8c9d1e40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("scada_import_runs") as batch_op:
        batch_op.add_column(
            sa.Column("quality_report", sa.Text(), nullable=False, server_default="{}")
        )

    with op.batch_alter_table("scada_raw_measurements") as batch_op:
        batch_op.add_column(sa.Column("source_tag_raw", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column("canonical_variable", sa.String(128), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "normalized_quality",
                sa.String(32),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_system",
                sa.String(128),
                nullable=False,
                server_default="AspenTech OSI trend export",
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_provider",
                sa.String(64),
                nullable=False,
                server_default="csv_trend_export",
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_timezone",
                sa.String(64),
                nullable=False,
                server_default="America/Port_of_Spain",
            )
        )
        batch_op.add_column(sa.Column("interval_seconds", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("engineering_unit", sa.String(32), nullable=True))
        batch_op.add_column(
            sa.Column(
                "aggregation",
                sa.String(32),
                nullable=False,
                server_default="interval_summary",
            )
        )
        batch_op.add_column(
            sa.Column("anomaly_flags", sa.Text(), nullable=False, server_default="[]")
        )
        batch_op.add_column(sa.Column("record_hash", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column("source_metadata", sa.Text(), nullable=False, server_default="{}")
        )
        batch_op.create_index(
            "idx_scada_raw_measurements_normalized_quality",
            ["normalized_quality"],
            unique=False,
        )
        batch_op.create_index(
            "idx_scada_raw_measurements_record_hash",
            ["record_hash"],
            unique=True,
        )

    with op.batch_alter_table("scada_grid_snapshots") as batch_op:
        batch_op.add_column(
            sa.Column("field_provenance", sa.Text(), nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column("anomaly_flags", sa.Text(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column(
                "formula_version",
                sa.String(64),
                nullable=False,
                server_default="wgdss-headroom-v1",
            )
        )

    with op.batch_alter_table("forecast_training_rows") as batch_op:
        batch_op.add_column(
            sa.Column("feature_observation_time", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("feature_available_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("target_observation_time", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("target_available_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("forecast_training_rows") as batch_op:
        batch_op.drop_column("target_available_at")
        batch_op.drop_column("target_observation_time")
        batch_op.drop_column("feature_available_at")
        batch_op.drop_column("feature_observation_time")

    with op.batch_alter_table("scada_grid_snapshots") as batch_op:
        batch_op.drop_column("formula_version")
        batch_op.drop_column("anomaly_flags")
        batch_op.drop_column("field_provenance")

    with op.batch_alter_table("scada_raw_measurements") as batch_op:
        batch_op.drop_index("idx_scada_raw_measurements_record_hash")
        batch_op.drop_index("idx_scada_raw_measurements_normalized_quality")
        batch_op.drop_column("source_metadata")
        batch_op.drop_column("record_hash")
        batch_op.drop_column("anomaly_flags")
        batch_op.drop_column("aggregation")
        batch_op.drop_column("engineering_unit")
        batch_op.drop_column("interval_seconds")
        batch_op.drop_column("source_timezone")
        batch_op.drop_column("source_provider")
        batch_op.drop_column("source_system")
        batch_op.drop_column("normalized_quality")
        batch_op.drop_column("canonical_variable")
        batch_op.drop_column("source_tag_raw")

    with op.batch_alter_table("scada_import_runs") as batch_op:
        batch_op.drop_column("quality_report")
