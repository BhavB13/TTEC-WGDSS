from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median
from zipfile import BadZipFile, ZipFile

from app.database.session import SessionLocal
from app.services.scada_import_service import ScadaImportResult, ScadaImportService
from app.services.scada_snapshot_service import (
    SCADA_TAG_FIELD_MAP,
    ScadaSnapshotService,
)


MAX_ARCHIVE_MEMBER_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class ScadaArchiveMemberReport:
    member_name: str
    source_hash: str
    row_count: int
    duplicate_rows: int
    tags: tuple[str, ...]
    start_at: datetime
    end_at: datetime
    median_interval_minutes: float
    quality_counts: dict[str, int] = field(default_factory=dict)
    minimum_value: float | None = None
    maximum_value: float | None = None


@dataclass(frozen=True)
class ScadaArchiveReport:
    source_filename: str
    source_hash: str
    member_reports: tuple[ScadaArchiveMemberReport, ...]
    observed_tags: tuple[str, ...]
    missing_tags: tuple[str, ...]
    total_rows: int
    duplicate_rows: int
    aligned_hour_count: int
    strict_good_hour_count: int
    conditional_hour_count: int
    degraded_hour_count: int
    validation_status: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScadaArchiveImportResult:
    report: ScadaArchiveReport
    import_results: tuple[ScadaImportResult, ...]

    @property
    def rows_imported(self) -> int:
        return sum(result.row_count for result in self.import_results if result.imported)

    @property
    def files_imported(self) -> int:
        return sum(1 for result in self.import_results if result.imported)

    @property
    def duplicate_files_skipped(self) -> int:
        return sum(1 for result in self.import_results if result.skipped_duplicate)


class ScadaArchiveService:
    """Validate and import filename-agnostic SCADA CSV archives."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory
        self.import_service = ScadaImportService(session_factory=session_factory)

    def can_handle(self, source_path: str | Path) -> bool:
        source = Path(source_path)
        if source.suffix.lower() != ".zip":
            return False
        try:
            report, _ = self._inspect(source)
        except (BadZipFile, OSError, UnicodeDecodeError, ValueError):
            return False
        return bool(report.observed_tags)

    def inspect_archive(self, source_path: str | Path) -> ScadaArchiveReport:
        source = self._validate_source(source_path)
        report, _ = self._inspect(source)
        if report.missing_tags:
            raise ValueError(
                "SCADA archive is missing required tag(s): "
                + ", ".join(report.missing_tags)
            )
        return report

    def import_archive(self, source_path: str | Path) -> ScadaArchiveImportResult:
        source = self._validate_source(source_path)
        report, payloads = self._inspect(source)
        if report.missing_tags:
            raise ValueError(
                "SCADA archive is missing required tag(s): "
                + ", ".join(report.missing_tags)
            )
        results = tuple(
            self.import_service.import_payload(
                payload,
                source_filename=member_name,
                source_path=f"{source.resolve()}::{member_name}",
            )
            for member_name, payload in payloads
        )
        return ScadaArchiveImportResult(report=report, import_results=results)

    @staticmethod
    def _validate_source(source_path: str | Path) -> Path:
        source = Path(source_path)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"SCADA archive not found: {source}")
        if source.suffix.lower() != ".zip":
            raise ValueError("SCADA archive must be a ZIP file")
        return source

    def _inspect(
        self,
        source: Path,
    ) -> tuple[ScadaArchiveReport, list[tuple[str, bytes]]]:
        payloads: list[tuple[str, bytes]] = []
        member_reports: list[ScadaArchiveMemberReport] = []
        all_measurements: list[dict[str, object]] = []
        with ZipFile(source) as archive:
            members = [
                info
                for info in archive.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".csv")
            ]
            if not members:
                raise ValueError("SCADA archive contains no CSV files")
            for info in members:
                if info.flag_bits & 0x1:
                    raise ValueError(f"Encrypted archive member is not supported: {info.filename}")
                if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise ValueError(f"Archive member exceeds size limit: {info.filename}")
                payload = archive.read(info)
                parsed = self.import_service.parse_measurements_bytes(payload)
                if not parsed.measurements:
                    raise ValueError(f"SCADA CSV contains no rows: {info.filename}")
                enriched = [
                    {**row, "source_filename": info.filename}
                    for row in parsed.measurements
                ]
                all_measurements.extend(enriched)
                payloads.append((info.filename, payload))
                member_reports.append(
                    self._member_report(
                        info.filename,
                        payload,
                        parsed.measurements,
                        parsed.duplicate_rows_skipped,
                    )
                )

        observed_tags = tuple(
            sorted(
                {
                    str(row["tag_name"]).strip()
                    for row in all_measurements
                    if str(row["tag_name"]).strip() in SCADA_TAG_FIELD_MAP
                }
            )
        )
        missing_tags = tuple(sorted(set(SCADA_TAG_FIELD_MAP) - set(observed_tags)))
        snapshots = ScadaSnapshotService(
            session_factory=self.session_factory
        ).preview_hourly_snapshots(all_measurements)
        strict_count = sum(row.quality_status == "GOOD" for row in snapshots)
        conditional_count = sum(
            row.quality_status == "USABLE_WITH_WARNING" for row in snapshots
        )
        degraded_count = sum(row.quality_status == "DEGRADED" for row in snapshots)
        warnings: list[str] = []
        quality_counts = Counter(
            str(row["quality"]).strip().lower() for row in all_measurements
        )
        if quality_counts.get("other"):
            warnings.append(
                "'Other' quality is preserved and conditionally weighted; engineering approval is required for production use"
            )
        excluded = sorted(set(quality_counts) - {"good", "other"})
        if excluded:
            warnings.append("Excluded quality values present: " + ", ".join(excluded))
        if degraded_count:
            warnings.append(f"{degraded_count} hourly snapshot(s) fail coverage or quality gates")
        if conditional_count:
            warnings.append(
                f"{conditional_count} hourly snapshot(s) are usable with quality warnings"
            )
        if len(snapshots) < 24 * 60:
            warnings.append(
                "Less than 60 days of aligned history; model results remain prototype-only"
            )

        report = ScadaArchiveReport(
            source_filename=source.name,
            source_hash=_file_hash(source),
            member_reports=tuple(member_reports),
            observed_tags=observed_tags,
            missing_tags=missing_tags,
            total_rows=sum(item.row_count for item in member_reports),
            duplicate_rows=sum(item.duplicate_rows for item in member_reports),
            aligned_hour_count=strict_count + conditional_count,
            strict_good_hour_count=strict_count,
            conditional_hour_count=conditional_count,
            degraded_hour_count=degraded_count,
            validation_status="VALID" if not missing_tags else "INVALID",
            warnings=tuple(warnings),
        )
        return report, payloads

    @staticmethod
    def _member_report(
        member_name: str,
        payload: bytes,
        measurements: list[dict[str, object]],
        duplicates: int,
    ) -> ScadaArchiveMemberReport:
        start_times = [
            row["start_time"]
            for row in measurements
            if isinstance(row.get("start_time"), datetime)
        ]
        end_times = [
            row["end_time"]
            for row in measurements
            if isinstance(row.get("end_time"), datetime)
        ]
        if not start_times or not end_times:
            raise ValueError(f"SCADA CSV has no valid intervals: {member_name}")
        intervals = [
            (end - start).total_seconds() / 60.0
            for start, end in zip(start_times, end_times)
            if end > start
        ]
        if not intervals:
            raise ValueError(f"SCADA CSV has no positive intervals: {member_name}")
        values = [float(row["avg_value"]) for row in measurements]
        return ScadaArchiveMemberReport(
            member_name=member_name,
            source_hash=hashlib.sha256(payload).hexdigest(),
            row_count=len(measurements),
            duplicate_rows=duplicates,
            tags=tuple(sorted({str(row["tag_name"]).strip() for row in measurements})),
            start_at=min(start_times),
            end_at=max(end_times),
            median_interval_minutes=round(median(intervals), 4),
            quality_counts=dict(
                sorted(Counter(str(row["quality"]).strip() for row in measurements).items())
            ),
            minimum_value=min(values),
            maximum_value=max(values),
        )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

