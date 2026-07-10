from __future__ import annotations

import csv
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.scada import ScadaImportRun, ScadaRawMeasurement
from app.services.scada_import_service import ScadaImportService


KNOWN_SCADA_ROWS = [
    [
        "1",
        "PTL132 GENERATION TOTALS",
        "2026-06-30 08:00:00",
        "2026-06-30 09:00:00",
        "2026-06-30 08:15:00",
        "840",
        "2026-06-30 08:45:00",
        "860",
        "850",
        "Good",
    ],
    [
        "2",
        "MHO132 AVERAGE AMBIENT TEMPERATURE",
        "2026-06-30 08:00:00",
        "2026-06-30 09:00:00",
        "2026-06-30 08:05:00",
        "27.1",
        "2026-06-30 08:40:00",
        "28.3",
        "27.8",
        "Good",
    ],
    [
        "3",
        "GSYS SYSTEM_CORRECTED_SPIN_TOTAL",
        "2026-06-30 08:00:00",
        "2026-06-30 09:00:00",
        "2026-06-30 08:00:00",
        "140",
        "2026-06-30 08:55:00",
        "155",
        "148",
        "Good",
    ],
    [
        "4",
        "GSYS SYSTEM_AVAIL_TOTAL",
        "2026-06-30 08:00:00",
        "2026-06-30 09:00:00",
        "2026-06-30 08:10:00",
        "1180",
        "2026-06-30 08:20:00",
        "1200",
        "1190",
        "Good",
    ],
    [
        "5",
        "GSYS SYSTEM_ONLN_TOTAL",
        "2026-06-30 08:00:00",
        "2026-06-30 09:00:00",
        "2026-06-30 08:10:00",
        "930",
        "2026-06-30 08:20:00",
        "950",
        "940",
        "Inactive",
    ],
]


def _session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _write_csv(
    path: Path,
    rows: list[list[str]] | None = None,
    headers: list[str] | None = None,
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            headers
            or [
                "Pen Index",
                "Name",
                "Start Time",
                "End Time",
                "Min Time",
                "Min Value",
                "Max Time",
                "Max Value",
                "Avg Value",
                "Quality",
            ]
        )
        writer.writerows(rows or KNOWN_SCADA_ROWS)


def test_scada_import_preserves_known_tags_and_avg_values(tmp_path):
    session_factory = _session_factory(tmp_path)
    csv_path = tmp_path / "scada.csv"
    _write_csv(csv_path)

    result = ScadaImportService(session_factory=session_factory).import_csv(csv_path)

    assert result.imported is True
    assert result.row_count == 5
    assert result.skipped_duplicate is False

    with session_factory() as session:
        assert session.scalar(select(func.count(ScadaImportRun.id))) == 1
        assert session.scalar(select(func.count(ScadaRawMeasurement.id))) == 5
        measurements = session.scalars(
            select(ScadaRawMeasurement).order_by(ScadaRawMeasurement.pen_index)
        ).all()

    assert [measurement.tag_name for measurement in measurements] == [
        "PTL132 GENERATION TOTALS",
        "MHO132 AVERAGE AMBIENT TEMPERATURE",
        "GSYS SYSTEM_CORRECTED_SPIN_TOTAL",
        "GSYS SYSTEM_AVAIL_TOTAL",
        "GSYS SYSTEM_ONLN_TOTAL",
    ]
    assert [measurement.avg_value for measurement in measurements] == [
        850,
        27.8,
        148,
        1190,
        940,
    ]
    assert measurements[-1].quality == "Inactive"
    assert measurements[0].source_filename == "scada.csv"
    assert measurements[0].start_time.year == 2026


def test_scada_import_skips_duplicate_by_source_hash(tmp_path):
    session_factory = _session_factory(tmp_path)
    csv_path = tmp_path / "scada.csv"
    _write_csv(csv_path)
    service = ScadaImportService(session_factory=session_factory)

    first = service.import_csv(csv_path)
    second = service.import_csv(csv_path)

    assert first.imported is True
    assert second.imported is False
    assert second.skipped_duplicate is True
    assert second.import_run_id == first.import_run_id

    with session_factory() as session:
        assert session.scalar(select(func.count(ScadaImportRun.id))) == 1
        assert session.scalar(select(func.count(ScadaRawMeasurement.id))) == 5


def test_scada_import_normalizes_headers_case_insensitively(tmp_path):
    session_factory = _session_factory(tmp_path)
    csv_path = tmp_path / "scada_lower_headers.csv"
    _write_csv(
        csv_path,
        headers=[
            "pen index",
            "NAME",
            "start_time",
            "End Time",
            "min time",
            "MIN VALUE",
            "max time",
            "Max Value",
            "avg value",
            "QUALITY",
        ],
    )

    result = ScadaImportService(session_factory=session_factory).import_csv(csv_path)

    assert result.row_count == 5
    with session_factory() as session:
        demand = session.scalar(
            select(ScadaRawMeasurement).where(
                ScadaRawMeasurement.tag_name == "PTL132 GENERATION TOTALS"
            )
        )
    assert demand is not None
    assert demand.avg_value == 850


def test_scada_import_rejects_missing_required_headers(tmp_path):
    session_factory = _session_factory(tmp_path)
    csv_path = tmp_path / "missing_quality.csv"
    _write_csv(
        csv_path,
        headers=[
            "Pen Index",
            "Name",
            "Start Time",
            "End Time",
            "Min Time",
            "Min Value",
            "Max Time",
            "Max Value",
            "Avg Value",
        ],
    )

    with pytest.raises(ValueError, match="missing required header"):
        ScadaImportService(session_factory=session_factory).import_csv(csv_path)

    with session_factory() as session:
        assert session.scalar(select(func.count(ScadaImportRun.id))) == 0
        assert session.scalar(select(func.count(ScadaRawMeasurement.id))) == 0


def test_scada_import_parses_excel_serial_timestamps(tmp_path):
    session_factory = _session_factory(tmp_path)
    csv_path = tmp_path / "excel_serial.csv"
    _write_csv(
        csv_path,
        rows=[
            [
                "1",
                "PTL132 GENERATION TOTALS",
                "46203.3333333333",
                "46203.375",
                "46203.3333333333",
                "840",
                "46203.375",
                "860",
                "850",
                "Good",
            ]
        ],
    )

    result = ScadaImportService(session_factory=session_factory).import_csv(csv_path)

    assert result.row_count == 1
    with session_factory() as session:
        measurement = session.scalar(select(ScadaRawMeasurement))
    assert measurement is not None
    assert measurement.start_time.year == 2026
    assert measurement.avg_value == 850
