from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from zipfile import BadZipFile, ZipFile

from app.services.calibration_import_service import CalibrationImportService
from app.services.scada_archive_service import ScadaArchiveService
from app.services.scada_import_service import ScadaImportService


SCADA_SCHEMA_MAPPING = {
    "pen index": "pen_index",
    "name": "tag_name",
    "start time": "start_time",
    "end time": "end_time",
    "min time": "min_time",
    "min value": "min_value",
    "max time": "max_time",
    "max value": "max_value",
    "avg value": "avg_value",
    "quality": "quality",
}


@dataclass(frozen=True)
class HistoricalImportReport:
    adapter_id: str
    source_filename: str
    source_hash: str
    imported: bool
    skipped_duplicate: bool
    row_count: int
    validation_status: str
    schema_mapping: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)


class HistoricalDatasetAdapter(Protocol):
    adapter_id: str

    def can_handle(self, source: Path) -> bool: ...

    def validate(self, source: Path) -> list[str]: ...

    def import_dataset(self, source: Path) -> HistoricalImportReport: ...


class ScadaCsvAdapter:
    adapter_id = "scada_csv_v1"

    def __init__(self, service: ScadaImportService | None = None) -> None:
        self.service = service or ScadaImportService()

    def can_handle(self, source: Path) -> bool:
        return source.suffix.lower() == ".csv"

    def validate(self, source: Path) -> list[str]:
        rows = self.service.read_measurements(source)
        warnings: list[str] = []
        if not rows:
            raise ValueError("SCADA CSV contains no measurement rows")
        qualities = {str(row["quality"]).strip().upper() for row in rows}
        if qualities - {"GOOD"}:
            warnings.append(
                "Non-Good quality rows are preserved and will be excluded where required"
            )
        return warnings

    def import_dataset(self, source: Path) -> HistoricalImportReport:
        warnings = self.validate(source)
        result = self.service.import_csv(source)
        return HistoricalImportReport(
            adapter_id=self.adapter_id,
            source_filename=result.source_filename,
            source_hash=result.source_hash,
            imported=result.imported,
            skipped_duplicate=result.skipped_duplicate,
            row_count=result.row_count,
            validation_status="VALID",
            schema_mapping=dict(SCADA_SCHEMA_MAPPING),
            warnings=warnings,
            next_actions=[
                "Build timestamp-aligned SCADA snapshots",
                "Run replay preflight validation",
                "Rebuild forecast rows and retrain only if chronological gates pass",
            ],
        )


class CalibrationArchiveAdapter:
    adapter_id = "calibration_archive_v1"

    def __init__(self, service: CalibrationImportService | None = None) -> None:
        self.service = service or CalibrationImportService()

    def can_handle(self, source: Path) -> bool:
        if source.suffix.lower() != ".zip":
            return False
        try:
            with ZipFile(source) as archive:
                names = [name.lower() for name in archive.namelist()]
        except (BadZipFile, OSError):
            return False
        return any(name.endswith(".xlsx") for name in names)

    def validate(self, source: Path) -> list[str]:
        try:
            with ZipFile(source) as archive:
                workbooks = [name for name in archive.namelist() if name.lower().endswith(".xlsx")]
        except BadZipFile as exc:
            raise ValueError("Calibration archive is not a valid ZIP file") from exc
        if not workbooks:
            raise ValueError("Calibration archive contains no XLSX workbooks")
        return []

    def import_dataset(self, source: Path) -> HistoricalImportReport:
        warnings = self.validate(source)
        counts = self.service.import_archive(source, replace_existing=True)
        row_count = counts["temperature_samples"] + counts["scenario_profiles"]
        return HistoricalImportReport(
            adapter_id=self.adapter_id,
            source_filename=source.name,
            source_hash=_file_hash(source),
            imported=counts["import_runs"] > 0,
            skipped_duplicate=counts.get("skipped_duplicate", 0) > 0,
            row_count=row_count,
            validation_status="VALID",
            schema_mapping={
                "SCADA Avg Value": "temperature_c",
                "Scenario Demand MW": "demand_mw",
                "Scenario Spin MW": "spinning_reserve_mw",
            },
            warnings=warnings,
            next_actions=[
                "Review scenario coverage and quality",
                "Recalibrate scenario selection; do not treat calibration rows as live SCADA",
            ],
        )


class ScadaArchiveAdapter:
    adapter_id = "scada_archive_v2"

    def __init__(self, service: ScadaArchiveService | None = None) -> None:
        self.service = service or ScadaArchiveService()

    def can_handle(self, source: Path) -> bool:
        return self.service.can_handle(source)

    def validate(self, source: Path) -> list[str]:
        return list(self.service.inspect_archive(source).warnings)

    def import_dataset(self, source: Path) -> HistoricalImportReport:
        result = self.service.import_archive(source)
        return HistoricalImportReport(
            adapter_id=self.adapter_id,
            source_filename=result.report.source_filename,
            source_hash=result.report.source_hash,
            imported=result.files_imported > 0,
            skipped_duplicate=(
                bool(result.import_results)
                and result.duplicate_files_skipped == len(result.import_results)
            ),
            row_count=result.rows_imported,
            validation_status=result.report.validation_status,
            schema_mapping=dict(SCADA_SCHEMA_MAPPING),
            warnings=list(result.report.warnings),
            next_actions=[
                "Build interval-overlap hourly SCADA snapshots",
                "Backfill current-time historical weather without using future observations",
                "Generate leakage-safe horizon features and run chronological model comparison",
                "Review prototype metrics before activating a retrained model",
            ],
        )


class HistoricalDataImportService:
    def __init__(
        self,
        adapters: list[HistoricalDatasetAdapter] | None = None,
    ) -> None:
        self.adapters = (
            [ScadaCsvAdapter(), ScadaArchiveAdapter(), CalibrationArchiveAdapter()]
            if adapters is None
            else list(adapters)
        )

    def register(self, adapter: HistoricalDatasetAdapter) -> None:
        if any(existing.adapter_id == adapter.adapter_id for existing in self.adapters):
            raise ValueError(f"Historical adapter already registered: {adapter.adapter_id}")
        self.adapters.append(adapter)

    def import_dataset(
        self,
        source_path: str | Path,
        adapter_id: str | None = None,
    ) -> HistoricalImportReport:
        source = Path(source_path)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Historical dataset not found: {source}")
        candidates = [
            adapter
            for adapter in self.adapters
            if adapter_id is None or adapter.adapter_id == adapter_id
        ]
        for adapter in candidates:
            if adapter.can_handle(source):
                return adapter.import_dataset(source)
        requested = f" for adapter {adapter_id}" if adapter_id else ""
        raise ValueError(f"No historical data adapter accepts {source.name}{requested}")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
