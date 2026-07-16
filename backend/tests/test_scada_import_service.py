from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
    assert measurements[0].aggregation == "interval_summary"
    assert measurements[0].canonical_variable == "system_generation_total_mw"
    assert measurements[0].record_hash is not None
    assert measurements[0].engineering_unit is None
    assert measurements[0].source_provider == "csv_trend_export"


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


def test_scada_import_parses_two_digit_year_and_trims_tag_whitespace(tmp_path):
    session_factory = _session_factory(tmp_path)
    csv_path = tmp_path / "future_archive_member.csv"
    row = list(KNOWN_SCADA_ROWS[0])
    row[1] = "  PTL132 GENERATION TOTALS  "
    row[2] = " 06/01/26 12:00 AM "
    row[3] = "06/01/26 01:18 AM"
    row[4] = "06/01/26 12:10 AM"
    row[6] = "06/01/26 01:05 AM"
    _write_csv(csv_path, rows=[row])

    result = ScadaImportService(session_factory=session_factory).import_csv(csv_path)

    assert result.row_count == 1
    with session_factory() as session:
        measurement = session.scalar(select(ScadaRawMeasurement))
    assert measurement is not None
    assert measurement.tag_name == "PTL132 GENERATION TOTALS"
    assert measurement.start_time == datetime(2026, 6, 1, 0, 0)
    assert measurement.end_time == datetime(2026, 6, 1, 1, 18)


def test_scada_import_reports_quality_extrema_and_reporting_window_anomalies(tmp_path):
    session_factory = _session_factory(tmp_path)
    csv_path = tmp_path / "june_temperature.csv"
    row = list(KNOWN_SCADA_ROWS[1])
    row[2] = "2026-06-30 23:57:00"
    row[3] = "2026-07-01 00:00:00"
    row[4] = "2026-07-01 00:58:00"
    row[6] = "2026-07-01 00:26:00"
    row[9] = "Other"
    _write_csv(csv_path, rows=[row])

    result = ScadaImportService(
        session_factory=session_factory,
        expected_reporting_end=datetime(
            2026,
            6,
            30,
            23,
            59,
            59,
            tzinfo=ZoneInfo("America/Port_of_Spain"),
        ),
    ).import_csv(csv_path)

    assert result.quality_counts == {"unknown": 1}
    assert result.anomaly_counts["min_time_outside_interval"] == 1
    assert result.anomaly_counts["max_time_outside_interval"] == 1
    assert result.anomaly_counts["outside_expected_reporting_window"] == 1
    with session_factory() as session:
        measurement = session.scalar(select(ScadaRawMeasurement))
        import_run = session.scalar(select(ScadaImportRun))
    assert measurement is not None
    assert import_run is not None
    assert measurement.quality == "Other"
    assert measurement.normalized_quality == "unknown"
    assert "unconfirmed_quality_mapping" in json.loads(measurement.anomaly_flags)
    report = json.loads(import_run.quality_report)
    assert report["aggregation"] == "interval_summary"
    assert report["anomaly_counts"]["outside_expected_reporting_window"] == 1


def test_scada_import_deduplicates_same_interval_across_different_files(tmp_path):
    session_factory = _session_factory(tmp_path)
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    _write_csv(first_path, rows=[KNOWN_SCADA_ROWS[0]])
    _write_csv(
        second_path,
        rows=[KNOWN_SCADA_ROWS[0]],
        headers=[
            "PEN_INDEX",
            "NAME",
            "START_TIME",
            "END_TIME",
            "MIN_TIME",
            "MIN_VALUE",
            "MAX_TIME",
            "MAX_VALUE",
            "AVG_VALUE",
            "QUALITY",
        ],
    )
    service = ScadaImportService(session_factory=session_factory)

    first = service.import_csv(first_path)
    second = service.import_csv(second_path)

    assert first.row_count == 1
    assert second.imported is True
    assert second.row_count == 0
    assert second.duplicate_records_skipped == 1
    with session_factory() as session:
        assert session.scalar(select(func.count(ScadaRawMeasurement.id))) == 1
        assert session.scalar(select(func.count(ScadaImportRun.id))) == 2
