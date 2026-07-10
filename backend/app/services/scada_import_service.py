from __future__ import annotations

import csv
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.scada import ScadaImportRun, ScadaRawMeasurement

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


class ScadaImportService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def import_csv(self, csv_path: str | Path) -> ScadaImportResult:
        source = Path(csv_path)
        if not source.exists():
            raise FileNotFoundError(f"SCADA CSV not found: {source}")
        if not source.is_file():
            raise ValueError(f"SCADA CSV path is not a file: {source}")

        if self.session_factory is SessionLocal:
            initialize_database()
        source_hash = self._file_hash(source)
        source_path = str(source.resolve())

        with self.session_factory() as session:
            existing = session.scalar(
                select(ScadaImportRun).where(ScadaImportRun.source_hash == source_hash)
            )
            if existing is not None:
                logger.info(
                    "Skipping duplicate SCADA import for %s with hash %s",
                    source.name,
                    source_hash,
                )
                return ScadaImportResult(
                    source_filename=existing.source_filename,
                    source_hash=source_hash,
                    imported=False,
                    import_run_id=existing.id,
                    row_count=existing.row_count,
                    skipped_duplicate=True,
                )

            measurements = self._read_measurements(source)
            import_run = ScadaImportRun(
                source_filename=source.name,
                source_path=source_path,
                source_hash=source_hash,
                row_count=len(measurements),
                import_status="IMPORTED",
                summary=f"Imported {len(measurements)} SCADA measurement row(s)",
            )
            session.add(import_run)
            session.flush()

            for measurement in measurements:
                session.add(
                    ScadaRawMeasurement(
                        import_run_id=import_run.id,
                        source_filename=source.name,
                        **measurement,
                    )
                )

            session.commit()
            return ScadaImportResult(
                source_filename=source.name,
                source_hash=source_hash,
                imported=True,
                import_run_id=import_run.id,
                row_count=len(measurements),
            )

    def _read_measurements(self, source: Path) -> list[dict[str, Any]]:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError("SCADA CSV is missing a header row")

            header_map = self._build_header_map(reader.fieldnames)
            missing = sorted(REQUIRED_HEADERS - set(header_map))
            if missing:
                raise ValueError(
                    "SCADA CSV is missing required header(s): " + ", ".join(missing)
                )

            measurements: list[dict[str, Any]] = []
            for line_number, row in enumerate(reader, start=2):
                normalized = self._normalize_row(row, header_map)
                if not self._row_has_values(normalized):
                    continue
                measurements.append(self._parse_measurement(normalized, line_number))

        return measurements

    @staticmethod
    def _build_header_map(fieldnames: list[str]) -> dict[str, str]:
        return {_normalize_header(name): name for name in fieldnames if name is not None}

    @staticmethod
    def _normalize_row(row: dict[str, str | None], header_map: dict[str, str]) -> dict[str, str]:
        return {
            normalized: (row.get(original) or "").strip()
            for normalized, original in header_map.items()
        }

    @staticmethod
    def _row_has_values(row: dict[str, str]) -> bool:
        return any(value.strip() for value in row.values())

    def _parse_measurement(
        self,
        row: dict[str, str],
        line_number: int,
    ) -> dict[str, Any]:
        tag_name = row["name"].strip()
        quality = row["quality"].strip() or "Unknown"
        if not tag_name:
            raise ValueError(f"SCADA CSV line {line_number} is missing Name")

        return {
            "pen_index": self._parse_int(row["pen index"], "Pen Index", line_number),
            "tag_name": tag_name,
            "start_time": self._parse_datetime(row["start time"], "Start Time", line_number),
            "end_time": self._parse_datetime(row["end time"], "End Time", line_number),
            "min_time": self._parse_datetime(row["min time"], "Min Time", line_number),
            "min_value": self._parse_optional_float(row["min value"], "Min Value", line_number),
            "max_time": self._parse_datetime(row["max time"], "Max Time", line_number),
            "max_value": self._parse_optional_float(row["max value"], "Max Value", line_number),
            "avg_value": self._parse_float(row["avg value"], "Avg Value", line_number),
            "quality": quality,
        }

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
            return float(value)
        except ValueError as exc:
            raise ValueError(
                f"SCADA CSV line {line_number} has invalid {field_name}: {value!r}"
            ) from exc

    @staticmethod
    def _parse_datetime(value: str, field_name: str, line_number: int) -> datetime | None:
        if value is None or value.strip() == "":
            return None
        raw = value.strip()
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
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%m/%d/%Y %I:%M:%S %p",
            "%m/%d/%Y %I:%M %p",
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
