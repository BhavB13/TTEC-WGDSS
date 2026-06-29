from __future__ import annotations

import json
import logging

from sqlalchemy.exc import SQLAlchemyError

from app.database.session import SessionLocal
from app.models.grid_data import GridData
from app.models.probability_results import ProbabilityResult
from app.models.weather import Weather
from app.schemas.dashboard import DashboardSnapshotResponse

logger = logging.getLogger(__name__)


class SnapshotPersistenceService:
    """Persist live dashboard observations without blocking snapshot delivery."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def persist(self, snapshot: DashboardSnapshotResponse) -> bool:
        try:
            with self.session_factory() as session:
                weather = snapshot.weather
                grid = snapshot.grid
                probability = snapshot.probability
                recommendation = snapshot.recommendation

                if weather.timestamp is not None:
                    session.add(
                        Weather(
                            timestamp=weather.timestamp,
                            temperature_c=weather.temperature_c,
                            humidity_percent=weather.humidity_percent,
                            wind_speed_kph=weather.wind_speed_kmh,
                            wind_direction_deg=weather.wind_direction_deg,
                            pressure_hpa=weather.pressure_hpa,
                            precipitation_mm=weather.rainfall_mm_hr,
                            rainfall_mm_hr=weather.rainfall_mm_hr,
                            cloud_cover_percent=weather.cloud_cover_percent,
                            weather_condition=weather.weather_condition,
                            heat_index_c=weather.heat_index_c,
                            rain_severity=weather.rain_severity,
                            provider_name=weather.provider_name,
                        )
                    )

                if grid.timestamp is not None:
                    session.add(
                        GridData(
                            timestamp=grid.timestamp,
                            current_demand_mw=grid.current_demand_mw,
                            current_generation_mw=grid.current_generation_mw,
                            total_available_capacity_mw=grid.total_available_capacity_mw,
                            reserve_margin_percent=grid.reserve_margin_percent,
                            grid_status=grid.grid_status,
                            demand_period=grid.demand_period,
                            source_provider=grid.source_provider,
                        )
                    )

                session.add(
                    ProbabilityResult(
                        probability_score=probability.probability_score,
                        risk_level=probability.risk_level,
                        forecast_demand_30m=probability.forecast_demand_30m,
                        forecast_demand_60m=probability.forecast_demand_60m,
                        recommendation=recommendation.recommendation,
                        factors=json.dumps(probability.factors),
                    )
                )
                session.commit()
            return True
        except SQLAlchemyError:
            logger.exception("Dashboard snapshot persistence failed")
            return False
