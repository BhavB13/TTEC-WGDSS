from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from app.database.session import SessionLocal
from app.models.generation import Generation
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
                            snapshot_id=snapshot.snapshot_id,
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
                            snapshot_id=snapshot.snapshot_id,
                            timestamp=grid.timestamp,
                            current_demand_mw=grid.current_demand_mw,
                            current_generation_mw=grid.current_generation_mw,
                            total_available_capacity_mw=grid.total_available_capacity_mw,
                            reserve_margin_percent=grid.reserve_margin_percent,
                            spinning_reserve_mw=grid.spinning_reserve_mw,
                            spinning_reserve_source=grid.spinning_reserve_source,
                            grid_status=grid.grid_status,
                            demand_period=grid.demand_period,
                            source_provider=grid.source_provider,
                            received_at=grid.received_at,
                            quality_status=str(grid.quality_status),
                        )
                    )

                for unit in grid.generation_units:
                    session.add(
                        Generation(
                            snapshot_id=snapshot.snapshot_id,
                            station_name=unit.station_name,
                            unit_name=unit.unit_name,
                            fuel_type=unit.fuel_type,
                            available_capacity_mw=unit.available_capacity_mw,
                            current_output_mw=unit.current_output_mw,
                            status=unit.status,
                            is_dispatchable=unit.is_dispatchable,
                            observed_at=unit.observed_at,
                            last_updated=(
                                unit.observed_at
                                or grid.timestamp
                                or datetime.now(timezone.utc)
                            ),
                            quality_status=str(unit.quality_status),
                            source_tag=unit.source_tag,
                        )
                    )

                session.add(
                    ProbabilityResult(
                        snapshot_id=snapshot.snapshot_id,
                        probability_score=probability.probability_score,
                        risk_level=probability.risk_level,
                        forecast_demand_30m=probability.forecast_demand_30m,
                        forecast_demand_60m=probability.forecast_demand_60m,
                        recommendation=recommendation.recommendation,
                        factors=json.dumps(probability.factors),
                        engine_version=probability.engine_version,
                        weather_observed_at=weather.timestamp,
                        grid_observed_at=grid.timestamp,
                        weather_source=weather.provider_name,
                        grid_source=grid.source_provider,
                        input_quality_status=snapshot.data_quality.overall_status,
                        calibration_scenario=(
                            snapshot.calibration.selected_scenario_label
                            if snapshot.calibration is not None
                            else None
                        ),
                    )
                )
                session.commit()
            return True
        except SQLAlchemyError:
            logger.exception("Dashboard snapshot persistence failed")
            return False
