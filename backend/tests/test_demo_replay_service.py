from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.demo_replay import DemoObservation, DemoReplayState
from app.models.demand_forecast import ScadaReplayForecastResult
from app.models.scada import ScadaGridSnapshot
from app.models.weather import Weather
from app.schemas.replay import ReplayControlRequest
from app.services.demo_replay_service import DemoReplayService


@pytest.fixture(scope="module")
def replay_service(tmp_path_factory):
    database = tmp_path_factory.mktemp("demo-replay") / "replay.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    clock = lambda: datetime(2026, 7, 15, 10, 42, tzinfo=ZoneInfo("America/Port_of_Spain"))
    return DemoReplayService(session_factory=session_factory, clock=clock), session_factory


def test_demo_seed_separates_year_archive_from_june_replay(replay_service):
    service, session_factory = replay_service

    assert service.ensure_seeded() == 8760
    status = service.get_status()

    assert status.dataset_start == datetime(2025, 1, 1)
    assert status.dataset_end == datetime(2025, 12, 31, 23)
    assert status.replay_start == datetime(2025, 6, 1)
    assert status.replay_end == datetime(2025, 6, 30, 23)
    assert status.total_replay_records == 720
    assert status.cursor_at == datetime(2025, 6, 15, 10)
    assert status.is_playing is True
    assert status.speed_multiplier == 1
    assert status.revealed_records == 347
    with session_factory() as session:
        assert session.scalar(select(func.count(DemoObservation.id))) == 8760


def test_replay_dashboard_exposes_history_forecast_and_no_future_actuals(replay_service):
    service, _ = replay_service
    service.control(ReplayControlRequest(action="reset"))

    context = service.get_dashboard_context()
    assert context is not None
    replay = context["replay"]

    assert replay.summary.historical_months == 11
    assert replay.summary.historical_record_count == 8040
    assert len(replay.operational_history) == 48
    assert len(replay.full_day_load_forecast) == 24
    assert replay.full_day_load_forecast[10].actual_demand_mw is not None
    assert all(
        point.actual_demand_mw is None
        for point in replay.full_day_load_forecast[11:]
    )
    assert len(context["forecast"]) == 24
    assert context["forecast"][0]["forecast_timestamp"] == "2025-06-15T11:00:00-04:00"
    assert all(item["source_count"] == 1 for item in context["forecast"][:6])
    assert all(
        item["source_names"] == ["Replay Historical Weather Baseline"]
        for item in context["forecast"][:6]
    )
    assert all(item["source_sync_status"] == "COMPLETE" for item in context["forecast"][:6])
    assert replay.summary.training_rows > 3000
    assert replay.summary.forecast_mae_mw <= replay.summary.baseline_mae_mw
    assert context["grid"]["source_provider"] == "SimulatedLiveScadaReplay"
    assert [
        row.horizon_hours for row in context["demand_forecast"].horizons
    ] == [1, 2, 6]
    assert context["model_status"].feature_profile == "replay_weather_features"


def test_replay_control_steps_configures_and_resets_cursor(replay_service):
    service, session_factory = replay_service
    service.control(
        ReplayControlRequest(action="configure", step_minutes=1440, speed_multiplier=86400)
    )
    stepped = service.control(ReplayControlRequest(action="step"))
    assert stepped.cursor_at == datetime(2025, 6, 16, 10)
    assert stepped.revealed_records == 371

    with session_factory() as session:
        state = session.get(DemoReplayState, 1)
        assert state is not None
        state.is_playing = True
        state.last_wallclock_at = (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=2)
        )
        session.commit()

    advanced = service.get_status()
    assert advanced.cursor_at >= datetime(2025, 6, 17, 10)
    reset = service.control(ReplayControlRequest(action="reset"))
    assert reset.cursor_at == datetime(2025, 6, 15, 10)
    assert reset.is_playing is True
    assert reset.speed_multiplier == 1


def test_june_scada_overlay_maps_completed_interval_without_future_leakage(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'scada-replay.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    clock = lambda: datetime(
        2026,
        7,
        15,
        10,
        42,
        tzinfo=ZoneInfo("America/Port_of_Spain"),
    )
    service = DemoReplayService(session_factory=session_factory, clock=clock)
    service.ensure_seeded()
    start = datetime(2026, 6, 1)
    with session_factory() as session:
        for offset in range(15 * 24):
            timestamp = start + timedelta(hours=offset)
            available_at = timestamp + timedelta(hours=1)
            demand = 900 + timestamp.day * 10 + timestamp.hour
            if timestamp == datetime(2026, 6, 15, 10):
                demand = 9999
            session.add(
                ScadaGridSnapshot(
                    timestamp=timestamp,
                    available_at=available_at,
                    current_demand_mw=demand,
                    temperature_c=29 + timestamp.hour * 0.05,
                    spinning_reserve_mw=200,
                    available_capacity_mw=1450,
                    online_capacity_mw=1300,
                    reserve_margin_mw=1450 - demand,
                    reserve_margin_percent=(1450 - demand) / demand * 100,
                    online_spare_mw=1300 - demand,
                    quality_status="USABLE_WITH_WARNING",
                    missing_fields="",
                    coverage_percent=100,
                    quality_notes="Conditionally accepted Other quality",
                    resampling_method="interval_overlap_hourly",
                    source="future-filename.csv",
                )
            )
            session.add(
                Weather(
                    timestamp=available_at,
                    temperature_c=28,
                    humidity_percent=78,
                    wind_speed_kph=14,
                    wind_direction_deg=85,
                    pressure_hpa=1013,
                    precipitation_mm=0.1,
                    rainfall_mm_hr=0.1,
                    cloud_cover_percent=60,
                    weather_condition="Partly cloudy",
                    heat_index_c=30,
                    rain_severity="LIGHT",
                    provider_name="Open-Meteo Historical Weather",
                    created_at=available_at,
                )
            )
        source_cursor = datetime(2026, 6, 15, 10)
        for horizon, demand in ((1, 1111.0), (2, 1122.0), (6, 1166.0)):
            session.add(
                ScadaReplayForecastResult(
                    source_cursor_at=source_cursor,
                    feature_timestamp=source_cursor,
                    forecast_timestamp=source_cursor + timedelta(hours=horizon),
                    horizon_hours=horizon,
                    forecast_demand_mw=demand,
                    forecast_uncertainty_mw=20.0 + horizon,
                    model_name="HistGradientBoostingRegressor",
                    model_version="demand-forecast-v2.0",
                    baseline_name="persistence",
                    baseline_forecast_mw=demand - 10,
                    quality_status="ML_ACTIVE_DEGRADED",
                    mae=12.5,
                    rmse=16.0,
                    mape=1.1,
                    residual_std=15.0,
                    baseline_mae=20.0,
                    ml_beats_baseline=True,
                    feature_profile="demand_weather_v2",
                    validation_status="PROTOTYPE",
                    training_span_hours=335,
                    train_row_count=250,
                    test_row_count=63,
                    candidate_metrics='{"active": {"model": "HistGradientBoostingRegressor"}}',
                    training_rows=313,
                    generated_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
                )
            )
        session.add(
            ScadaReplayForecastResult(
                source_cursor_at=source_cursor + timedelta(hours=1),
                feature_timestamp=source_cursor + timedelta(hours=1),
                forecast_timestamp=source_cursor + timedelta(hours=2),
                horizon_hours=1,
                forecast_demand_mw=9999,
                forecast_uncertainty_mw=1,
                model_name="future-model",
                model_version="future",
                baseline_name="future",
                baseline_forecast_mw=9999,
                quality_status="ML_ACTIVE",
                mae=1,
                rmse=1,
                mape=1,
                residual_std=1,
                baseline_mae=2,
                ml_beats_baseline=True,
                feature_profile="future",
                validation_status="VALIDATED",
                training_span_hours=9999,
                train_row_count=9999,
                test_row_count=1,
                candidate_metrics="{}",
                training_rows=10000,
                generated_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
            )
        )
        session.commit()

    context = service.get_dashboard_context()

    assert context is not None
    assert context["grid"]["current_demand_mw"] == 1059
    assert context["grid"]["source_provider"] == "HistoricalScadaSimulatedReplay"
    assert context["grid"]["quality_status"] == "UNCERTAIN"
    assert context["weather"]["temperature_c"] == 29.45
    assert context["weather"]["humidity_percent"] == 78
    assert all(
        point.actual_demand_mw is None
        for point in context["replay"].full_day_load_forecast[11:]
    )
    assert max(
        point.forecast_demand_mw
        for point in context["replay"].full_day_load_forecast[11:]
    ) < 2000
    chart_by_hour = {
        point.timestamp.hour: point
        for point in context["replay"].full_day_load_forecast
    }
    assert chart_by_hour[11].forecast_demand_mw == 1111
    assert chart_by_hour[12].forecast_demand_mw == 1122
    assert chart_by_hour[16].forecast_demand_mw == 1166
    assert context["risk_payload"]["forecast_demand_60m"] == 1111
    assert [
        item.horizon_hours for item in context["demand_forecast"].horizons
    ] == [1, 2, 6]
    assert context["model_status"].active_model == "HistGradientBoostingRegressor"
    assert context["model_status"].baseline_comparison.ml_beats_baseline is True
    assert context["scada_status"].latest_snapshot == datetime(2025, 6, 15, 10)
