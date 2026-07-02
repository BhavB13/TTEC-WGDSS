from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.grid_data import GridData
from app.models.generation import Generation
from app.models.probability_results import ProbabilityResult
from app.models.weather import Weather
from app.schemas.dashboard import DashboardSnapshotResponse, ForecastBundleResponse
from app.schemas.data_quality import DataQualityResponse
from app.schemas.grid import GenerationUnitResponse, GridStatusResponse
from app.schemas.probability import ProbabilityResponse
from app.schemas.recommendation import RecommendationResponse
from app.schemas.weather import CurrentWeatherResponse
from app.services.snapshot_persistence_service import SnapshotPersistenceService


def test_snapshot_persistence_writes_weather_grid_and_probability(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    timestamp = datetime.now(timezone.utc)
    probability = ProbabilityResponse(
        probability_score=0.4,
        risk_level="LOW",
        forecast_demand_30m=960,
        forecast_demand_60m=970,
        factors=["Stable conditions"],
        reason="Stable conditions",
    )
    snapshot = DashboardSnapshotResponse(
        weather=CurrentWeatherResponse(
            timestamp=timestamp,
            temperature_c=30,
            humidity_percent=70,
            rainfall_mm_hr=0,
            cloud_cover_percent=40,
            wind_speed_kmh=15,
            weather_condition="Partly cloudy",
            heat_index_c=33,
            rain_severity="DRY",
            provider_name="Test Provider",
        ),
        grid=GridStatusResponse(
            timestamp=timestamp,
            current_demand_mw=950,
            current_generation_mw=960,
            total_available_capacity_mw=1200,
            reserve_margin_percent=26,
            grid_status="NORMAL",
            demand_period="AFTERNOON",
            source_provider="MockGridProvider",
            generation_units=[
                GenerationUnitResponse(
                    station_name="Point Lisas",
                    unit_name="GT-1",
                    fuel_type="Natural Gas",
                    available_capacity_mw=120,
                    current_output_mw=110,
                    status="ONLINE",
                    is_dispatchable=True,
                    observed_at=timestamp,
                    source_tag="test.point_lisas.gt1",
                )
            ],
        ),
        forecast=ForecastBundleResponse(items=[]),
        probability=probability,
        recommendation=RecommendationResponse(
            **probability.model_dump(),
            recommendation="NO ACTION REQUIRED",
        ),
        data_quality=DataQualityResponse(
            overall_status="GOOD",
            weather_status="LIVE",
            grid_status="SIMULATED",
            calibration_status="UNAVAILABLE",
            weather_source="Test Provider",
            grid_source="MockGridProvider",
        ),
    )

    assert SnapshotPersistenceService(session_factory=session_factory).persist(snapshot) is True

    with session_factory() as session:
        assert session.scalar(select(func.count(Weather.id))) == 1
        assert session.scalar(select(func.count(GridData.id))) == 1
        assert session.scalar(select(func.count(ProbabilityResult.id))) == 1
        assert session.scalar(select(func.count(Generation.id))) == 1
        probability_row = session.scalar(select(ProbabilityResult))
        assert probability_row is not None
        assert probability_row.snapshot_id == snapshot.snapshot_id
        assert probability_row.engine_version == "unknown"
