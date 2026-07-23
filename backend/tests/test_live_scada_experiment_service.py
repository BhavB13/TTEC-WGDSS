from __future__ import annotations

import csv
import io
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from app.providers.excel_snapshot_scada_provider import TRINIDAD_TZ
from app.services.frozen_snapshot_model_service import FrozenSnapshotModelService
from app.services.live_scada_experiment_service import (
    LiveScadaExperimentService,
    LiveScadaSessionRepository,
)


class FakeWeather:
    async def get_current_weather(self, *_args, **_kwargs):
        return {"timestamp": "2026-07-23T12:00:00-04:00", "temperature_c": 32}

    async def get_forecast(self, *_args, **_kwargs):
        return [
            {
                "forecast_timestamp": (
                    datetime(2026, 7, 23, 12, tzinfo=TRINIDAD_TZ)
                    + timedelta(hours=hour)
                ).isoformat(),
                "temperature_c": 32 + hour,
                "humidity_percent": 70,
                "rainfall_mm_hr": 0,
                "cloud_cover_percent": 30,
                "wind_speed_kmh": 15,
                "provider_name": "Test provider",
            }
            for hour in range(8)
        ]


def _source(path: Path) -> Path:
    tags = [
        ("PTL132 GENERATION TOTALS", 1200),
        ("MHO132 TRINIDAD AVERAGE AMBIENT TEMP", 32),
        ("GSYS SYSTEM_CORRECTED_SPIN_TOTAL", 80),
        ("GSYS SYSTEM_ONLN_TOTAL", 1350),
    ]
    headers = [
        "Pen Index", "Name", "Start Time", "End Time", "Min Time",
        "Min Value", "Max Time", "Max Value", "Avg Value", "Quality",
    ]
    with ZipFile(path, "w") as archive:
        for index, (tag, value) in enumerate(tags):
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerow(
                [1, tag, "07/23/2026 10:00", "07/23/2026 11:30", "", value,
                 "", value, value, "Good"]
            )
            archive.writestr(f"{index}.csv", output.getvalue())
    return path


def test_session_is_isolated_and_weather_is_post_boundary(tmp_path: Path):
    source = _source(tmp_path / "source.zip")
    repository = LiveScadaSessionRepository(tmp_path / "sessions")
    service = LiveScadaExperimentService(
        source_path=source,
        weather_service=FakeWeather(),
        repository=repository,
        model_service=FrozenSnapshotModelService(tmp_path / "missing.joblib"),
    )
    session = asyncio.run(service.run())

    assert session.source.latest_valid_timestamp == datetime(
        2026, 7, 23, 11, 30, tzinfo=TRINIDAD_TZ
    )
    assert all(
        datetime.fromisoformat(item["forecast_timestamp"])
        > session.source.latest_valid_timestamp
        for item in session.weather.forecast
    )
    assert all(
        (
            item["feature_timestamp"]
            if isinstance(item["feature_timestamp"], datetime)
            else datetime.fromisoformat(item["feature_timestamp"])
        )
        <= session.source.latest_valid_timestamp
        for item in session.model_inputs
    )
    assert session.model.status == "NO_FROZEN_MODEL_ARTIFACT"
    assert session.model.snapshot_used_for_training is False
    assert session.model.preprocessing_refit is False
    assert len(session.reference_forecasts) == 3
    assert all(point.status == "UNAVAILABLE" for point in session.risk)
    assert repository.latest().session_id == session.session_id
    assert not (tmp_path / "wgdss.db").exists()
    assert source.is_file()
