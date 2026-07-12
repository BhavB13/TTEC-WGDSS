from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.demand_forecast import ForecastTrainingRow
from app.models.forecast import Forecast
from app.models.scada import ScadaGridSnapshot
from app.models.weather import Weather
from app.services.forecast_dataset_service import ForecastDatasetService


def _session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _ts(hour: int) -> datetime:
    return datetime(2026, 6, 30, hour)


def _seed_snapshots(session_factory, hours: range = range(0, 8)) -> None:
    with session_factory() as session:
        for hour in hours:
            demand = 800 + hour * 10
            session.add(
                ScadaGridSnapshot(
                    timestamp=_ts(hour),
                    current_demand_mw=demand,
                    temperature_c=27 + hour * 0.1,
                    spinning_reserve_mw=150,
                    available_capacity_mw=1200,
                    online_capacity_mw=950,
                    reserve_margin_mw=1200 - demand,
                    reserve_margin_percent=(1200 - demand) / demand * 100,
                    online_spare_mw=950 - demand,
                    quality_status="GOOD",
                    missing_fields="",
                    source="test",
                )
            )
        session.commit()


def _seed_weather_and_forecast(session_factory, hours: range = range(0, 8)) -> None:
    with session_factory() as session:
        for hour in hours:
            session.add(
                Weather(
                    timestamp=_ts(hour),
                    temperature_c=28 + hour * 0.2,
                    humidity_percent=70 + hour,
                    wind_speed_kph=12 + hour,
                    wind_direction_deg=90,
                    pressure_hpa=1012,
                    precipitation_mm=0.1,
                    rainfall_mm_hr=0.2 + hour * 0.1,
                    cloud_cover_percent=40 + hour,
                    weather_condition="Cloudy",
                    heat_index_c=29,
                    rain_severity="LIGHT",
                    provider_name="TestWeather",
                )
            )
            session.add(
                Forecast(
                    forecast_timestamp=_ts(hour),
                    temperature_c=29 + hour * 0.25,
                    humidity_percent=75,
                    rainfall_mm_hr=0.3 + hour * 0.1,
                    cloud_cover_percent=50 + hour,
                    wind_speed_kph=14,
                    wind_direction_deg=100,
                    precipitation_probability_percent=60,
                    precipitation_mm=0.4,
                    weather_condition="Forecast",
                    heat_index_c=30,
                    rain_severity="LIGHT",
                    confidence_score=0.8,
                    provider_name="TestForecast",
                    created_at=_ts(0) - timedelta(hours=1),
                )
            )
        session.commit()


def test_forecast_dataset_builds_rows_without_future_leakage(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_snapshots(session_factory)
    _seed_weather_and_forecast(session_factory)

    result = ForecastDatasetService(session_factory=session_factory).build_training_rows()

    assert result.rows_created == 15
    assert result.source_snapshots == 8
    with session_factory() as session:
        row = session.scalar(
            select(ForecastTrainingRow).where(
                ForecastTrainingRow.feature_timestamp == _ts(2),
                ForecastTrainingRow.horizon_hours == 1,
            )
        )

    assert row is not None
    assert row.target_timestamp == _ts(3)
    assert row.current_demand_mw == 820
    assert row.target_demand_mw == 830
    assert row.lag_1h_demand_mw == 810
    assert row.lag_2h_demand_mw == 800
    assert row.rolling_3h_demand_mw == 810
    assert row.hour_of_day == 2
    assert row.day_of_week == 1
    assert row.temperature_c == 28.4
    assert row.humidity_percent == 72
    assert row.forecast_temperature_c == 29.75
    assert row.forecast_humidity_percent == 75
    assert round(row.forecast_rainfall_mm_hr, 4) == 0.6
    assert row.forecast_cloud_cover_percent == 53
    assert row.forecast_wind_speed_kmh == 14
    assert row.forecast_precipitation_probability_percent == 60
    assert row.pressure_hpa == 1012
    assert row.spinning_reserve_mw == 150
    assert row.available_capacity_mw == 1200
    assert row.online_capacity_mw == 950
    assert row.reserve_margin_mw == 380
    assert row.online_spare_mw == 130
    assert row.source_quality_status == "GOOD"


def test_forecast_dataset_uses_requested_horizons_and_replaces_rows(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_snapshots(session_factory)
    _seed_weather_and_forecast(session_factory)
    service = ForecastDatasetService(session_factory=session_factory)

    first = service.build_training_rows(horizons_hours=(1,))
    second = service.build_training_rows(horizons_hours=(1,))

    assert first.rows_created == 7
    assert second.rows_created == 7
    with session_factory() as session:
        assert session.scalar(select(func.count(ForecastTrainingRow.id))) == 7


def test_forecast_dataset_marks_missing_weather_or_forecast_degraded(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_snapshots(session_factory, range(0, 3))
    _seed_weather_and_forecast(session_factory, range(0, 2))

    result = ForecastDatasetService(session_factory=session_factory).build_training_rows(
        horizons_hours=(1,)
    )

    assert result.rows_created == 2
    with session_factory() as session:
        rows = session.scalars(
            select(ForecastTrainingRow).order_by(ForecastTrainingRow.feature_timestamp)
        ).all()

    assert rows[0].source_quality_status == "GOOD"
    assert rows[1].source_quality_status == "WEATHER_DEGRADED"
    assert rows[1].humidity_percent == 71
    assert rows[1].forecast_temperature_c is None


def test_forecast_dataset_rejects_forecasts_created_after_feature_time(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_snapshots(session_factory, range(0, 3))
    _seed_weather_and_forecast(session_factory, range(0, 3))
    with session_factory() as session:
        session.add(
            Forecast(
                forecast_timestamp=_ts(2),
                temperature_c=99,
                humidity_percent=75,
                rainfall_mm_hr=0.3,
                cloud_cover_percent=50,
                wind_speed_kph=14,
                wind_direction_deg=100,
                precipitation_probability_percent=60,
                precipitation_mm=0.4,
                weather_condition="Future revision",
                heat_index_c=30,
                rain_severity="LIGHT",
                confidence_score=0.8,
                provider_name="TestForecast",
                created_at=_ts(2),
            )
        )
        session.commit()

    ForecastDatasetService(session_factory=session_factory).build_training_rows(
        horizons_hours=(1,)
    )

    with session_factory() as session:
        row = session.scalar(
            select(ForecastTrainingRow).where(
                ForecastTrainingRow.feature_timestamp == _ts(1),
                ForecastTrainingRow.horizon_hours == 1,
            )
        )

    assert row is not None
    assert row.forecast_temperature_c == 29.5


def test_forecast_dataset_marks_bad_target_snapshot_degraded(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_snapshots(session_factory, range(0, 3))
    _seed_weather_and_forecast(session_factory, range(0, 3))
    with session_factory() as session:
        target = session.scalar(
            select(ScadaGridSnapshot).where(ScadaGridSnapshot.timestamp == _ts(2))
        )
        assert target is not None
        target.quality_status = "BAD"
        session.commit()

    ForecastDatasetService(session_factory=session_factory).build_training_rows(
        horizons_hours=(1,)
    )

    with session_factory() as session:
        row = session.scalar(
            select(ForecastTrainingRow).where(
                ForecastTrainingRow.feature_timestamp == _ts(1),
                ForecastTrainingRow.horizon_hours == 1,
            )
        )

    assert row is not None
    assert row.source_quality_status == "SCADA_DEGRADED"


def test_forecast_dataset_builds_future_inference_from_latest_snapshot(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_snapshots(session_factory, range(0, 8))
    _seed_weather_and_forecast(session_factory, range(0, 10))

    rows = ForecastDatasetService(
        session_factory=session_factory
    ).build_inference_rows(horizons_hours=(1, 2), as_of=_ts(7))

    assert set(rows) == {1, 2}
    assert rows[1].feature_timestamp == _ts(7)
    assert rows[1].target_timestamp == _ts(8)
    assert rows[1].current_demand_mw == 870
    assert rows[1].target_demand_mw == 870
    assert rows[1].lag_1h_demand_mw == 860
    assert rows[1].forecast_temperature_c == 31
    assert rows[1].forecast_humidity_percent == 75
    assert rows[1].forecast_wind_speed_kmh == 14
    assert rows[1].forecast_precipitation_probability_percent == 60
    assert rows[1].source_quality_status == "GOOD"
    assert rows[2].target_timestamp == _ts(9)


def test_forecast_dataset_refuses_inference_from_bad_latest_scada(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_snapshots(session_factory, range(0, 3))
    with session_factory() as session:
        latest = session.scalar(
            select(ScadaGridSnapshot).order_by(ScadaGridSnapshot.timestamp.desc())
        )
        assert latest is not None
        latest.quality_status = "BAD"
        session.commit()

    rows = ForecastDatasetService(
        session_factory=session_factory
    ).build_inference_rows(horizons_hours=(1,))

    assert rows == {}
