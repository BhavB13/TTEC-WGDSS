from __future__ import annotations

import logging
import re
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.calibration import (
    CalibrationImportRun,
    CalibrationScenarioProfile,
    ScadaTemperatureSample,
)

logger = logging.getLogger(__name__)

TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")
XML_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

SCADA_WORKBOOK_SCENARIO_MAP = {
    "20260512 sunny day.xlsx": "hot",
    "20260602 typical day.xlsx": "typical",
    "20260623 rain day.xlsx": "rainy",
}

LOAD_SHEET_SCENARIO_MAP = {
    "hot day 20260512": "hot",
    "typical day 20260602": "typical",
    "rainy day 20260623": "rainy",
}

SCENARIO_METADATA = {
    "hot": {"label": "Hot Day", "regime": "HOT"},
    "typical": {"label": "Typical Day", "regime": "TYPICAL"},
    "rainy": {"label": "Rainy Day", "regime": "RAINY"},
}


class CalibrationImportService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def import_archive(self, archive_path: str | Path, replace_existing: bool = True) -> dict[str, int]:
        archive = Path(archive_path)
        if not archive.exists():
            raise FileNotFoundError(f"Calibration archive not found: {archive}")

        initialize_database()

        source_hash = self._file_hash(archive)
        counts = {
            "workbooks": 0,
            "temperature_samples": 0,
            "scenario_profiles": 0,
            "import_runs": 0,
            "skipped_duplicate": 0,
        }

        with ZipFile(archive) as outer_zip, self.session_factory() as session:
            existing = session.scalar(
                select(CalibrationImportRun).where(
                    CalibrationImportRun.source_hash == source_hash
                )
            )
            if existing is not None:
                counts["skipped_duplicate"] = 1
                return counts
            if replace_existing:
                self._delete_existing_archive_records(session, str(archive.resolve()))

            for nested_name in outer_zip.namelist():
                if not nested_name.lower().endswith(".xlsx"):
                    continue

                workbook_bytes = outer_zip.read(nested_name)
                reader = _SimpleXlsxReader(workbook_bytes)
                workbook_name = Path(nested_name).name
                counts["workbooks"] += 1

                if workbook_name.lower() in SCADA_WORKBOOK_SCENARIO_MAP:
                    scenario_key = SCADA_WORKBOOK_SCENARIO_MAP[workbook_name.lower()]
                    counts["temperature_samples"] += self._import_scada_workbook(
                        session=session,
                        reader=reader,
                        source_archive=str(archive.resolve()),
                        source_workbook=workbook_name,
                        scenario_key=scenario_key,
                    )
                elif workbook_name.lower() == "load forecasting data.xlsx":
                    counts["scenario_profiles"] += self._import_scenario_workbook(
                        session=session,
                        reader=reader,
                        source_archive=str(archive.resolve()),
                        source_workbook=workbook_name,
                    )
                else:
                    logger.info("Skipping unrecognized workbook %s", workbook_name)

            summary = (
                f"Imported {counts['workbooks']} workbook(s), "
                f"{counts['temperature_samples']} SCADA sample(s), "
                f"{counts['scenario_profiles']} scenario profile row(s)"
            )
            session.add(
                CalibrationImportRun(
                    source_archive=str(archive.resolve()),
                    source_filename=archive.name,
                    source_hash=source_hash,
                    import_status="IMPORTED",
                    summary=summary,
                )
            )
            counts["import_runs"] += 1
            session.commit()

        return counts

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def import_archive_if_present(self, archive_path: str | Path) -> dict[str, int] | None:
        archive = Path(archive_path)
        if not archive.exists():
            logger.warning("Calibration archive not found at %s", archive)
            return None
        return self.import_archive(archive, replace_existing=True)

    def _delete_existing_archive_records(self, session: Session, source_archive: str) -> None:
        session.execute(
            delete(CalibrationImportRun).where(CalibrationImportRun.source_archive == source_archive)
        )
        session.execute(
            delete(ScadaTemperatureSample).where(ScadaTemperatureSample.source_archive == source_archive)
        )
        session.execute(
            delete(CalibrationScenarioProfile).where(
                CalibrationScenarioProfile.source_archive == source_archive
            )
        )
        session.flush()

    def _import_scada_workbook(
        self,
        session: Session,
        reader: "_SimpleXlsxReader",
        source_archive: str,
        source_workbook: str,
        scenario_key: str,
    ) -> int:
        sheet_name = reader.sheet_names[0]
        rows = reader.sheet_rows(sheet_name)
        if not rows:
            return 0

        header_row = rows[0]
        header_map = _build_header_map(header_row)
        imported = 0
        measurement_name = "MHO132 TRINIDAD AVERAGE AMBIENT TEMP"

        for row in rows[1:]:
            if not _row_has_values(row):
                continue

            pen_index = _as_int(_cell_value(row, header_map, "pen index"), default=1)
            quality_status = str(_cell_value(row, header_map, "quality") or "Unknown").strip() or "Unknown"
            sample_timestamp = _excel_serial_to_datetime(_as_float(_cell_value(row, header_map, "start time")))
            start_time = sample_timestamp
            end_time = _excel_serial_to_datetime(_as_float(_cell_value(row, header_map, "end time")))
            min_time = _excel_serial_to_datetime(_as_float(_cell_value(row, header_map, "min time")))
            max_time = _excel_serial_to_datetime(_as_float(_cell_value(row, header_map, "max time")))
            min_value_c = _as_float(_cell_value(row, header_map, "min value"))
            max_value_c = _as_float(_cell_value(row, header_map, "max value"))
            avg_value_c = _as_float(_cell_value(row, header_map, "avg value"))

            if sample_timestamp is None or start_time is None or end_time is None:
                continue

            session.add(
                ScadaTemperatureSample(
                    scenario_key=scenario_key,
                    source_archive=source_archive,
                    source_workbook=source_workbook,
                    source_sheet=sheet_name,
                    measurement_name=measurement_name,
                    pen_index=pen_index,
                    sample_timestamp=sample_timestamp,
                    start_time=start_time,
                    end_time=end_time,
                    min_time=min_time or sample_timestamp,
                    max_time=max_time or sample_timestamp,
                    min_value_c=min_value_c,
                    max_value_c=max_value_c,
                    avg_value_c=avg_value_c,
                    quality_status=quality_status,
                )
            )
            imported += 1

        session.flush()
        logger.info(
            "Imported %s SCADA temperature samples for %s from %s",
            imported,
            scenario_key,
            source_workbook,
        )
        return imported

    def _import_scenario_workbook(
        self,
        session: Session,
        reader: "_SimpleXlsxReader",
        source_archive: str,
        source_workbook: str,
    ) -> int:
        imported = 0

        for sheet_name in reader.sheet_names:
            scenario_key = self._scenario_key_from_sheet(sheet_name)
            if scenario_key is None:
                logger.info("Skipping unrecognized scenario sheet %s", sheet_name)
                continue

            rows = reader.sheet_rows(sheet_name)
            if not rows:
                continue

            header_row_index = self._find_header_row_index(rows)
            if header_row_index is None:
                logger.warning("Could not locate header row in %s", sheet_name)
                continue

            header_map = _build_header_map(rows[header_row_index])
            metadata = SCENARIO_METADATA[scenario_key]

            for row in rows[header_row_index + 1 :]:
                if not _row_has_values(row):
                    continue

                hour_of_day = _as_int(_cell_value(row, header_map, "hour"), default=0)
                demand_mw = _as_float(_cell_value(row, header_map, "demand mw"))
                spin_mw = _as_float(_cell_value(row, header_map, "spin mw"))
                temperature_c = _maybe_float(_cell_value(row, header_map, "temp"))

                if hour_of_day <= 0:
                    continue

                session.add(
                    CalibrationScenarioProfile(
                        scenario_key=scenario_key,
                        scenario_label=metadata["label"],
                        operating_regime=metadata["regime"],
                        source_archive=source_archive,
                        source_workbook=source_workbook,
                        source_sheet=sheet_name,
                        hour_of_day=hour_of_day,
                        demand_mw=demand_mw,
                        spin_mw=spin_mw,
                        temperature_c=temperature_c,
                        quality_status="Calibrated",
                    )
                )
                imported += 1

        session.flush()
        logger.info("Imported %s scenario profile rows from %s", imported, source_workbook)
        return imported

    @staticmethod
    def _scenario_key_from_sheet(sheet_name: str) -> str | None:
        normalized = _normalize_text(sheet_name)
        for key in LOAD_SHEET_SCENARIO_MAP.values():
            if key in normalized:
                return key
        if "hot" in normalized:
            return "hot"
        if "typical" in normalized:
            return "typical"
        if "rain" in normalized:
            return "rainy"
        return None

    @staticmethod
    def _find_header_row_index(rows: list[list[Any]]) -> int | None:
        for index, row in enumerate(rows[:4]):
            labels = {_normalize_text(str(cell or "")) for cell in row}
            if "hour" in labels and "demandmw" in labels:
                return index
        return None


class _SimpleXlsxReader:
    def __init__(self, workbook_bytes: bytes) -> None:
        self._zip = ZipFile(BytesIO(workbook_bytes))
        self._shared_strings = self._load_shared_strings()
        self._sheet_targets = self._load_sheet_targets()
        self.sheet_names = list(self._sheet_targets.keys())

    def sheet_rows(self, sheet_name: str) -> list[list[Any]]:
        target = self._sheet_targets[sheet_name]
        root = ET.fromstring(self._zip.read(target))
        rows: list[list[Any]] = []
        for row in root.findall(".//a:sheetData/a:row", XML_NS):
            values: dict[int, Any] = {}
            for cell in row.findall("a:c", XML_NS):
                ref = cell.attrib.get("r", "")
                column_index = _column_to_index(ref)
                values[column_index] = self._cell_value(cell)
            if values:
                max_index = max(values)
                rows.append([values.get(index) for index in range(1, max_index + 1)])
        return rows

    def _load_shared_strings(self) -> list[str]:
        if "xl/sharedStrings.xml" not in self._zip.namelist():
            return []
        root = ET.fromstring(self._zip.read("xl/sharedStrings.xml"))
        shared: list[str] = []
        for item in root.findall("a:si", XML_NS):
            shared.append("".join(text.text or "" for text in item.findall(".//a:t", XML_NS)))
        return shared

    def _load_sheet_targets(self) -> dict[str, str]:
        workbook = ET.fromstring(self._zip.read("xl/workbook.xml"))
        rels = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {
            rel.attrib["Id"]: rel.attrib["Target"].lstrip("/")
            for rel in rels.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
        }

        targets: dict[str, str] = {}
        for sheet in workbook.findall("a:sheets/a:sheet", XML_NS):
            sheet_name = sheet.attrib["name"]
            rel_id = sheet.attrib[REL_NS]
            target = rel_targets[rel_id]
            targets[sheet_name] = target if target.startswith("xl/") else f"xl/{target}"
        return targets

    def _cell_value(self, cell: ET.Element) -> Any:
        cell_type = cell.attrib.get("t")
        value_node = cell.find("a:v", XML_NS)
        if value_node is None:
            inline_text = cell.find(".//a:t", XML_NS)
            return inline_text.text if inline_text is not None else None
        raw_value = value_node.text
        if raw_value is None:
            return None
        if cell_type == "s":
            index = int(raw_value)
            return self._shared_strings[index] if index < len(self._shared_strings) else None
        if cell_type == "inlineStr":
            return raw_value
        if cell_type == "b":
            return raw_value == "1"
        return raw_value


def _build_header_map(header_row: list[Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, raw_value in enumerate(header_row):
        normalized = _normalize_text(str(raw_value or ""))
        if normalized:
            mapping[normalized] = index
    return mapping


def _cell_value(row: list[Any], header_map: dict[str, int], key: str) -> Any:
    index = header_map.get(_normalize_text(key))
    if index is None or index >= len(row):
        return None
    return row[index]


def _row_has_values(row: list[Any]) -> bool:
    return any(cell not in (None, "") for cell in row)


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _column_to_index(cell_ref: str) -> int:
    letters = "".join(character for character in cell_ref if character.isalpha())
    index = 0
    for character in letters:
        index = index * 26 + (ord(character.upper()) - 64)
    return index


def _excel_serial_to_datetime(value: float | None) -> datetime | None:
    if value is None:
        return None
    try:
        serial = float(value)
    except (TypeError, ValueError):
        return None

    if serial <= 0:
        return None

    base = datetime(1899, 12, 30)
    result = base + timedelta(days=serial)
    return result.replace(tzinfo=TRINIDAD_TZ)


def _maybe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float = 0.0) -> float:
    maybe = _maybe_float(value)
    return default if maybe is None else maybe


def _as_int(value: Any, default: int = 0) -> int:
    maybe = _maybe_float(value)
    return default if maybe is None else int(round(maybe))
