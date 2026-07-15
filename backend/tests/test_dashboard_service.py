from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.demand_forecast import DemandForecastResult
from app.models.scada import ScadaGridSnapshot
from app.services.dashboard_service import DashboardService
from app.services.model_status_service import ModelStatusService
from app.services.recommendation_engine import RecommendationEngine
from app.schemas.grid import GridStatusResponse
from app.schemas.calibration import CalibrationSnapshotResponse
from app.schemas.weather import CurrentWeatherResponse


class FakeWeatherService:
    last_current_fallback_used = False
    last_forecast_fallback_used = False

    async def get_current_weather(self, latitude, longitude, force_refresh=False):
        return {
            "timestamp": datetime.now(ZoneInfo("America/Port_of_Spain")).isoformat(),
            "temperature_c": 29,
            "humidity_percent": 70,
            "rainfall_mm_hr": 0.5,
            "cloud_cover_percent": 50,
            "wind_speed_kmh": 14,
            "weather_condition": "Partly cloudy",
            "heat_index_c": 31,
            "rain_severity": "LIGHT",
            "wind_direction_deg": 90,
            "pressure_hpa": 1012,
            "provider_name": "Test Weather",
        }

    async def get_forecast(self, latitude, longitude, days=7, force_refresh=False):
        return [
            {
                "forecast_timestamp": "2026-06-27T13:00:00-04:00",
                "temperature_c": 30,
                "humidity_percent": 68,
                "rainfall_mm_hr": 0,
                "cloud_cover_percent": 40,
                "wind_speed_kmh": 15,
                "weather_condition": "Partly cloudy",
                "heat_index_c": 32,
                "precipitation_probability_percent": 10,
                "confidence_score": 0.9,
                "rain_severity": "DRY",
                "provider_name": "Test Weather",
            }
        ]


class FakeGridService:
    async def get_grid_status(self):
        return {
            "timestamp": datetime.now(ZoneInfo("America/Port_of_Spain")).isoformat(),
            "current_demand_mw": 950,
            "current_generation_mw": 960,
            "total_available_capacity_mw": 1200,
            "reserve_margin_percent": 26.3,
            "grid_status": "NORMAL",
            "demand_period": "AFTERNOON",
            "source_provider": "MockGridProvider",
            "generation_units": [],
        }

    async def get_generation_status(self):
        return []


class NoCalibrationService:
    def get_snapshot(self, weather):
        return None


class HistoricalCalibrationService:
    def get_snapshot(self, weather):
        return CalibrationSnapshotResponse(
            selected_scenario_key="hot",
            selected_scenario_label="Hot Day",
            selected_temperature_c=35.0,
            selection_reason="Historical calibration profile",
        )


class FallbackWeatherService(FakeWeatherService):
    last_current_fallback_used = True
    last_forecast_fallback_used = False


class StaleWeatherService(FakeWeatherService):
    async def get_current_weather(self, latitude, longitude, force_refresh=False):
        weather = await super().get_current_weather(
            latitude,
            longitude,
            force_refresh=force_refresh,
        )
        weather["timestamp"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        return weather


class RecordingPersistenceService:
    def __init__(self):
        self.snapshots = []

    def persist(self, snapshot):
        self.snapshots.append(snapshot)
        return True


class FlakyGridService(FakeGridService):
    def __init__(self):
        self.calls = 0

    async def get_grid_status(self):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("SCADA connection lost")
        return await super().get_grid_status()


class StaleGridService(FakeGridService):
    async def get_grid_status(self):
        status = await super().get_grid_status()
        status["timestamp"] = (
            datetime.now(timezone.utc) - timedelta(minutes=2)
        ).isoformat()
        return status


class UncertainGridService(FakeGridService):
    async def get_grid_status(self):
        status = await super().get_grid_status()
        status["quality_status"] = "UNCERTAIN"
        return status


def _model_session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dashboard_model.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed_model_status_data(session_factory):
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        session.add(
            ScadaGridSnapshot(
                timestamp=now - timedelta(minutes=5),
                current_demand_mw=900,
                temperature_c=29,
                spinning_reserve_mw=80,
                available_capacity_mw=1180,
                online_capacity_mw=1120,
                reserve_margin_mw=280,
                reserve_margin_percent=31.1,
                online_spare_mw=220,
                quality_status="GOOD",
                missing_fields="",
                source="scada.csv",
            )
        )
        session.add(
            DemandForecastResult(
                forecast_timestamp=now + timedelta(minutes=55),
                generated_at=now,
                horizon_hours=1,
                forecast_demand_mw=1040,
                forecast_uncertainty_mw=30,
                model_name="persistence",
                model_version="demand-forecast-v1.3",
                baseline_name="persistence",
                baseline_forecast_mw=1030,
                mae=10,
                rmse=12,
                mape=1.2,
                residual_std=30,
                ml_beats_baseline=False,
                quality_status="BASELINE_ACTIVE",
            )
        )
        session.commit()


@pytest.mark.asyncio
async def test_dashboard_snapshot_aggregates_live_data_and_persists():
    persistence = RecordingPersistenceService()
    service = DashboardService(
        weather_service=FakeWeatherService(),
        grid_service=FakeGridService(),
        recommendation_engine=RecommendationEngine(),
        calibration_service=NoCalibrationService(),
        persistence_service=persistence,
    )

    snapshot = await service.get_snapshot(days=1)

    assert snapshot.weather.temperature_c == 29
    assert snapshot.grid.current_demand_mw == 950
    assert len(snapshot.forecast.items) == 1
    assert snapshot.data_quality.weather_status == "LIVE"
    assert snapshot.data_quality.grid_status == "SIMULATED"
    assert snapshot.data_quality.decision_status == "SIMULATION"
    assert snapshot.data_quality.calibration_status == "UNAVAILABLE"
    assert snapshot.data_quality.overall_status == "GOOD"
    assert any("not live dispatch" in note for note in snapshot.data_quality.notes)
    assert len(persistence.snapshots) == 1


def test_dashboard_data_quality_covers_calibrated_fallback_and_stale_branches():
    service = DashboardService(
        weather_service=FakeWeatherService(),
        grid_service=FakeGridService(),
        recommendation_engine=RecommendationEngine(),
        calibration_service=NoCalibrationService(),
        persistence_service=RecordingPersistenceService(),
    )

    fresh_weather = CurrentWeatherResponse(
        timestamp=datetime.now(timezone.utc),
        temperature_c=30,
        humidity_percent=72,
        rainfall_mm_hr=0.2,
        cloud_cover_percent=45,
        wind_speed_kmh=14,
        weather_condition="Partly cloudy",
        heat_index_c=33,
        rain_severity="LIGHT",
        provider_name="Open-Meteo + SCADA Calibration",
    )
    fresh_grid = GridStatusResponse.model_validate(
        {
            "timestamp": datetime.now(ZoneInfo("America/Port_of_Spain")).isoformat(),
            "current_demand_mw": 950,
            "current_generation_mw": 960,
            "total_available_capacity_mw": 1200,
            "reserve_margin_percent": 26.3,
            "grid_status": "NORMAL",
            "demand_period": "AFTERNOON",
            "source_provider": "MockGridProvider",
            "generation_units": [],
        }
    )

    service.weather_service.last_current_fallback_used = True
    service.weather_service.last_forecast_fallback_used = False
    fallback_quality = service._build_data_quality(fresh_weather, fresh_grid, calibration_available=True)
    assert fallback_quality.weather_status == "CALIBRATED"
    assert fallback_quality.fallback_used is True
    assert fallback_quality.calibration_status == "CALIBRATED"

    stale_weather = fresh_weather.model_copy(
        update={
            "timestamp": datetime.now(timezone.utc) - timedelta(hours=2),
            "provider_name": "Open-Meteo",
        }
    )
    service.weather_service.last_current_fallback_used = False
    service.weather_service.last_forecast_fallback_used = False
    stale_quality = service._build_data_quality(stale_weather, fresh_grid, calibration_available=False)
    assert stale_quality.weather_status == "STALE"
    assert stale_quality.is_stale is True
    assert stale_quality.calibration_status == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_dashboard_snapshot_marks_fallback_weather_when_provider_switches():
    service = DashboardService(
        weather_service=FallbackWeatherService(),
        grid_service=FakeGridService(),
        recommendation_engine=RecommendationEngine(),
        calibration_service=NoCalibrationService(),
        persistence_service=RecordingPersistenceService(),
    )

    snapshot = await service.get_snapshot(days=1)

    assert snapshot.data_quality.weather_status == "FALLBACK"
    assert snapshot.data_quality.fallback_used is True


@pytest.mark.asyncio
async def test_historical_scada_calibration_does_not_replace_live_temperature():
    service = DashboardService(
        weather_service=FakeWeatherService(),
        grid_service=FakeGridService(),
        recommendation_engine=RecommendationEngine(),
        calibration_service=HistoricalCalibrationService(),
        persistence_service=RecordingPersistenceService(),
    )

    snapshot = await service.get_snapshot(days=1)

    assert snapshot.weather.temperature_c == 29
    assert snapshot.weather.provider_name == "Test Weather"
    assert snapshot.calibration is not None
    assert snapshot.calibration.selected_temperature_c == 35


@pytest.mark.asyncio
async def test_dashboard_reuses_last_good_grid_snapshot_and_marks_fallback():
    grid_service = FlakyGridService()
    service = DashboardService(
        weather_service=FakeWeatherService(),
        grid_service=grid_service,
        recommendation_engine=RecommendationEngine(),
        calibration_service=NoCalibrationService(),
        persistence_service=RecordingPersistenceService(),
    )

    first = await service.get_snapshot(days=1)
    second = await service.get_snapshot(days=1)

    assert first.grid.current_demand_mw == 950
    assert second.grid.current_demand_mw == 950
    assert second.data_quality.grid_fallback_used is True
    assert second.data_quality.grid_status == "FALLBACK"
    assert second.data_quality.overall_status == "DEGRADED"


@pytest.mark.asyncio
async def test_stale_grid_telemetry_inhibits_recommendation():
    service = DashboardService(
        weather_service=FakeWeatherService(),
        grid_service=StaleGridService(),
        recommendation_engine=RecommendationEngine(),
        calibration_service=NoCalibrationService(),
        persistence_service=RecordingPersistenceService(),
    )

    snapshot = await service.get_snapshot(days=1)

    assert snapshot.data_quality.grid_is_stale is True
    assert snapshot.data_quality.decision_status == "INHIBITED"
    assert snapshot.probability.risk_level == "UNAVAILABLE"
    assert snapshot.recommendation.recommendation == "DATA UNAVAILABLE"


@pytest.mark.asyncio
async def test_uncertain_grid_quality_inhibits_recommendation():
    service = DashboardService(
        weather_service=FakeWeatherService(),
        grid_service=UncertainGridService(),
        recommendation_engine=RecommendationEngine(),
        calibration_service=NoCalibrationService(),
        persistence_service=RecordingPersistenceService(),
    )

    snapshot = await service.get_snapshot(days=1)

    assert snapshot.data_quality.grid_status == "UNCERTAIN"
    assert snapshot.data_quality.decision_status == "INHIBITED"
    assert snapshot.recommendation.recommendation == "DATA UNAVAILABLE"


@pytest.mark.asyncio
async def test_stale_weather_inhibits_weather_based_recommendation():
    service = DashboardService(
        weather_service=StaleWeatherService(),
        grid_service=FakeGridService(),
        recommendation_engine=RecommendationEngine(),
        calibration_service=NoCalibrationService(),
        persistence_service=RecordingPersistenceService(),
    )

    snapshot = await service.get_snapshot(days=1)

    assert snapshot.data_quality.is_stale is True


@pytest.mark.asyncio
async def test_dashboard_snapshot_exposes_model_scada_status_and_operating_risk(tmp_path):
    session_factory = _model_session_factory(tmp_path)
    _seed_model_status_data(session_factory)
    service = DashboardService(
        weather_service=FakeWeatherService(),
        grid_service=FakeGridService(),
        recommendation_engine=RecommendationEngine(),
        calibration_service=NoCalibrationService(),
        model_status_service=ModelStatusService(session_factory=session_factory),
        persistence_service=RecordingPersistenceService(),
    )

    snapshot = await service.get_snapshot(days=1)

    assert snapshot.demand_forecast is not None
    assert len(snapshot.demand_forecast.horizons) == 1
    assert snapshot.model_status is not None
    assert snapshot.model_status.mode == "BASELINE_ACTIVE"
    assert snapshot.model_status.metrics.mae == 10
    assert snapshot.scada_status is not None
    assert snapshot.scada_status.quality_status == "GOOD"
    assert snapshot.probability.engine_version == "operating-risk-v2.0"
    assert snapshot.probability.risk_level == "HIGH"
    assert snapshot.probability.forecast_demand_30m == 970
    assert snapshot.recommendation.recommendation == "START HEAVY GENERATOR SET"
    assert snapshot.data_quality.decision_status == "SIMULATION"


def test_historical_backtest_result_cannot_drive_live_operating_risk(tmp_path):
    session_factory = _model_session_factory(tmp_path)
    _seed_model_status_data(session_factory)
    with session_factory() as session:
        forecast = session.scalar(select(DemandForecastResult))
        scada = session.scalar(select(ScadaGridSnapshot))
        assert forecast is not None
        assert scada is not None
        forecast.forecast_timestamp = scada.timestamp
        session.commit()

    payload = ModelStatusService(
        session_factory=session_factory
    ).get_operating_risk_payload()

    assert payload is None


def test_dashboard_selects_weather_nearest_requested_forecast_horizon():
    reference = "2026-07-10T12:10:00-04:00"
    items = [
        {"forecast_timestamp": "2026-07-10T12:00:00-04:00", "temperature_c": 29},
        {"forecast_timestamp": "2026-07-10T13:00:00-04:00", "temperature_c": 31},
        {"forecast_timestamp": "2026-07-10T14:00:00-04:00", "temperature_c": 32},
    ]

    selected = DashboardService._forecast_for_horizon(
        items,
        reference_time=reference,
        horizon_minutes=60,
    )

    assert selected is items[1]
