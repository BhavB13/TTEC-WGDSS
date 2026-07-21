from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select

from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.scada import ScadaArchiveImportRun
from app.services.scada_import_service import ScadaImportResult, ScadaImportService
from app.services.scada_snapshot_service import SCADA_TAG_FIELD_MAP, ScadaSnapshotService


MAX_ARCHIVE_MEMBER_BYTES = 100 * 1024 * 1024
MIN_PERIOD_INFERENCE_CONFIDENCE = 0.80


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
    normalized_quality_counts: dict[str, int] = field(default_factory=dict)
    anomaly_counts: dict[str, int] = field(default_factory=dict)
    reporting_period: str | None = None
    reporting_start_at: datetime | None = None
    reporting_end_at: datetime | None = None
    period_inference_confidence: float = 0.0
    source_row_count: int = 0
    clean_row_count: int = 0
    out_of_period_rows: int = 0


@dataclass(frozen=True)
class ScadaArchivePeriodReport:
    period: str
    reporting_start_at: datetime
    reporting_end_at: datetime
    observed_tags: tuple[str, ...]
    missing_tags: tuple[str, ...]
    source_row_count: int
    normalized_row_count: int
    clean_row_count: int
    duplicate_rows: int
    out_of_period_rows: int
    aligned_hour_count: int
    strict_good_hour_count: int
    conditional_hour_count: int
    degraded_hour_count: int
    validation_status: str


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
    normalized_quality_counts: dict[str, int] = field(default_factory=dict)
    anomaly_counts: dict[str, int] = field(default_factory=dict)
    source_row_count: int = 0
    clean_row_count: int = 0
    out_of_period_rows: int = 0
    period_reports: tuple[ScadaArchivePeriodReport, ...] = ()


@dataclass(frozen=True)
class _ArchivePayload:
    member_name: str
    payload: bytes
    reporting_period: str | None
    reporting_start_at: datetime | None
    reporting_end_at: datetime | None


@dataclass(frozen=True)
class ScadaArchiveImportResult:
    report: ScadaArchiveReport
    import_results: tuple[ScadaImportResult, ...]
    archive_import_run_id: int | None = None
    skipped_duplicate: bool = False

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
    """Validate and import filename-agnostic, monthly SCADA CSV archives."""

    def __init__(
        self,
        session_factory=SessionLocal,
        *,
        import_service: ScadaImportService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.import_service = import_service or ScadaImportService(
            session_factory=session_factory
        )

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
        if self.session_factory is SessionLocal:
            initialize_database()

        with self.session_factory() as session:
            existing = session.scalar(
                select(ScadaArchiveImportRun).where(
                    ScadaArchiveImportRun.source_hash == report.source_hash
                )
            )
            if existing is not None:
                return ScadaArchiveImportResult(
                    report=report,
                    import_results=(),
                    archive_import_run_id=existing.id,
                    skipped_duplicate=True,
                )
            archive_run = ScadaArchiveImportRun(
                source_filename=source.name,
                source_path=str(source.resolve()),
                source_hash=report.source_hash,
                file_count=len(report.member_reports),
                source_row_count=report.source_row_count,
                normalized_row_count=report.total_rows,
                duplicate_row_count=report.duplicate_rows,
                out_of_period_row_count=report.out_of_period_rows,
                import_status="PENDING",
                data_start_at=min(item.start_at for item in report.member_reports),
                data_end_at=max(item.end_at for item in report.member_reports),
                validation_report=_report_json(report),
            )
            session.add(archive_run)
            session.commit()
            archive_run_id = archive_run.id

        try:
            results = tuple(
                self._member_import_service(item).import_payload(
                    item.payload,
                    source_filename=item.member_name,
                    source_path=f"{source.resolve()}::{item.member_name}",
                    archive_import_run_id=archive_run_id,
                    source_metadata_overrides={
                        "archive_source_hash": report.source_hash,
                        "reporting_period": item.reporting_period,
                        "reporting_start_at": (
                            item.reporting_start_at.isoformat()
                            if item.reporting_start_at is not None
                            else None
                        ),
                        "reporting_end_at": (
                            item.reporting_end_at.isoformat()
                            if item.reporting_end_at is not None
                            else None
                        ),
                    },
                )
                for item in payloads
            )
        except Exception as exc:
            self._set_archive_status(archive_run_id, "FAILED", report, error=str(exc))
            raise

        self._set_archive_status(archive_run_id, "IMPORTED", report)
        return ScadaArchiveImportResult(
            report=report,
            import_results=results,
            archive_import_run_id=archive_run_id,
        )

    def _set_archive_status(
        self,
        archive_run_id: int,
        status: str,
        report: ScadaArchiveReport,
        *,
        error: str | None = None,
    ) -> None:
        with self.session_factory() as session:
            archive_run = session.get(ScadaArchiveImportRun, archive_run_id)
            if archive_run is None:
                return
            archive_run.import_status = status
            payload = json.loads(_report_json(report))
            if error:
                payload["import_error"] = error
            archive_run.validation_report = json.dumps(payload, sort_keys=True)
            session.commit()

    def _member_import_service(self, payload: _ArchivePayload) -> ScadaImportService:
        if (
            self.import_service.expected_reporting_start is not None
            or self.import_service.expected_reporting_end is not None
        ):
            return self.import_service
        return ScadaImportService(
            session_factory=self.session_factory,
            expected_reporting_start=payload.reporting_start_at,
            expected_reporting_end=payload.reporting_end_at,
        )

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
    ) -> tuple[ScadaArchiveReport, list[_ArchivePayload]]:
        payloads: list[_ArchivePayload] = []
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
                    raise ValueError(
                        f"Encrypted archive member is not supported: {info.filename}"
                    )
                if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise ValueError(
                        f"Archive member exceeds size limit: {info.filename}"
                    )
                payload = archive.read(info)
                initial = self.import_service.parse_measurements_bytes(payload)
                if not initial.measurements:
                    raise ValueError(f"SCADA CSV contains no rows: {info.filename}")
                period, period_start, period_end, confidence = _infer_reporting_period(
                    initial.measurements
                )
                parser = self.import_service
                if (
                    parser.expected_reporting_start is None
                    and parser.expected_reporting_end is None
                    and period_start is not None
                    and period_end is not None
                ):
                    parser = ScadaImportService(
                        session_factory=self.session_factory,
                        expected_reporting_start=period_start,
                        expected_reporting_end=period_end,
                    )
                parsed = parser.parse_measurements_bytes(payload)
                enriched = [
                    {
                        **row,
                        "source_filename": info.filename,
                        "_reporting_period": period,
                    }
                    for row in parsed.measurements
                ]
                all_measurements.extend(enriched)
                payloads.append(
                    _ArchivePayload(
                        member_name=info.filename,
                        payload=payload,
                        reporting_period=period,
                        reporting_start_at=period_start,
                        reporting_end_at=period_end,
                    )
                )
                member_reports.append(
                    self._member_report(
                        info.filename,
                        payload,
                        parsed.measurements,
                        parsed.duplicate_rows_skipped,
                        parsed.quality_counts,
                        parsed.anomaly_counts,
                        reporting_period=period,
                        reporting_start_at=period_start,
                        reporting_end_at=period_end,
                        period_inference_confidence=confidence,
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
        strict_count, conditional_count, degraded_count = _snapshot_counts(snapshots)
        period_reports = self._period_reports(all_measurements, member_reports)

        warnings: list[str] = []
        quality_counts = Counter(
            str(row["quality"]).strip().lower() for row in all_measurements
        )
        normalized_quality_counts: Counter[str] = Counter()
        anomaly_counts: Counter[str] = Counter()
        for member_report in member_reports:
            normalized_quality_counts.update(member_report.normalized_quality_counts)
            anomaly_counts.update(member_report.anomaly_counts)
            if member_report.reporting_period is None:
                warnings.append(
                    f"Could not infer a reporting month for {member_report.member_name}; "
                    "out-of-month cleaning was not applied"
                )
        if quality_counts.get("other"):
            warnings.append(
                "'Other' quality is preserved and conditionally weighted; engineering approval is required for production use"
            )
        excluded = sorted(set(quality_counts) - {"good", "other"})
        if excluded:
            warnings.append("Excluded quality values present: " + ", ".join(excluded))
        for period_report in period_reports:
            if period_report.missing_tags:
                warnings.append(
                    f"{period_report.period} is missing tag(s): "
                    + ", ".join(period_report.missing_tags)
                )
        if degraded_count:
            warnings.append(
                f"{degraded_count} hourly snapshot(s) fail coverage or quality gates"
            )
        if conditional_count:
            warnings.append(
                f"{conditional_count} hourly snapshot(s) are usable with quality warnings"
            )
        if len(snapshots) < 24 * 60:
            warnings.append(
                "Less than 60 days of aligned history; model results remain prototype-only"
            )
        if anomaly_counts:
            warnings.append(
                "Source interval anomalies are present; inspect anomaly_counts before modeling"
            )

        has_period_gaps = any(item.missing_tags for item in period_reports)
        validation_status = (
            "INVALID"
            if missing_tags
            else "VALID_WITH_GAPS"
            if has_period_gaps
            else "VALID"
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
            validation_status=validation_status,
            warnings=tuple(dict.fromkeys(warnings)),
            normalized_quality_counts=dict(sorted(normalized_quality_counts.items())),
            anomaly_counts=dict(sorted(anomaly_counts.items())),
            source_row_count=sum(item.source_row_count for item in member_reports),
            clean_row_count=sum(item.clean_row_count for item in member_reports),
            out_of_period_rows=sum(item.out_of_period_rows for item in member_reports),
            period_reports=period_reports,
        )
        return report, payloads

    def _period_reports(
        self,
        measurements: list[dict[str, object]],
        member_reports: list[ScadaArchiveMemberReport],
    ) -> tuple[ScadaArchivePeriodReport, ...]:
        grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in measurements:
            period = row.get("_reporting_period")
            if isinstance(period, str):
                grouped[period].append(row)
        member_by_period: dict[str, list[ScadaArchiveMemberReport]] = defaultdict(list)
        for report in member_reports:
            if report.reporting_period is not None:
                member_by_period[report.reporting_period].append(report)

        reports: list[ScadaArchivePeriodReport] = []
        for period in sorted(grouped):
            period_members = member_by_period[period]
            period_rows = grouped[period]
            snapshots = ScadaSnapshotService(
                session_factory=self.session_factory
            ).preview_hourly_snapshots(period_rows)
            strict, conditional, degraded = _snapshot_counts(snapshots)
            observed = tuple(
                sorted(
                    {
                        str(row["tag_name"]).strip()
                        for row in period_rows
                        if str(row["tag_name"]).strip() in SCADA_TAG_FIELD_MAP
                    }
                )
            )
            missing = tuple(sorted(set(SCADA_TAG_FIELD_MAP) - set(observed)))
            period_start = next(
                item.reporting_start_at
                for item in period_members
                if item.reporting_start_at is not None
            )
            period_end = next(
                item.reporting_end_at
                for item in period_members
                if item.reporting_end_at is not None
            )
            reports.append(
                ScadaArchivePeriodReport(
                    period=period,
                    reporting_start_at=period_start,
                    reporting_end_at=period_end,
                    observed_tags=observed,
                    missing_tags=missing,
                    source_row_count=sum(item.source_row_count for item in period_members),
                    normalized_row_count=sum(item.row_count for item in period_members),
                    clean_row_count=sum(item.clean_row_count for item in period_members),
                    duplicate_rows=sum(item.duplicate_rows for item in period_members),
                    out_of_period_rows=sum(
                        item.out_of_period_rows for item in period_members
                    ),
                    aligned_hour_count=strict + conditional,
                    strict_good_hour_count=strict,
                    conditional_hour_count=conditional,
                    degraded_hour_count=degraded,
                    validation_status="VALID" if not missing else "PARTIAL",
                )
            )
        return tuple(reports)

    @staticmethod
    def _member_report(
        member_name: str,
        payload: bytes,
        measurements: list[dict[str, object]],
        duplicates: int,
        normalized_quality_counts: dict[str, int],
        anomaly_counts: dict[str, int],
        *,
        reporting_period: str | None,
        reporting_start_at: datetime | None,
        reporting_end_at: datetime | None,
        period_inference_confidence: float,
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
        out_of_period_rows = sum(
            _has_anomaly(row, "outside_expected_reporting_window")
            for row in measurements
        )
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
            normalized_quality_counts=normalized_quality_counts,
            anomaly_counts=anomaly_counts,
            reporting_period=reporting_period,
            reporting_start_at=reporting_start_at,
            reporting_end_at=reporting_end_at,
            period_inference_confidence=round(period_inference_confidence, 4),
            source_row_count=len(measurements) + duplicates,
            clean_row_count=len(measurements) - out_of_period_rows,
            out_of_period_rows=out_of_period_rows,
        )


def _infer_reporting_period(
    measurements: list[dict[str, Any]],
) -> tuple[str | None, datetime | None, datetime | None, float]:
    starts = [
        row["start_time"]
        for row in measurements
        if isinstance(row.get("start_time"), datetime)
    ]
    if not starts:
        return None, None, None, 0.0
    counts = Counter((value.year, value.month) for value in starts)
    (year, month), count = counts.most_common(1)[0]
    confidence = count / len(starts)
    if confidence < MIN_PERIOD_INFERENCE_CONFIDENCE:
        return None, None, None, confidence
    sample = next(value for value in starts if value.year == year and value.month == month)
    start = datetime(year, month, 1, tzinfo=sample.tzinfo)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=sample.tzinfo)
    else:
        end = datetime(year, month + 1, 1, tzinfo=sample.tzinfo)
    return f"{year:04d}-{month:02d}", start, end, confidence


def _has_anomaly(row: dict[str, object], anomaly: str) -> bool:
    raw = row.get("anomaly_flags")
    if not isinstance(raw, str):
        return False
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return isinstance(values, list) and anomaly in values


def _snapshot_counts(snapshots: list[Any]) -> tuple[int, int, int]:
    strict = sum(row.quality_status == "GOOD" for row in snapshots)
    conditional = sum(
        row.quality_status == "USABLE_WITH_WARNING" for row in snapshots
    )
    degraded = sum(row.quality_status == "DEGRADED" for row in snapshots)
    return strict, conditional, degraded


def _report_json(report: ScadaArchiveReport) -> str:
    return json.dumps(asdict(report), default=_json_default, sort_keys=True)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported archive report value: {type(value).__name__}")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
