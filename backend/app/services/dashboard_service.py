from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.schemas.dashboard import DashboardSnapshotResponse, ForecastBundleResponse
from app.schemas.probability import ProbabilityResponse
from app.schemas.recommendation import RecommendationResponse
from app.services.grid_service import GridService
from app.services.recommendation_engine import RecommendationEngine
from app.services.weather_service import WeatherService


class DashboardService:
    def __init__(
        self,
        weather_service: WeatherService | None = None,
        grid_service: GridService | None = None,
        recommendation_engine: RecommendationEngine | None = None,
    ) -> None:
        self.weather_service = weather_service or WeatherService()
        self.grid_service = grid_service or GridService()
        self.recommendation_engine = recommendation_engine or RecommendationEngine()

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
        probability_payload = self.recommendation_engine.evaluate(weather, grid_status)
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

        return DashboardSnapshotResponse(
            weather=weather,
            grid=grid_status,
            forecast=ForecastBundleResponse(items=forecast),
            probability=probability,
            recommendation=recommendation,
        )

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
