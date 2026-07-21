from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.demo_replay import DemoObservation, DemoReplayState
from app.models.demand_forecast import ScadaReplayForecastResult
from app.models.scada import ScadaGridSnapshot
from app.models.weather import Weather
from app.providers.open_meteo_replay_provider import ArchivedForecastResult
from app.schemas.replay import ReplayControlRequest
from app.services.demo_replay_service import DemoReplayService


class UnavailableReplayWeatherProvider:
    def get_forecast_sources(self, **_kwargs):
        raise RuntimeError("archived forecast unavailable in fallback test")


class ThreeModelReplayWeatherProvider:
    def get_forecast_sources(self, source_cursor, hours=24, **_kwargs):
        names = (
            "Open-Meteo ECMWF IFS",
            "Open-Meteo NOAA GFS",
            "Open-Meteo DWD ICON",
        )
        sources = []
        for source_index, name in enumerate(names):
            sources.append(
                [
                    {
                        "forecast_timestamp": source_cursor + timedelta(hours=horizon),
                        "temperature_c": 32.0 + source_index * 0.3,
                        "humidity_percent": 78.0 - source_index,
                        "rainfall_mm_hr": 0.2 + source_index * 0.05,
                        "cloud_cover_percent": 55.0 + source_index,
                        "wind_speed_kmh": 18.0 + source_index,
                        "pressure_hpa": 1011.0,
                        "weather_condition": "Partly cloudy",
                        "precipitation_probability_percent": 55.0,
                        "provider_name": name,
                    }
                    for horizon in range(1, hours + 1)
                ]
            )
        return ArchivedForecastResult(
            source_payloads=sources,
            run_initialized_at=datetime(2026, 6, 15, 0, tzinfo=timezone.utc),
            assumed_available_at=datetime(2026, 6, 15, 6, tzinfo=timezone.utc),
            expected_source_count=3,
        )


class ThreeSourceLiveWeatherService:
    async def get_forecast(self, *_args, **_kwargs):
        source_names = [
            "Open-Meteo Best Match",
            "MET Norway",
            "Open-Meteo NOAA GFS",
        ]
        start = datetime(
            2026,
            7,
            15,
            11,
            tzinfo=ZoneInfo("America/Port_of_Spain"),
        )
        return [
            {
                "forecast_timestamp": (start + timedelta(hours=index)).isoformat(),
                "temperature_c": 30.0 + index * 0.1,
                "humidity_percent": 76.0,
                "rainfall_mm_hr": 0.4,
                "cloud_cover_percent": 58.0,
                "wind_speed_kmh": 18.0,
                "pressure_hpa": 1011.0,
                "weather_condition": "Partly cloudy",
                "heat_index_c": 32.0,
                "precipitation_probability_percent": 48.0,
                "confidence_score": 0.86,
                "rain_severity": "LIGHT",
                "provider_name": "Consensus (Open-Meteo + MET Norway + GFS)",
                "source_count": 3,
                "source_names": source_names,
                "source_sync_status": "COMPLETE",
                "field_source_counts": {
                    "temperature_c": 3,
                    "humidity_percent": 3,
                    "rainfall_mm_hr": 3,
                    "cloud_cover_percent": 3,
                    "wind_speed_kmh": 3,
                },
            }
            for index in range(24)
        ]


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
        sample = session.scalars(
            select(DemoObservation).order_by(DemoObservation.timestamp).limit(48)
        ).all()
        assert any(
            abs(
                row.spinning_reserve_mw
                - (row.online_capacity_mw - row.demand_mw)
            )
            > 0.1
            for row in sample
        )


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
    assert context["grid"]["source_provider"] == "SyntheticReplayProvider"
    assert [
        row.horizon_hours for row in context["demand_forecast"].horizons
    ] == [1, 2, 3, 4, 5, 6]
    assert (
        context["model_status"].feature_profile
        == "replay_weather_load_state_v4"
    )


def test_full_day_forecast_never_mixes_scada_and_simulation_training(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'forecast-regimes.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = DemoReplayService(
        session_factory=session_factory,
        clock=lambda: datetime(
            2026,
            7,
            15,
            10,
            tzinfo=ZoneInfo("America/Port_of_Spain"),
        ),
    )
    service.ensure_seeded()
    calls: list[dict[str, object]] = []

    class CapturingForecastService:
        def forecast_day(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(model_name="captured")

    service.forecast_service = CapturingForecastService()
    with session_factory() as session:
        state = session.get(DemoReplayState, 1)
        assert state is not None

        old_scada = {
            state.cursor_at - timedelta(days=10, hours=offset): SimpleNamespace(
                timestamp=state.cursor_at - timedelta(days=10, hours=offset),
                source="SCADA",
            )
            for offset in range(60)
        }
        service._full_day_forecast(session, state, [], old_scada, old_scada)
        simulation_call = calls[-1]
        assert len(simulation_call["history"]) > 1000
        assert all(
            isinstance(row, DemoObservation)
            for row in simulation_call["history"]
        )
        assert simulation_call["cursor_at"] == state.cursor_at

        current_scada = {
            state.cursor_at - timedelta(hours=offset): SimpleNamespace(
                timestamp=state.cursor_at - timedelta(hours=offset),
                source="SCADA",
            )
            for offset in range(60)
        }
        finalized_scada = {
            timestamp: row
            for timestamp, row in current_scada.items()
            if timestamp <= state.cursor_at - timedelta(hours=3)
        }
        service._full_day_forecast(
            session,
            state,
            [],
            current_scada,
            finalized_scada,
        )
        scada_call = calls[-1]
        assert len(scada_call["history"]) == 57
        assert all(row.source == "SCADA" for row in scada_call["history"])
        assert scada_call["cursor_at"] == state.cursor_at - timedelta(hours=3)
        assert scada_call["actual_reveal_at"] == state.cursor_at


def test_simulated_grid_uses_live_three_source_forecast_when_injected(replay_service):
    _, session_factory = replay_service
    clock = lambda: datetime(
        2026,
        7,
        15,
        10,
        42,
        tzinfo=ZoneInfo("America/Port_of_Spain"),
    )
    service = DemoReplayService(
        session_factory=session_factory,
        clock=clock,
        live_weather_service=ThreeSourceLiveWeatherService(),
    )
    service.control(ReplayControlRequest(action="reset"))

    context = service.get_dashboard_context()

    assert context is not None
    assert all(item["source_count"] == 3 for item in context["forecast"][:6])
    assert all(
        item["forecast_mode"] == "LIVE_ENSEMBLE_MAPPED_TO_SIMULATION"
        for item in context["forecast"][:6]
    )
    assert all(
        item["source_sync_status"] == "COMPLETE"
        for item in context["forecast"][:6]
    )
    upcoming = [
        point
        for point in context["replay"].full_day_load_forecast
        if point.timestamp > context["replay"].status.cursor_at
    ]
    assert upcoming[0].weather_source_count == 3


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
    service = DemoReplayService(
        session_factory=session_factory,
        clock=clock,
        replay_weather_provider=UnavailableReplayWeatherProvider(),
    )
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
    # Replay charts display the post-event value at its observation hour. The
    # forecast path separately gates this row by its exact available_at time.
    assert context["grid"]["current_demand_mw"] == 9999
    assert context["grid"]["current_generation_mw"] == 1300
    assert context["grid"]["spinning_reserve_mw"] == 200
    assert (
        context["grid"]["spinning_reserve_source"]
        == "GSYS SYSTEM_CORRECTED_SPIN_TOTAL"
    )
    assert context["grid"]["source_provider"] == "HistoricalScadaReplay"
    assert context["grid"]["quality_status"] == "UNCERTAIN"
    assert context["weather"]["temperature_c"] == 29.5
    assert context["weather"]["humidity_percent"] == 78
    assert context["risk_payload"]["probability_score"] < 1
    # Operator history displays post-event source truth at its observation
    # hour, matching the revealed demand line. Model and risk inputs remain
    # separately gated by available_at.
    assert context["replay"].operational_history[-1].generation_mw == 1300
    assert context["replay"].operational_history[-1].spinning_reserve_mw == 200
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
    assert context["scada_status"].latest_snapshot == datetime(2026, 6, 15, 10)
    assert context["scada_status"].available_at == datetime(2026, 6, 15, 11)
    assert context["scada_status"].mode == "historical_replay"

    ensemble_context = DemoReplayService(
        session_factory=session_factory,
        clock=clock,
        replay_weather_provider=ThreeModelReplayWeatherProvider(),
    ).get_dashboard_context()
    assert ensemble_context is not None
    assert all(
        item["source_count"] == 3
        for item in ensemble_context["forecast"][:6]
    )
    assert all(
        item["source_sync_status"] == "COMPLETE"
        for item in ensemble_context["forecast"][:6]
    )
    ensemble_chart = {
        point.timestamp.hour: point
        for point in ensemble_context["replay"].full_day_load_forecast
    }
    assert ensemble_chart[11].weather_source_count == 3
    assert ensemble_chart[11].forecast_demand_mw != 1111
    assert (
        ensemble_context["demand_forecast"].horizons[0].forecast_demand_mw
        == ensemble_chart[11].forecast_demand_mw
    )
    assert (
        ensemble_context["risk_payload"]["forecast_demand_60m"]
        == ensemble_chart[11].forecast_demand_mw
    )


def test_irregular_scada_overlay_keeps_observation_hours_when_availability_collides(
    tmp_path,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'irregular-overlay.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = DemoReplayService(
        session_factory=session_factory,
        clock=lambda: datetime(
            2026,
            7,
            20,
            2,
            tzinfo=ZoneInfo("America/Port_of_Spain"),
        ),
        replay_weather_provider=UnavailableReplayWeatherProvider(),
    )
    service.ensure_seeded()
    with session_factory() as session:
        for hour, demand in ((2, 1027.966), (3, 1000.70)):
            session.add(
                ScadaGridSnapshot(
                    timestamp=datetime(2026, 6, 20, hour),
                    available_at=datetime(2026, 6, 20, 4, 17, 51),
                    current_demand_mw=demand,
                    temperature_c=27,
                    spinning_reserve_mw=120,
                    available_capacity_mw=1500,
                    online_capacity_mw=1250,
                    reserve_margin_mw=1500 - demand,
                    reserve_margin_percent=(1500 - demand) / demand * 100,
                    online_spare_mw=1250 - demand,
                    quality_status="USABLE_WITH_WARNING",
                    missing_fields="",
                    coverage_percent=100,
                    quality_notes="Conditionally accepted Other quality",
                    resampling_method="interval_overlap_hourly",
                    source="June Load demand 2026.csv",
                )
            )
        session.commit()
        state = session.get(DemoReplayState, 1)
        assert state is not None
        overlay = service._scada_overlay(session, state)
        available = service._available_scada_overlay(
            overlay,
            datetime(2025, 6, 20, 2),
        )

    assert overlay[datetime(2025, 6, 20, 2)].demand_mw == 1027.966
    assert overlay[datetime(2025, 6, 20, 3)].demand_mw == 1000.70
    assert datetime(2025, 6, 20, 2) not in available
    assert datetime(2025, 6, 20, 3) not in available
