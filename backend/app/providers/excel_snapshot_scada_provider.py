from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo
from zipfile import BadZipFile, ZipFile

from app.providers.grid_provider import GridProvider
from app.schemas.grid import GenerationUnitResponse, GridStatusResponse
from app.schemas.live_scada_experiment import (
    SnapshotFieldEvidence,
    SnapshotHourlyPoint,
    SnapshotImportSummary,
)
from app.services.scada_data_contract import normalize_quality


TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")
SOURCE_TIMEZONE = "America/Port_of_Spain"
REQUIRED_HEADERS = {
    "pen index",
    "name",
    "start time",
    "end time",
    "min time",
    "min value",
    "max time",
    "max value",
    "avg value",
    "quality",
}


@dataclass(frozen=True)
class SnapshotTag:
    canonical_field: str
    engineering_unit: str
    minimum: float
    maximum: float


TAG_ALIASES: dict[str, SnapshotTag] = {
    "PTL132 GENERATION TOTALS": SnapshotTag(
        "current_demand_mw", "MW", 0.0, 2500.0
    ),
    "MHO132 AVERAGE AMBIENT TEMPERATURE": SnapshotTag(
        "temperature_c", "degC", -10.0, 60.0
    ),
    "MHO132 TRINIDAD AVERAGE AMBIENT TEMP": SnapshotTag(
        "temperature_c", "degC", -10.0, 60.0
    ),
    "GSYS SYSTEM_CORRECTED_SPIN_TOTAL": SnapshotTag(
        "spinning_reserve_mw", "MW", -500.0, 1000.0
    ),
    "GSYS SYSTEM_AVAIL_TOTAL": SnapshotTag(
        "available_capacity_ta_mw", "MW", 0.0, 4000.0
    ),
    "GSYS SYSTEM_ONLN_TOTAL": SnapshotTag(
        "generation_tra_mw", "MW", 0.0, 3000.0
    ),
}
REQUIRED_FIELDS = (
    "current_demand_mw",
    "temperature_c",
    "spinning_reserve_mw",
    "available_capacity_ta_mw",
    "generation_tra_mw",
)
BOUNDARY_FIELDS = (
    "current_demand_mw",
    "temperature_c",
    "spinning_reserve_mw",
    "generation_tra_mw",
)


@dataclass
class SnapshotRecord:
    source_member: str
    line_number: int
    source_tag: str
    canonical_field: str
    engineering_unit: str
    start_time: datetime
    end_time: datetime
    avg_value: float
    raw_avg_value: str
    raw_quality: str
    normalized_quality: str
    raw_row: dict[str, str]
    warnings: list[str] = field(default_factory=list)

    @property
    def value_timestamp(self) -> datetime:
        return max(self.start_time, self.end_time)

    def audit_payload(self) -> dict[str, object]:
        return {
            "source_member": self.source_member,
            "line_number": self.line_number,
            "source_tag": self.source_tag,
            "canonical_field": self.canonical_field,
            "engineering_unit": self.engineering_unit,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "avg_value": self.avg_value,
            "raw_avg_value": self.raw_avg_value,
            "raw_quality": self.raw_quality,
            "normalized_quality": self.normalized_quality,
            "warnings": self.warnings,
        }


@dataclass
class SnapshotProviderResult:
    summary: SnapshotImportSummary
    raw_audit_rows: list[dict[str, object]]
    cleaned_audit_rows: list[dict[str, object]]


class SnapshotMissingRequiredVariablesError(RuntimeError):
    pass


class ExcelSnapshotScadaProvider(GridProvider):
    """Read one immutable Excel/OSI trend-export snapshot.

    The supplied July package is a ZIP of CSV sheets exported from Excel/OSI.
    This provider intentionally never imports those rows into the normal WGDSS
    SCADA tables and never writes to the source archive.
    """

    def __init__(
        self,
        source_path: str | Path,
        *,
        imported_at: datetime | None = None,
        future_tolerance: timedelta = timedelta(minutes=5),
    ) -> None:
        self.source_path = Path(source_path)
        self.imported_at = (imported_at or datetime.now(TRINIDAD_TZ)).astimezone(
            TRINIDAD_TZ
        )
        self.future_tolerance = future_tolerance
        self._result: SnapshotProviderResult | None = None

    def load_snapshot(self) -> SnapshotProviderResult:
        if self._result is not None:
            return self._result
        if not self.source_path.is_file():
            raise FileNotFoundError(
                f"Experimental SCADA snapshot not found: {self.source_path}"
            )

        source_hash_before = _sha256_file(self.source_path)
        members = self._read_source_members()
        raw_audit_rows: list[dict[str, object]] = []
        parsed: list[SnapshotRecord] = []
        malformed = 0
        for member_name, payload in members:
            member_records, member_raw, member_malformed = self._parse_csv_member(
                member_name,
                payload,
            )
            parsed.extend(member_records)
            raw_audit_rows.extend(member_raw)
            malformed += member_malformed

        source_hash_after = _sha256_file(self.source_path)
        if source_hash_before != source_hash_after:
            raise RuntimeError(
                "SCADA snapshot changed while being read; session creation aborted"
            )

        deduplicated, duplicate_count = self._deduplicate(parsed)
        cleaned, future_count, range_warning_count = self._validate_records(
            deduplicated
        )
        by_field: dict[str, list[SnapshotRecord]] = defaultdict(list)
        for record in cleaned:
            by_field[record.canonical_field].append(record)
        for records in by_field.values():
            records.sort(key=lambda item: (item.start_time, item.end_time))

        missing = [field for field in REQUIRED_FIELDS if not by_field.get(field)]
        boundary = self._latest_common_boundary(by_field)
        field_evidence = self._field_evidence(by_field, boundary, missing)
        warnings = self._quality_warnings(
            by_field=by_field,
            missing=missing,
            malformed=malformed,
            duplicate_count=duplicate_count,
            future_count=future_count,
            range_warning_count=range_warning_count,
        )
        hourly = self._hourly_series(by_field, boundary)
        available_start = min(
            (record.start_time for record in cleaned),
            default=None,
        )
        available_end = max(
            (record.value_timestamp for record in cleaned),
            default=None,
        )
        model_issue_hour = (
            boundary.replace(minute=0, second=0, microsecond=0)
            if boundary is not None
            else None
        )
        summary = SnapshotImportSummary(
            source_filename=self.source_path.name,
            source_path=self.source_path.name,
            source_file_hash=source_hash_before,
            source_format=(
                "zip_csv_excel_export"
                if self.source_path.suffix.lower() == ".zip"
                else "csv_excel_export"
            ),
            imported_at=self.imported_at,
            available_start=available_start,
            available_end=available_end,
            latest_valid_timestamp=boundary,
            model_issue_hour=model_issue_hour,
            raw_record_count=len(raw_audit_rows),
            cleaned_record_count=len(cleaned),
            malformed_record_count=malformed,
            duplicate_record_count=duplicate_count,
            future_record_count=future_count,
            missing_required_variables=missing,
            field_evidence=field_evidence,
            hourly_series=hourly,
            warnings=warnings,
        )
        self._result = SnapshotProviderResult(
            summary=summary,
            raw_audit_rows=raw_audit_rows,
            cleaned_audit_rows=[record.audit_payload() for record in cleaned],
        )
        return self._result

    async def get_generation_status(self) -> list[GenerationUnitResponse]:
        # The supplied snapshot is aggregate telemetry, not a unit roster.
        return []

    async def get_grid_status(self) -> GridStatusResponse:
        result = self.load_snapshot()
        evidence = {
            item.field: item for item in result.summary.field_evidence
        }
        missing = [
            field
            for field in (
                "current_demand_mw",
                "generation_tra_mw",
                "available_capacity_ta_mw",
            )
            if evidence.get(field) is None
            or evidence[field].cleaned_value is None
        ]
        if missing:
            raise SnapshotMissingRequiredVariablesError(
                "GridProvider compatibility requires missing field(s): "
                + ", ".join(missing)
            )
        demand = float(evidence["current_demand_mw"].cleaned_value)
        generation = float(evidence["generation_tra_mw"].cleaned_value)
        available = float(evidence["available_capacity_ta_mw"].cleaned_value)
        spin = evidence.get("spinning_reserve_mw")
        margin = (
            (available - demand) / demand * 100.0 if demand > 0 else 0.0
        )
        return GridStatusResponse(
            timestamp=result.summary.latest_valid_timestamp,
            received_at=result.summary.imported_at,
            current_demand_mw=demand,
            current_generation_mw=generation,
            total_available_capacity_mw=available,
            reserve_margin_percent=round(margin, 2),
            spinning_reserve_mw=(
                spin.cleaned_value if spin is not None else None
            ),
            spinning_reserve_source="GSYS SYSTEM_CORRECTED_SPIN_TOTAL",
            grid_status="EXPERIMENTAL_SNAPSHOT",
            demand_period=_demand_period(
                result.summary.latest_valid_timestamp.hour
                if result.summary.latest_valid_timestamp
                else 0
            ),
            source_provider="ExcelSnapshotScadaProvider",
            generation_units=[],
            quality_status="UNCERTAIN",
            missing_fields=result.summary.missing_required_variables,
        )

    def _read_source_members(self) -> list[tuple[str, bytes]]:
        suffix = self.source_path.suffix.lower()
        if suffix == ".csv":
            return [(self.source_path.name, self.source_path.read_bytes())]
        if suffix != ".zip":
            raise ValueError(
                "ExcelSnapshotScadaProvider supports CSV files or ZIP archives "
                "containing CSV trend exports"
            )
        try:
            with ZipFile(self.source_path) as archive:
                members = [
                    item
                    for item in archive.infolist()
                    if not item.is_dir() and item.filename.lower().endswith(".csv")
                ]
                if not members:
                    raise ValueError(
                        "SCADA snapshot ZIP contains no CSV trend-export members"
                    )
                return [
                    (item.filename, archive.read(item))
                    for item in sorted(members, key=lambda value: value.filename)
                ]
        except BadZipFile as exc:
            raise ValueError("SCADA snapshot is not a valid ZIP archive") from exc

    def _parse_csv_member(
        self,
        member_name: str,
        payload: bytes,
    ) -> tuple[list[SnapshotRecord], list[dict[str, object]], int]:
        text = _decode_csv(payload)
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames is None:
            raise ValueError(f"{member_name} is missing a header row")
        header_map = {
            _normalize_header(name): name
            for name in reader.fieldnames
            if name is not None
        }
        missing_headers = sorted(REQUIRED_HEADERS - set(header_map))
        if missing_headers:
            raise ValueError(
                f"{member_name} is missing required header(s): "
                + ", ".join(missing_headers)
            )

        records: list[SnapshotRecord] = []
        raw_audit: list[dict[str, object]] = []
        malformed = 0
        for line_number, source_row in enumerate(reader, start=2):
            raw = {
                key: (source_row.get(original) or "")
                for key, original in header_map.items()
            }
            if not any(value.strip() for value in raw.values()):
                continue
            raw_entry: dict[str, object] = {
                "source_member": member_name,
                "line_number": line_number,
                "raw": raw,
                "parse_status": "accepted",
                "errors": [],
            }
            try:
                record = self._parse_record(member_name, line_number, raw)
                records.append(record)
            except ValueError as exc:
                malformed += 1
                raw_entry["parse_status"] = "rejected"
                raw_entry["errors"] = [str(exc)]
            raw_audit.append(raw_entry)
        return records, raw_audit, malformed

    def _parse_record(
        self,
        member_name: str,
        line_number: int,
        row: dict[str, str],
    ) -> SnapshotRecord:
        source_tag = " ".join(row["name"].strip().split())
        tag = TAG_ALIASES.get(source_tag)
        if tag is None:
            raise ValueError(
                f"line {line_number}: unsupported source tag {source_tag!r}"
            )
        start = _parse_datetime(row["start time"], line_number, "Start Time")
        end = _parse_datetime(row["end time"], line_number, "End Time")
        raw_avg = row["avg value"].strip()
        value = _parse_float(raw_avg, line_number, "Avg Value")
        quality = row["quality"].strip() or "Unknown"
        warnings: list[str] = []
        if end < start:
            raise ValueError(f"line {line_number}: End Time precedes Start Time")
        if end == start:
            warnings.append("point_sample")
        if not tag.minimum <= value <= tag.maximum:
            warnings.append("value_outside_provisional_range")
        if normalize_quality(quality).value == "unknown":
            warnings.append("quality_mapping_unconfirmed")
        return SnapshotRecord(
            source_member=member_name,
            line_number=line_number,
            source_tag=source_tag,
            canonical_field=tag.canonical_field,
            engineering_unit=tag.engineering_unit,
            start_time=start,
            end_time=end,
            avg_value=value,
            raw_avg_value=raw_avg,
            raw_quality=quality,
            normalized_quality=normalize_quality(quality).value,
            raw_row=row,
            warnings=warnings,
        )

    @staticmethod
    def _deduplicate(
        records: Iterable[SnapshotRecord],
    ) -> tuple[list[SnapshotRecord], int]:
        unique: list[SnapshotRecord] = []
        seen: set[tuple[object, ...]] = set()
        duplicates = 0
        for record in records:
            identity = (
                record.canonical_field,
                record.start_time,
                record.end_time,
                record.avg_value,
                record.raw_quality.strip().lower(),
            )
            if identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            unique.append(record)
        return unique, duplicates

    def _validate_records(
        self,
        records: Iterable[SnapshotRecord],
    ) -> tuple[list[SnapshotRecord], int, int]:
        cleaned: list[SnapshotRecord] = []
        future_count = 0
        range_warning_count = 0
        future_limit = self.imported_at + self.future_tolerance
        for record in records:
            if record.value_timestamp > future_limit:
                record.warnings.append("future_record_excluded")
                future_count += 1
                continue
            if "value_outside_provisional_range" in record.warnings:
                range_warning_count += 1
                continue
            cleaned.append(record)
        return cleaned, future_count, range_warning_count

    @staticmethod
    def _latest_common_boundary(
        by_field: dict[str, list[SnapshotRecord]],
    ) -> datetime | None:
        latest = [
            max(record.value_timestamp for record in by_field[field])
            for field in BOUNDARY_FIELDS
            if by_field.get(field)
        ]
        if len(latest) != len(BOUNDARY_FIELDS):
            return min(latest) if latest else None
        return min(latest)

    def _field_evidence(
        self,
        by_field: dict[str, list[SnapshotRecord]],
        boundary: datetime | None,
        missing: list[str],
    ) -> list[SnapshotFieldEvidence]:
        evidence: list[SnapshotFieldEvidence] = []
        for field_name in REQUIRED_FIELDS:
            candidates = [
                record
                for record in by_field.get(field_name, [])
                if boundary is None or record.value_timestamp <= boundary
            ]
            if not candidates:
                evidence.append(
                    SnapshotFieldEvidence(
                        field=field_name,
                        engineering_unit=(
                            "degC" if field_name == "temperature_c" else "MW"
                        ),
                        status="MISSING_REQUIRED",
                        warnings=["No accepted source record was supplied"],
                    )
                )
                continue
            record = max(candidates, key=lambda item: item.value_timestamp)
            evidence.append(
                SnapshotFieldEvidence(
                    field=field_name,
                    source_tag=record.source_tag,
                    source_member=record.source_member,
                    timestamp=record.value_timestamp,
                    raw_value=record.raw_avg_value,
                    cleaned_value=record.avg_value,
                    engineering_unit=record.engineering_unit,
                    raw_quality=record.raw_quality,
                    normalized_quality=record.normalized_quality,
                    status=(
                        "AVAILABLE_WITH_WARNING"
                        if record.warnings
                        or record.normalized_quality != "good"
                        else "AVAILABLE"
                    ),
                    warnings=list(record.warnings),
                )
            )
        return evidence

    def _quality_warnings(
        self,
        *,
        by_field: dict[str, list[SnapshotRecord]],
        missing: list[str],
        malformed: int,
        duplicate_count: int,
        future_count: int,
        range_warning_count: int,
    ) -> list[str]:
        warnings: list[str] = []
        if missing:
            warnings.append(
                "Missing required variable(s): " + ", ".join(missing)
            )
        if malformed:
            warnings.append(f"{malformed} malformed record(s) were excluded")
        if duplicate_count:
            warnings.append(
                f"{duplicate_count} exact duplicate record(s) were excluded"
            )
        if future_count:
            warnings.append(f"{future_count} future record(s) were excluded")
        if range_warning_count:
            warnings.append(
                f"{range_warning_count} impossible or unit-inconsistent value(s) "
                "were excluded using provisional validation bounds"
            )
        for field_name, records in sorted(by_field.items()):
            gaps = _detect_gaps(records)
            if gaps:
                warnings.append(
                    f"{field_name}: {len(gaps)} sampling gap(s) exceed the "
                    "source-specific expected interval"
                )
        warnings.append(
            "Engineering units and tag semantics remain pending T&TEC/OSI confirmation"
        )
        return warnings

    def _hourly_series(
        self,
        by_field: dict[str, list[SnapshotRecord]],
        boundary: datetime | None,
    ) -> list[SnapshotHourlyPoint]:
        if boundary is None:
            return []
        starts = [
            record.start_time
            for records in by_field.values()
            for record in records
            if record.start_time <= boundary
        ]
        if not starts:
            return []
        hour = min(starts).replace(minute=0, second=0, microsecond=0)
        end_hour = boundary.replace(minute=0, second=0, microsecond=0)
        points: list[SnapshotHourlyPoint] = []
        while hour <= end_hour:
            interval_end = min(hour + timedelta(hours=1), boundary)
            if interval_end <= hour:
                break
            values: dict[str, float | None] = {}
            coverage: dict[str, float] = {}
            point_warnings: list[str] = []
            for field_name in REQUIRED_FIELDS:
                value, coverage_percent = _aggregate_interval(
                    by_field.get(field_name, []),
                    hour,
                    interval_end,
                )
                values[field_name] = value
                coverage[field_name] = coverage_percent
                if coverage_percent < 90.0:
                    point_warnings.append(
                        f"{field_name} coverage {coverage_percent:.1f}%"
                    )
            quality_status = (
                "GOOD"
                if not point_warnings and all(
                    values.get(field) is not None for field in REQUIRED_FIELDS
                )
                else "INCOMPLETE"
                if any(
                    values.get(field) is None
                    for field in ("current_demand_mw", "generation_tra_mw")
                )
                else "USABLE_WITH_WARNING"
            )
            points.append(
                SnapshotHourlyPoint(
                    timestamp=hour,
                    available_at=interval_end,
                    demand_mw=values["current_demand_mw"],
                    generation_tra_mw=values["generation_tra_mw"],
                    spinning_reserve_mw=values["spinning_reserve_mw"],
                    available_capacity_ta_mw=values[
                        "available_capacity_ta_mw"
                    ],
                    temperature_c=values["temperature_c"],
                    coverage_percent={
                        key: round(value, 1)
                        for key, value in coverage.items()
                    },
                    quality_status=quality_status,
                    warnings=point_warnings,
                )
            )
            hour += timedelta(hours=1)
        return points


def _decode_csv(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV member is not UTF-8, UTF-16, or CP1252")


def _normalize_header(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def _parse_datetime(value: str, line: int, field_name: str) -> datetime:
    raw = " ".join(value.strip().split())
    if not raw:
        raise ValueError(f"line {line}: missing {field_name}")
    try:
        serial = float(raw)
    except ValueError:
        serial = None
    if serial is not None:
        return datetime(1899, 12, 30, tzinfo=TRINIDAD_TZ) + timedelta(
            days=serial
        )
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in (
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%y %H:%M:%S",
            "%m/%d/%y %H:%M",
            "%m/%d/%Y %I:%M:%S %p",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%y %I:%M:%S %p",
            "%m/%d/%y %I:%M %p",
        ):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValueError(f"line {line}: invalid {field_name} {value!r}")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TRINIDAD_TZ)
    return parsed.astimezone(TRINIDAD_TZ)


def _parse_float(value: str, line: int, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"line {line}: invalid {field_name} {value!r}"
        ) from exc
    if not math.isfinite(parsed):
        raise ValueError(f"line {line}: non-finite {field_name}")
    return parsed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _detect_gaps(records: list[SnapshotRecord]) -> list[float]:
    ordered = sorted(records, key=lambda item: item.start_time)
    if len(ordered) < 3:
        return []
    deltas = [
        (current.start_time - previous.start_time).total_seconds()
        for previous, current in zip(ordered, ordered[1:])
        if current.start_time > previous.start_time
    ]
    if not deltas:
        return []
    expected = statistics.median(deltas)
    threshold = max(expected * 3.0, 300.0)
    return [delta for delta in deltas if delta > threshold]


def _effective_intervals(
    records: list[SnapshotRecord],
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime, SnapshotRecord]]:
    ordered = sorted(records, key=lambda item: (item.start_time, item.end_time))
    intervals: list[tuple[datetime, datetime, SnapshotRecord]] = []
    deltas = [
        (right.start_time - left.start_time).total_seconds()
        for left, right in zip(ordered, ordered[1:])
        if right.start_time > left.start_time
    ]
    expected = statistics.median(deltas) if deltas else 60.0
    for index, record in enumerate(ordered):
        record_end = record.end_time
        if record_end <= record.start_time:
            next_start = (
                ordered[index + 1].start_time
                if index + 1 < len(ordered)
                else record.start_time + timedelta(seconds=expected)
            )
            record_end = min(
                next_start,
                record.start_time + timedelta(seconds=max(expected, 1.0)),
            )
        overlap_start = max(start, record.start_time)
        overlap_end = min(end, record_end)
        if overlap_end > overlap_start:
            intervals.append((overlap_start, overlap_end, record))
    return intervals


def _aggregate_interval(
    records: list[SnapshotRecord],
    start: datetime,
    end: datetime,
) -> tuple[float | None, float]:
    intervals = _effective_intervals(records, start, end)
    duration = (end - start).total_seconds()
    if not intervals or duration <= 0:
        return None, 0.0
    boundaries = sorted(
        {start, end}
        | {left for left, _, _ in intervals}
        | {right for _, right, _ in intervals}
    )
    weighted = 0.0
    covered = 0.0
    for left, right in zip(boundaries, boundaries[1:]):
        midpoint = left + (right - left) / 2
        candidates = [
            record
            for interval_start, interval_end, record in intervals
            if interval_start <= midpoint < interval_end
        ]
        if not candidates:
            continue
        record = max(candidates, key=lambda item: item.start_time)
        seconds = (right - left).total_seconds()
        weighted += record.avg_value * seconds
        covered += seconds
    if covered <= 0:
        return None, 0.0
    return round(weighted / covered, 4), min(100.0, covered / duration * 100.0)


def _demand_period(hour: int) -> str:
    if hour < 6:
        return "NIGHT"
    if hour < 12:
        return "MORNING"
    if hour < 17:
        return "AFTERNOON"
    if hour < 22:
        return "EVENING_PEAK"
    return "LATE_NIGHT"
