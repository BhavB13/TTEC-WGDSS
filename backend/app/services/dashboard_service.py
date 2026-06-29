from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.schemas.dashboard import DashboardSnapshotResponse, ForecastBundleResponse
from app.schemas.data_quality import DataQualityResponse
from app.schemas.grid import GridStatusResponse
from app.schemas.probability import ProbabilityResponse
from app.schemas.recommendation import RecommendationResponse
from app.schemas.weather import CurrentWeatherResponse
from app.services.calibration_service import CalibrationService
from app.services.grid_service import GridService
from app.services.recommendation_engine import RecommendationEngine
from app.services.snapshot_persistence_service import SnapshotPersistenceService
from app.services.weather_service import WeatherService


class DashboardService:
    def __init__(
        self,
        weather_service: WeatherService | None = None,
        grid_service: GridService | None = None,
        recommendation_engine: RecommendationEngine | None = None,
        calibration_service: CalibrationService | None = None,
        persistence_service: SnapshotPersistenceService | None = None,
    ) -> None:
        self.weather_service = weather_service or WeatherService()
        self.grid_service = grid_service or GridService()
        self.recommendation_engine = recommendation_engine or RecommendationEngine()
        self.calibration_service = calibration_service or CalibrationService()
        self.persistence_service = persistence_service or SnapshotPersistenceService()

    async def get_snapshot(
        self,
        latitude: float = settings.DEFAULT_LATITUDE,
        longitude: float = settings.DEFAULT_LONGITUDE,
        days: int = 7,
        force_refresh: bool = False,
    ) -> DashboardSnapshotResponse:
        weather_task = self.weather_service.get_current_weather(
            latitude,
            longitude,
            force_refresh=force_refresh,
        )
        forecast_task = self.weather_service.get_forecast(
            latitude,
            longitude,
            days=days,
            force_refresh=force_refresh,
        )
        grid_task = self.grid_service.get_grid_status()
        generation_task = self.grid_service.get_generation_status()

        weather, forecast, grid_status, generation_units = await asyncio.gather(
            weather_task,
            forecast_task,
            grid_task,
            generation_task,
        )

        grid_status = {**grid_status, "generation_units": generation_units}
        calibration = self.calibration_service.get_snapshot(weather)

        calibration_payload = calibration.model_dump() if calibration is not None else None
        probability_payload = self.recommendation_engine.evaluate(
            weather,
            grid_status,
            calibration=calibration_payload,
        )
        weather_response = CurrentWeatherResponse.model_validate(weather)
        grid_response = GridStatusResponse.model_validate(grid_status)
        probability = ProbabilityResponse(
            probability_score=probability_payload["probability_score"],
            risk_level=probability_payload["risk_level"],
            forecast_demand_30m=probability_payload["forecast_demand_30m"],
            forecast_demand_60m=probability_payload["forecast_demand_60m"],
            factors=probability_payload["factors"],
            reason=probability_payload["reason"],
        )
        recommendation = RecommendationResponse(
            probability_score=probability_payload["probability_score"],
            risk_level=probability_payload["risk_level"],
            forecast_demand_30m=probability_payload["forecast_demand_30m"],
            forecast_demand_60m=probability_payload["forecast_demand_60m"],
            factors=probability_payload["factors"],
            reason=probability_payload["reason"],
            recommendation=probability_payload["recommendation"],
        )

        snapshot = DashboardSnapshotResponse(
            weather=weather_response,
            grid=grid_response,
            forecast=ForecastBundleResponse(items=forecast),
            probability=probability,
            recommendation=recommendation,
            calibration=calibration,
            data_quality=self._build_data_quality(
                weather_response,
                grid_response,
                calibration is not None,
            ),
        )
        if settings.SNAPSHOT_PERSISTENCE_ENABLED:
            persisted = await asyncio.to_thread(self.persistence_service.persist, snapshot)
            if not persisted:
                snapshot.data_quality.notes.append("Historical persistence unavailable")
                snapshot.data_quality.overall_status = "DEGRADED"
        return snapshot

    async def get_probability_and_recommendation(
        self,
        latitude: float = settings.DEFAULT_LATITUDE,
        longitude: float = settings.DEFAULT_LONGITUDE,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        snapshot = await self.get_snapshot(
            latitude=latitude,
            longitude=longitude,
            force_refresh=force_refresh,
        )
        return {
            "probability": snapshot.probability.model_dump(),
            "recommendation": snapshot.recommendation.model_dump(),
        }

    @staticmethod
    def _calculate_heat_index(temperature_c: float, humidity_percent: float) -> float:
        if temperature_c <= 0:
            return temperature_c
        humidity_factor = max(0.0, humidity_percent)
        return round(temperature_c + 0.033 * humidity_factor - 0.70, 2)

    def _build_data_quality(
        self,
        weather: CurrentWeatherResponse,
        grid: GridStatusResponse,
        calibration_available: bool,
    ) -> DataQualityResponse:
        age_seconds: int | None = None
        if weather.timestamp is not None:
            observed = weather.timestamp
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            age_seconds = max(0, int((datetime.now(timezone.utc) - observed).total_seconds()))

        stale = age_seconds is not None and age_seconds > settings.DATA_STALE_AFTER_SECONDS
        fallback_used = (
            self.weather_service.last_current_fallback_used
            or self.weather_service.last_forecast_fallback_used
        )
        consensus_degraded = getattr(
            self.weather_service,
            "last_forecast_consensus_degraded",
            False,
        )
        forecast_source_count = getattr(
            self.weather_service,
            "last_forecast_source_count",
            1,
        )
        forecast_provider_names = getattr(
            self.weather_service,
            "last_forecast_provider_names",
            [],
        )
        calibrated = "SCADA Calibration" in weather.provider_name
        weather_status = "STALE" if stale else ("FALLBACK" if fallback_used else "LIVE")
        if calibrated:
            weather_status = "CALIBRATED"

        notes: list[str] = []
        if stale:
            notes.append("Weather observation exceeds the freshness threshold")
        if fallback_used:
            notes.append("A fallback weather provider supplied part of this snapshot")
        if consensus_degraded:
            notes.append(
                "Hourly forecast is operating on one source; cross-source verification is unavailable"
            )
        elif forecast_source_count > 1:
            notes.append(
                "Hourly forecast cross-checked across "
                f"{forecast_source_count} sources: {', '.join(forecast_provider_names)}"
            )
        if not calibration_available:
            notes.append("SCADA calibration profiles are not loaded")

        return DataQualityResponse(
            overall_status=(
                "DEGRADED"
                if stale or fallback_used or consensus_degraded
                else "GOOD"
            ),
            weather_status=weather_status,
            grid_status="SIMULATED" if "Mock" in grid.source_provider else "LIVE",
            calibration_status="CALIBRATED" if calibration_available else "UNAVAILABLE",
            weather_source=weather.provider_name,
            grid_source=grid.source_provider,
            observed_at=weather.timestamp,
            age_seconds=age_seconds,
            is_stale=stale,
            fallback_used=fallback_used,
            notes=notes,
        )
