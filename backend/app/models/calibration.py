from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CalibrationImportRun(Base):
    __tablename__ = "calibration_import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_archive: Mapped[str] = mapped_column(String(255), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    import_status: Mapped[str] = mapped_column(String(32), nullable=False, default="IMPORTED")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_calibration_import_runs_source_archive", "source_archive"),
        Index("idx_calibration_import_runs_source_hash", "source_hash", unique=True),
        Index("idx_calibration_import_runs_imported_at", "imported_at"),
    )


class ScadaTemperatureSample(Base):
    __tablename__ = "scada_temperature_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_key: Mapped[str] = mapped_column(String(32), nullable=False)
    source_archive: Mapped[str] = mapped_column(String(255), nullable=False)
    source_workbook: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(255), nullable=False)
    measurement_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pen_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    sample_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    min_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    min_value_c: Mapped[float] = mapped_column(Float, nullable=False)
    max_value_c: Mapped[float] = mapped_column(Float, nullable=False)
    avg_value_c: Mapped[float] = mapped_column(Float, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_scada_temperature_samples_scenario", "scenario_key"),
        Index("idx_scada_temperature_samples_source", "source_archive", "source_workbook"),
        Index("idx_scada_temperature_samples_quality", "quality_status"),
    )


class CalibrationScenarioProfile(Base):
    __tablename__ = "calibration_scenario_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_key: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario_label: Mapped[str] = mapped_column(String(128), nullable=False)
    operating_regime: Mapped[str] = mapped_column(String(64), nullable=False)
    source_archive: Mapped[str] = mapped_column(String(255), nullable=False)
    source_workbook: Mapped[str] = mapped_column(String(255), nullable=False)
    source_sheet: Mapped[str] = mapped_column(String(255), nullable=False)

    hour_of_day: Mapped[int] = mapped_column(Integer, nullable=False)
    demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    spin_mw: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False, default="Calibrated")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_calibration_scenario_profiles_scenario", "scenario_key"),
        Index("idx_calibration_scenario_profiles_hour", "scenario_key", "hour_of_day"),
        Index("idx_calibration_scenario_profiles_source", "source_archive", "source_workbook"),
    )
