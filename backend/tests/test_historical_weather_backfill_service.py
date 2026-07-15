from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.weather import Weather
from app.services.historical_weather_backfill_service import (
    HistoricalWeatherBackfillService,
    PROVIDER_NAME,
)


def _session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _HttpSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return _Response(self.payload)


def _payload():
    return {
        "hourly": {
            "time": ["2026-06-15T00:00", "2026-06-15T01:00"],
            "temperature_2m": [25.3, 24.8],
            "relative_humidity_2m": [85, 88],
            "rain": [0.0, 0.2],
            "cloud_cover": [94, 99],
            "wind_speed_10m": [11.6, 12.1],
            "wind_direction_10m": [80, 85],
            "surface_pressure": [1015.0, 1014.2],
        }
    }


def test_historical_weather_backfill_persists_external_driver_fields(tmp_path):
    session_factory = _session_factory(tmp_path)
    http = _HttpSession(_payload())
    service = HistoricalWeatherBackfillService(
        session_factory=session_factory,
        session=http,
        retry_attempts=1,
    )

    first = service.backfill(date(2026, 6, 15), date(2026, 6, 15))
    second = service.backfill(date(2026, 6, 15), date(2026, 6, 15))

    assert first.rows_stored == 2
    assert second.rows_stored == 2
    assert len(http.calls) == 2
    assert http.calls[0][1]["timezone"] == "America/Port_of_Spain"
    with session_factory() as session:
        assert session.scalar(select(func.count(Weather.id))) == 2
        row = session.scalar(
            select(Weather).where(Weather.timestamp == datetime(2026, 6, 15, 1))
        )
    assert row is not None
    assert row.provider_name == PROVIDER_NAME
    assert row.humidity_percent == 88
    assert row.rainfall_mm_hr == 0.2
    assert row.cloud_cover_percent == 99
    assert row.wind_speed_kph == 12.1
    assert row.wind_direction_deg == 85
    assert row.pressure_hpa == 1014.2
