from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ScadaImportRun(Base):
    __tablename__ = "scada_import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    import_status: Mapped[str] = mapped_column(String(32), nullable=False, default="IMPORTED")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    measurements: Mapped[list["ScadaRawMeasurement"]] = relationship(
        back_populates="import_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_scada_import_runs_source_hash", "source_hash"),
        Index("idx_scada_import_runs_imported_at", "imported_at"),
    )


class ScadaRawMeasurement(Base):
    __tablename__ = "scada_raw_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_run_id: Mapped[int] = mapped_column(
        ForeignKey("scada_import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    pen_index: Mapped[int] = mapped_column(Integer, nullable=False)
    tag_name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    min_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    min_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_value: Mapped[float] = mapped_column(Float, nullable=False)
    quality: Mapped[str] = mapped_column(String(64), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    import_run: Mapped[ScadaImportRun] = relationship(back_populates="measurements")

    __table_args__ = (
        Index("idx_scada_raw_measurements_tag_start", "tag_name", "start_time"),
        Index("idx_scada_raw_measurements_import_run", "import_run_id"),
        Index("idx_scada_raw_measurements_quality", "quality"),
    )


class ScadaGridSnapshot(Base):
    __tablename__ = "scada_grid_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        unique=True,
    )
    current_demand_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    spinning_reserve_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    available_capacity_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    online_capacity_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    reserve_margin_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    reserve_margin_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    online_spare_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    missing_fields: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(500), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_scada_grid_snapshots_timestamp", "timestamp"),
        Index("idx_scada_grid_snapshots_quality", "quality_status"),
    )
