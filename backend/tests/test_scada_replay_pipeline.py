from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.forecast import Forecast
from app.models.scada import ScadaGridSnapshot
from app.models.weather import Weather
import pytest

from scripts.run_scada_replay_pipeline import format_summary, run_pipeline


SCADA_TAGS = (
    ("1", "PTL132 GENERATION TOTALS"),
    ("2", "MHO132 AVERAGE AMBIENT TEMPERATURE"),
    ("3", "GSYS SYSTEM_CORRECTED_SPIN_TOTAL"),
    ("4", "GSYS SYSTEM_AVAIL_TOTAL"),
    ("5", "GSYS SYSTEM_ONLN_TOTAL"),
)


def _session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _ts(hour: int) -> datetime:
    return datetime(2026, 6, 30, hour)


def _value_for_tag(tag_name: str, hour: int) -> float:
    if tag_name == "PTL132 GENERATION TOTALS":
        return 800 + hour * 10
    if tag_name == "MHO132 AVERAGE AMBIENT TEMPERATURE":
        return 27 + hour * 0.2
    if tag_name == "GSYS SYSTEM_CORRECTED_SPIN_TOTAL":
        return 150 - hour
    if tag_name == "GSYS SYSTEM_AVAIL_TOTAL":
        return 1200
    if tag_name == "GSYS SYSTEM_ONLN_TOTAL":
        return 980
    raise ValueError(f"Unexpected tag {tag_name}")


def _write_scada_csv(
    path: Path,
    missing_online_hour: int | None = None,
    excluded_tag: str | None = None,
    start_at: datetime | None = None,
    hour_count: int = 9,
) -> None:
    rows: list[list[str]] = []
    start = start_at or _ts(0)
    for hour in range(hour_count):
        for pen_index, tag_name in reversed(SCADA_TAGS):
            if tag_name == excluded_tag:
                continue
            if tag_name == "GSYS SYSTEM_ONLN_TOTAL" and hour == missing_online_hour:
                continue
            timestamp = start + timedelta(hours=hour)
            value = _value_for_tag(tag_name, hour)
            rows.append(
                [
                    pen_index,
                    tag_name,
                    timestamp.isoformat(sep=" "),
                    (timestamp + timedelta(hours=1)).isoformat(sep=" "),
                    timestamp.isoformat(sep=" "),
                    str(value),
                    timestamp.isoformat(sep=" "),
                    str(value),
                    str(value),
                    "Good",
                ]
            )

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
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
        writer.writerows(reversed(rows))


def _seed_weather_and_forecast(session_factory) -> None:
    with session_factory() as session:
        for hour in range(9):
            timestamp = _ts(hour)
            session.add(
                Weather(
                    timestamp=timestamp,
                    temperature_c=28 + hour * 0.2,
                    humidity_percent=70 + hour,
                    wind_speed_kph=12 + hour,
                    wind_direction_deg=95,
                    pressure_hpa=1012,
                    precipitation_mm=0.1,
                    rainfall_mm_hr=0.1 + hour * 0.05,
                    cloud_cover_percent=40 + hour,
                    weather_condition="Cloudy",
                    heat_index_c=30,
                    rain_severity="LIGHT",
                    provider_name="ReplayTestWeather",
                )
            )
            session.add(
                Forecast(
                    forecast_timestamp=timestamp,
                    temperature_c=29 + hour * 0.2,
                    humidity_percent=75,
                    rainfall_mm_hr=0.2 + hour * 0.05,
                    cloud_cover_percent=45 + hour,
                    wind_speed_kph=15,
                    wind_direction_deg=100,
                    precipitation_probability_percent=60,
                    precipitation_mm=0.2,
                    weather_condition="Forecast",
                    heat_index_c=31,
                    rain_severity="LIGHT",
                    confidence_score=0.85,
                    provider_name="ReplayTestForecast",
                )
            )
        session.commit()


def test_full_scada_replay_pipeline_handles_duplicates_and_reports_quality(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_weather_and_forecast(session_factory)
    csv_path = tmp_path / "scada_replay.csv"
    _write_scada_csv(csv_path, missing_online_hour=4)

    result = run_pipeline([csv_path, csv_path], session_factory=session_factory)

    assert result.files_imported == 1
    assert result.duplicates_skipped == 1
    assert result.raw_rows_stored == 44
    assert result.snapshot_result.snapshots_created == 9
    assert result.snapshot_result.degraded_snapshots == 1
    assert result.dataset_result.rows_created == 18
    assert result.dataset_result.skipped_rows == 9
    assert len(result.training_result.results) == 3

    report = result.validation_report
    assert report.import_status.import_runs == 1
    assert report.import_status.raw_measurements == 44
    assert report.snapshot_quality.degraded_snapshots == 1
    assert report.snapshot_quality.missing_fields == {"online_capacity_mw": 1}
    assert report.training_rows.by_horizon == {1: 8, 2: 7, 6: 3}
    assert [item.horizon_hours for item in report.model_metrics] == [1, 2, 6]
    assert report.risk_readiness.ready is True

    with session_factory() as session:
        degraded = session.scalar(
            select(ScadaGridSnapshot).where(
                ScadaGridSnapshot.quality_status == "DEGRADED"
            )
        )
    assert degraded is not None
    assert degraded.timestamp == _ts(4)

    summary = format_summary(result)
    assert "files imported: 1" in summary
    assert "preflight aligned usable hours: 8" in summary
    assert "duplicates skipped: 1" in summary
    assert "model horizons evaluated: 3" in summary
    assert "1h ML beats baseline: false" in summary


def test_scada_replay_pipeline_rejects_missing_required_tag_before_import(tmp_path):
    session_factory = _session_factory(tmp_path)
    csv_path = tmp_path / "incomplete_scada_replay.csv"
    _write_scada_csv(csv_path, excluded_tag="GSYS SYSTEM_ONLN_TOTAL")

    with pytest.raises(ValueError, match="missing required SCADA tag"):
        run_pipeline([csv_path], session_factory=session_factory)

    with session_factory() as session:
        assert session.scalar(select(ScadaGridSnapshot)) is None


def test_scada_replay_pipeline_accepts_filename_agnostic_zip_archive(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_weather_and_forecast(session_factory)
    csv_path = tmp_path / "future_export_unknown_name.csv"
    archive_path = tmp_path / "historian_export_2027.zip"
    _write_scada_csv(csv_path)
    with ZipFile(archive_path, "w") as archive:
        archive.write(csv_path, arcname="nested/arbitrary-name.csv")

    result = run_pipeline([archive_path], session_factory=session_factory)

    assert result.preflight_report.ready is True
    assert result.preflight_report.files_checked == 1
    assert result.preflight_report.aligned_hour_count == 9
    assert result.files_imported == 1
    assert result.snapshot_result.snapshots_created == 9
    assert result.dataset_result.rows_created == 18
    assert [item.horizon_hours for item in result.training_result.results] == [1, 2, 6]


def test_future_archive_pipeline_crosses_year_boundary_without_filename_logic(
    tmp_path,
):
    session_factory = _session_factory(tmp_path)
    csv_path = tmp_path / "opaque_member.csv"
    archive_path = tmp_path / "twelve_month_historian_bundle.zip"
    start = datetime(2031, 12, 31, 20)
    _write_scada_csv(csv_path, start_at=start, hour_count=9)
    with ZipFile(archive_path, "w") as archive:
        archive.write(csv_path, arcname="year-two/telemetry-part-027.csv")

    result = run_pipeline([archive_path], session_factory=session_factory)

    assert result.preflight_report.ready is True
    assert result.snapshot_result.snapshots_created == 9
    with session_factory() as session:
        timestamps = list(
            session.scalars(
                select(ScadaGridSnapshot.timestamp).order_by(
                    ScadaGridSnapshot.timestamp
                )
            )
        )
    assert timestamps[0] == start
    assert timestamps[-1] == datetime(2032, 1, 1, 4)
