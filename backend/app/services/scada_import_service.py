from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.scada import ScadaImportRun, ScadaRawMeasurement
from app.services.scada_data_contract import (
    AGGREGATION_INTERVAL_SUMMARY,
    SOURCE_PROVIDER,
    SOURCE_SYSTEM,
    SOURCE_TIMEZONE,
    TAG_REGISTRY,
    interval_anomalies,
    normalize_quality,
    stable_record_hash,
)

logger = logging.getLogger(__name__)

TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")

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
class ScadaImportResult:
    source_filename: str
    source_hash: str
    imported: bool
    import_run_id: int
    row_count: int
    skipped_duplicate: bool = False
    duplicate_rows_skipped: int = 0
    duplicate_records_skipped: int = 0
    anomaly_counts: dict[str, int] = field(default_factory=dict)
    quality_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ScadaParseResult:
    measurements: list[dict[str, Any]]
    duplicate_rows_skipped: int
    anomaly_counts: dict[str, int] = field(default_factory=dict)
    quality_counts: dict[str, int] = field(default_factory=dict)


class ScadaImportService:
    def __init__(
        self,
        session_factory=SessionLocal,
        *,
        expected_reporting_start: datetime | None = None,
        expected_reporting_end: datetime | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.expected_reporting_start = expected_reporting_start or parse_reporting_datetime(
            settings.SCADA_EXPECTED_REPORTING_START
        )
        self.expected_reporting_end = expected_reporting_end or parse_reporting_datetime(
            settings.SCADA_EXPECTED_REPORTING_END
        )

    def import_csv(self, csv_path: str | Path) -> ScadaImportResult:
        source = Path(csv_path)
        if not source.exists():
            raise FileNotFoundError(f"SCADA CSV not found: {source}")
        if not source.is_file():
            raise ValueError(f"SCADA CSV path is not a file: {source}")

        if self.session_factory is SessionLocal:
            initialize_database()
        payload = source.read_bytes()
        return self.import_payload(
            payload,
            source_filename=source.name,
            source_path=str(source.resolve()),
        )

    def import_payload(
        self,
        payload: bytes,
        *,
        source_filename: str,
        source_path: str,
    ) -> ScadaImportResult:
        """Import one CSV payload while preserving logical archive provenance."""
        if self.session_factory is SessionLocal:
            initialize_database()
        source_hash = hashlib.sha256(payload).hexdigest()
        parsed = self._read_measurements_text(payload.decode("utf-8-sig"))
        measurements = parsed.measurements
        duplicate_rows = parsed.duplicate_rows_skipped

        with self.session_factory() as session:
            existing = session.scalar(
                select(ScadaImportRun).where(ScadaImportRun.source_hash == source_hash)
            )
            if existing is not None:
                logger.info(
                    "Skipping duplicate SCADA import for %s with hash %s",
                    source_filename,
                    source_hash,
                )
                return ScadaImportResult(
                    source_filename=existing.source_filename,
                    source_hash=source_hash,
                    imported=False,
                    import_run_id=existing.id,
                    row_count=existing.row_count,
                    skipped_duplicate=True,
                    duplicate_rows_skipped=0,
                )

            record_hashes = [
                str(measurement["record_hash"])
                for measurement in measurements
                if measurement.get("record_hash")
            ]
            existing_record_hashes = set(
                session.scalars(
                    select(ScadaRawMeasurement.record_hash).where(
                        ScadaRawMeasurement.record_hash.in_(record_hashes)
                    )
                )
            )
            new_measurements = [
                measurement
                for measurement in measurements
                if measurement.get("record_hash") not in existing_record_hashes
            ]
            duplicate_records = len(measurements) - len(new_measurements)
            quality_report = {
                "schema": "wgdss-scada-ingestion-quality-v1",
                "source_system": SOURCE_SYSTEM,
                "source_provider": SOURCE_PROVIDER,
                "aggregation": AGGREGATION_INTERVAL_SUMMARY,
                "rows_parsed": len(measurements),
                "rows_imported": len(new_measurements),
                "exact_duplicates_within_file": duplicate_rows,
                "duplicate_records_already_stored": duplicate_records,
                "quality_counts": parsed.quality_counts,
                "anomaly_counts": parsed.anomaly_counts,
            }

            import_run = ScadaImportRun(
                source_filename=source_filename,
                source_path=source_path,
                source_hash=source_hash,
                row_count=len(new_measurements),
                import_status="IMPORTED",
                summary=(
                    f"Imported {len(new_measurements)} SCADA interval summary row(s); "
                    f"skipped {duplicate_rows} within-file and {duplicate_records} "
                    "previously stored exact duplicate row(s)"
                ),
                quality_report=json.dumps(quality_report, sort_keys=True),
            )
            session.add(import_run)
            session.flush()

            for measurement in new_measurements:
                measurement_payload = dict(measurement)
                metadata = json.loads(str(measurement_payload.pop("source_metadata")))
                metadata["source_path"] = source_path
                session.add(
                    ScadaRawMeasurement(
                        import_run_id=import_run.id,
                        source_filename=source_filename,
                        source_metadata=json.dumps(metadata, sort_keys=True),
                        **measurement_payload,
                    )
                )

            session.commit()
            return ScadaImportResult(
                source_filename=source_filename,
                source_hash=source_hash,
                imported=True,
                import_run_id=import_run.id,
                row_count=len(new_measurements),
                duplicate_rows_skipped=duplicate_rows,
                duplicate_records_skipped=duplicate_records,
                anomaly_counts=parsed.anomaly_counts,
                quality_counts=parsed.quality_counts,
            )

    def read_measurements(self, source: str | Path) -> list[dict[str, Any]]:
        """Parse and validate a SCADA export without persisting its rows."""
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"SCADA CSV not found: {path}")
        if not path.is_file():
            raise ValueError(f"SCADA CSV path is not a file: {path}")

        return self._read_measurements_text(
            path.read_text(encoding="utf-8-sig")
        ).measurements

    def read_measurements_bytes(self, payload: bytes) -> list[dict[str, Any]]:
        return self.parse_measurements_bytes(payload).measurements

    def parse_measurements_bytes(self, payload: bytes) -> ScadaParseResult:
        return self._read_measurements_text(payload.decode("utf-8-sig"))

    def _read_measurements_text(
        self,
        text: str,
    ) -> ScadaParseResult:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames is None:
            raise ValueError("SCADA CSV is missing a header row")

        header_map = self._build_header_map(reader.fieldnames)
        missing = sorted(REQUIRED_HEADERS - set(header_map))
        if missing:
            raise ValueError(
                "SCADA CSV is missing required header(s): " + ", ".join(missing)
            )

        measurements: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        duplicates = 0
        anomaly_counts: Counter[str] = Counter()
        quality_counts: Counter[str] = Counter()
        for line_number, row in enumerate(reader, start=2):
            raw_values = self._raw_row(row, header_map)
            normalized = {key: value.strip() for key, value in raw_values.items()}
            if not self._row_has_values(normalized):
                continue
            measurement = self._parse_measurement(
                normalized,
                line_number,
                source_tag_raw=raw_values.get("name"),
            )
            identity = self._measurement_identity(measurement)
            if identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            measurements.append(measurement)
            anomaly_counts.update(json.loads(str(measurement["anomaly_flags"])))
            quality_counts[str(measurement["normalized_quality"])] += 1
        return ScadaParseResult(
            measurements=measurements,
            duplicate_rows_skipped=duplicates,
            anomaly_counts=dict(sorted(anomaly_counts.items())),
            quality_counts=dict(sorted(quality_counts.items())),
        )

    @staticmethod
    def _measurement_identity(measurement: dict[str, Any]) -> tuple[Any, ...]:
        return (measurement["record_hash"],)

    @staticmethod
    def _build_header_map(fieldnames: list[str]) -> dict[str, str]:
        return {_normalize_header(name): name for name in fieldnames if name is not None}

    @staticmethod
    def _raw_row(row: dict[str, str | None], header_map: dict[str, str]) -> dict[str, str]:
        return {
            normalized: (row.get(original) or "")
            for normalized, original in header_map.items()
        }

    @staticmethod
    def _row_has_values(row: dict[str, str]) -> bool:
        return any(value.strip() for value in row.values())

    def _parse_measurement(
        self,
        row: dict[str, str],
        line_number: int,
        *,
        source_tag_raw: str | None,
    ) -> dict[str, Any]:
        tag_name = row["name"].strip()
        quality = row["quality"].strip() or "Unknown"
        if not tag_name:
            raise ValueError(f"SCADA CSV line {line_number} is missing Name")

        start_time = self._parse_datetime(row["start time"], "Start Time", line_number)
        if start_time is None:
            raise ValueError(f"SCADA CSV line {line_number} is missing Start Time")
        end_time = self._parse_datetime(row["end time"], "End Time", line_number)
        min_time = self._parse_datetime(row["min time"], "Min Time", line_number)
        min_value = self._parse_optional_float(row["min value"], "Min Value", line_number)
        max_time = self._parse_datetime(row["max time"], "Max Time", line_number)
        max_value = self._parse_optional_float(row["max value"], "Max Value", line_number)
        avg_value = self._parse_float(row["avg value"], "Avg Value", line_number)
        definition = TAG_REGISTRY.get(tag_name)
        anomalies = interval_anomalies(
            start_time=start_time,
            end_time=end_time,
            min_time=min_time,
            min_value=min_value,
            max_time=max_time,
            max_value=max_value,
            avg_value=avg_value,
            raw_quality=quality,
        )
        if definition is None:
            anomalies.append("unregistered_source_tag")
        if (
            self.expected_reporting_start is not None
            and start_time < self.expected_reporting_start
        ):
            anomalies.append("outside_expected_reporting_window")
        if (
            self.expected_reporting_end is not None
            and end_time is not None
            and end_time > self.expected_reporting_end
        ):
            anomalies.append("outside_expected_reporting_window")
        interval_seconds = (
            int((end_time - start_time).total_seconds())
            if end_time is not None and end_time > start_time
            else None
        )
        measurement = {
            "pen_index": self._parse_int(row["pen index"], "Pen Index", line_number),
            "tag_name": tag_name,
            "source_tag_raw": source_tag_raw,
            "canonical_variable": (
                definition.canonical_variable if definition is not None else None
            ),
            "start_time": start_time,
            "end_time": end_time,
            "min_time": min_time,
            "min_value": min_value,
            "max_time": max_time,
            "max_value": max_value,
            "avg_value": avg_value,
            "quality": quality,
            "normalized_quality": normalize_quality(quality).value,
            "source_system": SOURCE_SYSTEM,
            "source_provider": SOURCE_PROVIDER,
            "source_timezone": SOURCE_TIMEZONE,
            "interval_seconds": interval_seconds,
            "engineering_unit": definition.engineering_unit if definition else None,
            "aggregation": AGGREGATION_INTERVAL_SUMMARY,
            "anomaly_flags": json.dumps(list(dict.fromkeys(anomalies))),
            "source_metadata": json.dumps(
                {
                    "business_alias": definition.business_alias if definition else None,
                    "semantic_status": (
                        definition.semantic_status if definition else "unregistered"
                    ),
                },
                sort_keys=True,
            ),
        }
        measurement["record_hash"] = stable_record_hash(measurement)
        return measurement

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _parse_int(value: str, field_name: str, line_number: int) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"SCADA CSV line {line_number} has invalid {field_name}: {value!r}"
            ) from exc

    @classmethod
    def _parse_float(cls, value: str, field_name: str, line_number: int) -> float:
        parsed = cls._parse_optional_float(value, field_name, line_number)
        if parsed is None:
            raise ValueError(
                f"SCADA CSV line {line_number} is missing required {field_name}"
            )
        return parsed

    @staticmethod
    def _parse_optional_float(
        value: str,
        field_name: str,
        line_number: int,
    ) -> float | None:
        if value is None or value.strip() == "":
            return None
        try:
            parsed = float(value)
        except ValueError as exc:
            raise ValueError(
                f"SCADA CSV line {line_number} has invalid {field_name}: {value!r}"
            ) from exc
        if not math.isfinite(parsed):
            raise ValueError(
                f"SCADA CSV line {line_number} has non-finite {field_name}: {value!r}"
            )
        return parsed

    @staticmethod
    def _parse_datetime(value: str, field_name: str, line_number: int) -> datetime | None:
        if value is None or value.strip() == "":
            return None
        raw = " ".join(value.strip().split())
        if _looks_like_excel_serial(raw):
            return _excel_serial_to_datetime(float(raw))

        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return _ensure_tz(parsed)
        except ValueError:
            pass

        formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%y %H:%M:%S",
            "%m/%d/%y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%m/%d/%Y %I:%M:%S %p",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%y %I:%M:%S %p",
            "%m/%d/%y %I:%M %p",
            "%d/%m/%Y %I:%M:%S %p",
            "%d/%m/%Y %I:%M %p",
        )
        for date_format in formats:
            try:
                return _ensure_tz(datetime.strptime(raw, date_format))
            except ValueError:
                continue

        raise ValueError(
            f"SCADA CSV line {line_number} has invalid {field_name}: {value!r}"
        )


def _normalize_header(header: str) -> str:
    return " ".join(header.strip().lower().replace("_", " ").split())


def _looks_like_excel_serial(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _excel_serial_to_datetime(value: float) -> datetime:
    # Excel's Windows date system starts at 1899-12-30 after accounting for the
    # historical leap-year bug.
    return (datetime(1899, 12, 30, tzinfo=TRINIDAD_TZ) + timedelta(days=value))


def _ensure_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=TRINIDAD_TZ)
    return value


def parse_reporting_datetime(value: str | None) -> datetime | None:
    """Parse an explicit reporting boundary without inferring an export month."""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return _ensure_tz(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError as exc:
        raise ValueError(
            "SCADA expected reporting windows must use ISO-8601 timestamps"
        ) from exc
