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
from app.services.demo_replay_service import DemoReplayService
from app.services.grid_service import GridService
from app.services.model_status_service import ModelStatusService
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
        model_status_service: ModelStatusService | None = None,
        persistence_service: SnapshotPersistenceService | None = None,
        demo_replay_service: DemoReplayService | None = None,
    ) -> None:
        self.weather_service = weather_service or WeatherService()
        self.grid_service = grid_service or GridService()
        self.recommendation_engine = recommendation_engine or RecommendationEngine()
        self.calibration_service = calibration_service or CalibrationService()
        self.model_status_service = model_status_service or ModelStatusService()
        self.persistence_service = persistence_service or SnapshotPersistenceService()
        self.demo_replay_service = demo_replay_service
        if (
            self.demo_replay_service is None
            and weather_service is None
            and grid_service is None
            and settings.DEMO_REPLAY_ENABLED
        ):
            self.demo_replay_service = DemoReplayService()
        self._last_weather: dict[str, Any] | None = None
        self._last_forecast: list[dict[str, Any]] | None = None
        self._last_grid_status: dict[str, Any] | None = None
        self._last_generation_units: list[dict[str, Any]] | None = None

    async def get_snapshot(
        self,
        latitude: float = settings.DEFAULT_LATITUDE,
        longitude: float = settings.DEFAULT_LONGITUDE,
        days: int = 7,
        force_refresh: bool = False,
    ) -> DashboardSnapshotResponse:
        replay_context = (
            await asyncio.to_thread(self.demo_replay_service.get_dashboard_context)
            if self.demo_replay_service is not None
            else None
        )
        replay_active = replay_context is not None
        if replay_context is not None:
            results = [
                replay_context["weather"],
                replay_context["forecast"],
                replay_context["grid"],
                replay_context["generation_units"],
            ]
        else:
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
            results = await asyncio.gather(
                weather_task,
                forecast_task,
                grid_task,
                generation_task,
                return_exceptions=True,
            )
        degradation_notes: list[str] = []
        weather, weather_fallback = self._resolve_result(
            "current weather",
            results[0],
            self._last_weather,
            degradation_notes,
        )
        forecast, _ = self._resolve_result(
            "hourly forecast",
            results[1],
            self._last_forecast,
            degradation_notes,
            default=[],
        )
        grid_status, grid_fallback = self._resolve_result(
            "grid telemetry",
            results[2],
            self._last_grid_status,
            degradation_notes,
        )
        generation_units, _ = self._resolve_result(
            "generation-unit telemetry",
            results[3],
            self._last_generation_units,
            degradation_notes,
            default=grid_status.get("generation_units", []),
        )

        if not weather_fallback:
            self._last_weather = weather
        if not isinstance(results[1], BaseException):
            self._last_forecast = forecast
        if not grid_fallback:
            self._last_grid_status = grid_status
        if not isinstance(results[3], BaseException):
            self._last_generation_units = generation_units

        grid_status = {**grid_status, "generation_units": generation_units}
        calibration = self.calibration_service.get_snapshot(weather)

        calibration_payload = calibration.model_dump() if calibration is not None else None
        weather_age_seconds = 0 if replay_active else self._age_seconds(weather.get("timestamp"))
        grid_age_seconds = 0 if replay_active else self._age_seconds(grid_status.get("timestamp"))
        grid_quality = str(grid_status.get("quality_status", "GOOD")).upper()
        grid_missing_fields = grid_status.get("missing_fields", [])
        grid_is_stale = (
            grid_age_seconds is not None
            and grid_age_seconds > settings.GRID_STALE_AFTER_SECONDS
        )
        weather_is_stale = (
            weather_age_seconds is not None
            and weather_age_seconds > settings.DATA_STALE_AFTER_SECONDS
        )
        acceptable_grid_quality = (
            {"GOOD", "UNCERTAIN"} if replay_active else {"GOOD"}
        )
        decision_inhibited = (
            weather_is_stale
            or grid_is_stale
            or grid_quality not in acceptable_grid_quality
            or bool(grid_missing_fields)
        )
        if decision_inhibited:
            probability_payload = self.recommendation_engine.unavailable(
                float(grid_status["current_demand_mw"]),
                "Required weather or grid telemetry is stale, incomplete, or bad; "
                "recommendation inhibited",
            )
        else:
            probability_payload = (
                (replay_context.get("risk_payload") if replay_context is not None else None)
                or self.model_status_service.get_operating_risk_payload()
                or self.recommendation_engine.evaluate(
                    weather,
                    grid_status,
                    calibration=calibration_payload,
                    forecast_weather=self._forecast_for_horizon(
                        forecast,
                        reference_time=weather.get("timestamp"),
                        horizon_minutes=60,
                    ),
                )
            )
        weather_response = CurrentWeatherResponse.model_validate(weather)
        grid_response = GridStatusResponse.model_validate(grid_status)
        probability = ProbabilityResponse(
            engine_version=probability_payload["engine_version"],
            probability_score=probability_payload["probability_score"],
            risk_level=probability_payload["risk_level"],
            forecast_demand_30m=probability_payload["forecast_demand_30m"],
            forecast_demand_60m=probability_payload["forecast_demand_60m"],
            factors=probability_payload["factors"],
            reason=probability_payload["reason"],
            **self._dispatch_evidence(probability_payload),
        )
        recommendation = RecommendationResponse(
            engine_version=probability_payload["engine_version"],
            probability_score=probability_payload["probability_score"],
            risk_level=probability_payload["risk_level"],
            forecast_demand_30m=probability_payload["forecast_demand_30m"],
            forecast_demand_60m=probability_payload["forecast_demand_60m"],
            factors=probability_payload["factors"],
            reason=probability_payload["reason"],
            recommendation=probability_payload["recommendation"],
            **self._dispatch_evidence(probability_payload),
        )
        demand_forecast = self.model_status_service.get_demand_forecast_bundle()
        model_status = self.model_status_service.get_model_status()
        scada_status = self.model_status_service.get_scada_status()

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
                degradation_notes=degradation_notes,
                grid_fallback_used=grid_fallback,
                weather_cache_fallback=weather_fallback,
                replay_active=replay_active,
                forecast_items=forecast,
            ),
            demand_forecast=demand_forecast,
            model_status=model_status,
            scada_status=scada_status,
            replay=(replay_context["replay"] if replay_context is not None else None),
        )
        if settings.SNAPSHOT_PERSISTENCE_ENABLED:
            persisted = await asyncio.to_thread(self.persistence_service.persist, snapshot)
            if not persisted:
                snapshot.data_quality.notes.append("Historical persistence unavailable")
                snapshot.data_quality.overall_status = "DEGRADED"
        return snapshot

    @staticmethod
    def _dispatch_evidence(payload: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "decision_action",
            "generator_set",
            "recommended_capacity_mw",
            "projected_shortfall_mw",
            "expected_shortfall_mw",
            "expected_load_rise_mw",
            "expected_rise_minutes",
            "startup_time_minutes",
            "decision_confidence",
            "weather_effect_mw",
            "available_start_capacity_mw",
            "residual_shortfall_mw",
        )
        return {field: payload[field] for field in fields if field in payload}

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

    @classmethod
    def _forecast_for_horizon(
        cls,
        forecast: list[dict[str, Any]],
        reference_time: Any,
        horizon_minutes: int,
    ) -> dict[str, Any] | None:
        if not forecast:
            return None
        reference = cls._parse_datetime(reference_time)
        if reference is None:
            return forecast[0]
        target = reference.timestamp() + horizon_minutes * 60
        timestamped = [
            (item, cls._parse_datetime(item.get("forecast_timestamp")))
            for item in forecast
        ]
        valid = [(item, timestamp) for item, timestamp in timestamped if timestamp]
        if not valid:
            return forecast[0]
        return min(valid, key=lambda pair: abs(pair[1].timestamp() - target))[0]

    def _build_data_quality(
        self,
        weather: CurrentWeatherResponse,
        grid: GridStatusResponse,
        calibration_available: bool,
        degradation_notes: list[str] | None = None,
        grid_fallback_used: bool = False,
        weather_cache_fallback: bool = False,
        replay_active: bool = False,
        forecast_items: list[dict[str, Any]] | None = None,
    ) -> DataQualityResponse:
        age_seconds = 0 if replay_active else self._age_seconds(weather.timestamp)
        grid_age_seconds = 0 if replay_active else self._age_seconds(grid.timestamp)

        stale = age_seconds is not None and age_seconds > settings.DATA_STALE_AFTER_SECONDS
        grid_stale = (
            grid_age_seconds is not None
            and grid_age_seconds > settings.GRID_STALE_AFTER_SECONDS
        )
        fallback_used = (
            self.weather_service.last_current_fallback_used
            or self.weather_service.last_forecast_fallback_used
            or weather_cache_fallback
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
        if replay_active and forecast_items:
            forecast_source_count = max(
                int(item.get("source_count", 1)) for item in forecast_items
            )
            forecast_provider_names = list(
                dict.fromkeys(
                    name
                    for item in forecast_items
                    for name in item.get("source_names", [])
                )
            )
            consensus_degraded = any(
                item.get("source_sync_status") != "COMPLETE"
                for item in forecast_items[:6]
            )
        calibrated = "SCADA Calibration" in weather.provider_name
        weather_status = "STALE" if stale else ("FALLBACK" if fallback_used else "LIVE")
        if replay_active:
            weather_status = "SIMULATED_REPLAY"
        if calibrated:
            weather_status = "CALIBRATED"

        notes: list[str] = list(degradation_notes or [])
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
        grid_quality = str(grid.quality_status).upper()
        if grid_stale:
            notes.append("Grid telemetry exceeds the freshness threshold")
        if grid_quality in {"BAD", "STALE"}:
            notes.append(f"Grid telemetry quality is {grid_quality}")
        if grid.missing_fields:
            notes.append(
                "Grid telemetry is missing: " + ", ".join(grid.missing_fields)
            )
        simulated_grid = "Mock" in grid.source_provider or replay_active
        decision_status = (
            "INHIBITED"
            if (
                stale
                or grid_stale
                or grid_quality
                not in ({"GOOD", "UNCERTAIN"} if replay_active else {"GOOD"})
                or grid.missing_fields
            )
            else ("SIMULATION" if simulated_grid else "AVAILABLE")
        )
        if grid_fallback_used:
            grid_status = "FALLBACK"
        elif grid_stale:
            grid_status = "STALE"
        elif grid_quality in {"BAD", "UNCERTAIN"}:
            grid_status = grid_quality
        else:
            grid_status = "SIMULATED_REPLAY" if replay_active else ("SIMULATED" if simulated_grid else "LIVE")

        if simulated_grid:
            notes.append(
                "Grid telemetry is simulated; this snapshot is for training and replay, not live dispatch"
            )
        if replay_active:
            notes.append(
                "Weather and grid measurements follow the persisted demonstration replay cursor"
            )

        return DataQualityResponse(
            overall_status=(
                "DEGRADED"
                if (
                    stale
                    or fallback_used
                    or consensus_degraded
                    or grid_stale
                    or grid_fallback_used
                    or grid_quality != "GOOD"
                    or bool(degradation_notes)
                )
                else "GOOD"
            ),
            weather_status=weather_status,
            grid_status=grid_status,
            calibration_status="CALIBRATED" if calibration_available else "UNAVAILABLE",
            weather_source=weather.provider_name,
            grid_source=grid.source_provider,
            observed_at=weather.timestamp,
            age_seconds=age_seconds,
            is_stale=stale,
            fallback_used=fallback_used,
            grid_observed_at=grid.timestamp,
            grid_age_seconds=grid_age_seconds,
            grid_is_stale=grid_stale,
            grid_fallback_used=grid_fallback_used,
            decision_status=decision_status,
            notes=notes,
        )

    @staticmethod
    def _resolve_result(
        name: str,
        result: Any,
        previous: Any,
        notes: list[str],
        default: Any = None,
    ) -> tuple[Any, bool]:
        if not isinstance(result, BaseException):
            return result, False
        if previous is not None:
            notes.append(
                f"{name.capitalize()} unavailable; using last known good value"
            )
            return previous, True
        if default is not None:
            notes.append(f"{name.capitalize()} unavailable; no cached value exists")
            return default, True
        raise RuntimeError(f"{name.capitalize()} is unavailable") from result

    @staticmethod
    def _age_seconds(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            observed = value
        else:
            try:
                observed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - observed).total_seconds()))

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
