from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import math
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.schemas.dashboard import (
    DashboardSnapshotResponse,
    ForecastBundleResponse,
    InferenceProvenanceResponse,
)
from app.schemas.data_quality import DataQualityResponse
from app.schemas.grid import GridStatusResponse
from app.schemas.probability import ProbabilityResponse
from app.schemas.recommendation import RecommendationResponse
from app.schemas.weather import CurrentWeatherResponse
from app.services.calibration_service import CalibrationService
from app.services.capacity_planning_service import (
    CapacityPlanningService,
    capacity_planning_service,
)
from app.services.demo_replay_service import DemoReplayService
from app.services.grid_service import GridService
from app.services.present_day_service import PresentDayService
from app.services.model_status_service import ModelStatusService
from app.services.recommendation_engine import RecommendationEngine
from app.services.risk_probability_engine import (
    OperatingForecastPoint,
    OperatingRiskInput,
    risk_result_details,
)
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
        capacity_plan_service: CapacityPlanningService | None = None,
        present_day_service: PresentDayService | None = None,
    ) -> None:
        self.weather_service = weather_service or WeatherService()
        self.grid_service = grid_service or GridService()
        self.recommendation_engine = recommendation_engine or RecommendationEngine()
        self.calibration_service = calibration_service or CalibrationService()
        self.model_status_service = model_status_service or ModelStatusService()
        self.persistence_service = persistence_service or SnapshotPersistenceService()
        self.capacity_plan_service = capacity_plan_service or capacity_planning_service
        self.present_day_service = (
            present_day_service or PresentDayService()
        )
        self.demo_replay_service = demo_replay_service
        if (
            self.demo_replay_service is None
            and weather_service is None
            and grid_service is None
            and settings.DEMO_REPLAY_ENABLED
        ):
            self.demo_replay_service = DemoReplayService(
                live_weather_service=self.weather_service,
            )
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
        selected_date: date | None = None,
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
        present_at = (
            replay_context["scada_status"].latest_snapshot
            if replay_context is not None
            and replay_context.get("scada_status") is not None
            and replay_context["scada_status"].latest_snapshot is not None
            else replay_context["replay"].status.cursor_at
            if replay_context is not None
            else self._parse_timestamp(grid_status.get("timestamp"))
            or datetime.now(timezone.utc)
        )
        time_context = self.present_day_service.context(
            selected_date=selected_date,
            present_at=present_at,
            present_source=(
                replay_context["replay"].status.source
                if replay_context is not None
                else str(grid_status.get("source_provider", "Runtime providers"))
            ),
        )
        previous_day_active = not time_context.is_active_day
        if previous_day_active and time_context.series:
            selected = time_context.series[-1]
            historical_weather = self.present_day_service.weather_at(
                selected.timestamp
            )
            historical_grid = {
                **grid_status,
                "timestamp": selected.timestamp,
                "current_demand_mw": selected.demand_mw or 0.0,
                "current_generation_mw": selected.generation_tra_mw or 0.0,
                "total_available_capacity_mw": selected.available_capacity_mw or 0.0,
                "spinning_reserve_mw": selected.spinning_reserve_mw,
                "spinning_reserve_source": "AspenTech OSI June replay export",
                "reserve_margin_percent": (
                    ((selected.available_capacity_mw - selected.demand_mw)
                    / selected.demand_mw * 100.0)
                    if selected.available_capacity_mw is not None
                    and selected.demand_mw not in (None, 0)
                    else 0.0
                ),
                "grid_status": (
                    "REPLAY COMPLETE"
                    if time_context.is_complete
                    else "REPLAY INCOMPLETE"
                ),
                "demand_period": selected.timestamp.strftime("%B %d, %Y"),
                "source_provider": "AspenTech OSI June replay export",
                "generation_units": [],
                "quality_status": (
                    "GOOD"
                    if selected.quality_status == "GOOD"
                    else "UNCERTAIN"
                    if selected.quality_status == "USABLE_WITH_WARNING"
                    else "BAD"
                ),
                "missing_fields": [],
            }
            grid_status = historical_grid
            weather = {
                "timestamp": selected.timestamp,
                "temperature_c": (
                    selected.temperature_c
                    if selected.temperature_c is not None
                    else historical_weather.temperature_c
                    if historical_weather is not None
                    else 0.0
                ),
                "humidity_percent": (
                    historical_weather.humidity_percent
                    if historical_weather is not None
                    else 0.0
                ),
                "rainfall_mm_hr": (
                    historical_weather.rainfall_mm_hr
                    if historical_weather is not None
                    else 0.0
                ),
                "cloud_cover_percent": (
                    historical_weather.cloud_cover_percent
                    if historical_weather is not None
                    else 0.0
                ),
                "wind_speed_kmh": (
                    historical_weather.wind_speed_kph
                    if historical_weather is not None
                    else 0.0
                ),
                "wind_direction_deg": (
                    historical_weather.wind_direction_deg
                    if historical_weather is not None
                    else None
                ),
                "pressure_hpa": (
                    historical_weather.pressure_hpa
                    if historical_weather is not None
                    else None
                ),
                "weather_condition": (
                    historical_weather.weather_condition
                    if historical_weather is not None
                    else "Historical weather unavailable"
                ),
                "heat_index_c": (
                    historical_weather.heat_index_c
                    if historical_weather is not None
                    else selected.temperature_c or 0.0
                ),
                "rain_severity": (
                    historical_weather.rain_severity
                    if historical_weather is not None
                    else "UNKNOWN"
                ),
                "provider_name": (
                    historical_weather.provider_name
                    if historical_weather is not None
                    else "Historical SCADA temperature only"
                ),
            }
            forecast = []
            replay_active = False
        calibration = self.calibration_service.get_snapshot(weather)

        calibration_payload = calibration.model_dump() if calibration is not None else None
        period_is_archived = replay_active or previous_day_active
        weather_age_seconds = (
            0 if period_is_archived else self._age_seconds(weather.get("timestamp"))
        )
        grid_age_seconds = (
            0 if period_is_archived else self._age_seconds(grid_status.get("timestamp"))
        )
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
            {"GOOD", "UNCERTAIN"} if period_is_archived else {"GOOD"}
        )
        decision_inhibited = (
            weather_is_stale
            or grid_is_stale
            or grid_quality not in acceptable_grid_quality
            or bool(grid_missing_fields)
        )
        live_model_status = (
            self.model_status_service.get_model_status()
            if replay_context is None and not previous_day_active
            else None
        )
        if decision_inhibited:
            probability_payload = self.recommendation_engine.unavailable(
                float(grid_status["current_demand_mw"]),
                "Required weather or grid telemetry is stale, incomplete, or bad; "
                "recommendation inhibited",
            )
        else:
            cached_operating_risk = (
                None
                if previous_day_active
                else self.model_status_service.get_operating_risk_payload()
            )
            probability_payload = (
                (
                    replay_context.get("risk_payload")
                    if replay_context is not None and not previous_day_active
                    else None
                )
                or cached_operating_risk
                or self.recommendation_engine.evaluate(
                    weather,
                    grid_status,
                    calibration=calibration_payload,
                    forecast_weather=self._forecast_for_horizon(
                        forecast,
                        reference_time=weather.get("timestamp"),
                        horizon_minutes=60,
                    ),
                    historical_validation_mae_mw=(
                        live_model_status.metrics.mae
                        if live_model_status is not None
                        else None
                    ),
                    historical_validation_rmse_mw=(
                        live_model_status.metrics.rmse
                        if live_model_status is not None
                        else None
                    ),
                )
            )
            probability_payload = self._anchor_capacity_risk_to_grid(
                probability_payload,
                grid_status,
            )
        weather_response = CurrentWeatherResponse.model_validate(weather)
        grid_response = GridStatusResponse.model_validate(grid_status)
        probability = ProbabilityResponse(
            engine_version=probability_payload["engine_version"],
            policy_status=probability_payload.get(
                "policy_status", settings.OPERATING_POLICY_STATUS
            ),
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
            policy_status=probability_payload.get(
                "policy_status", settings.OPERATING_POLICY_STATUS
            ),
            probability_score=probability_payload["probability_score"],
            risk_level=probability_payload["risk_level"],
            forecast_demand_30m=probability_payload["forecast_demand_30m"],
            forecast_demand_60m=probability_payload["forecast_demand_60m"],
            factors=probability_payload["factors"],
            reason=probability_payload["reason"],
            recommendation=probability_payload["recommendation"],
            **self._dispatch_evidence(probability_payload),
        )
        snapshot_id = str(uuid4())
        capacity_plan = self.capacity_plan_service.build_snapshot_plan(
            snapshot_id=snapshot_id,
            grid=grid_response,
            probability=probability,
        )
        if capacity_plan.recommended_actions:
            recommended_capacity = sum(
                action.total_capacity_mw
                for action in capacity_plan.recommended_actions
            )
            earliest_lead = min(
                action.startup_lead_time_minutes
                for action in capacity_plan.recommended_actions
            )
            recommendation = recommendation.model_copy(
                update={
                    "recommendation": "PREPARE ADDITIONAL GENERATION",
                    "decision_action": "REVIEW CAPACITY START PLAN",
                    "generator_set": "AGGREGATE START BLOCK PLAN",
                    "recommended_capacity_mw": recommended_capacity,
                    "startup_time_minutes": earliest_lead,
                    "residual_shortfall_mw": capacity_plan.unresolved_capacity_mw,
                }
            )
        if replay_context is not None and not previous_day_active:
            # Replay artifacts must match the simulated source cursor exactly.
            # Never substitute a model trained through a later historical row.
            demand_forecast = replay_context.get("demand_forecast")
            model_status = replay_context.get("model_status")
            scada_status = replay_context.get("scada_status")
        elif previous_day_active:
            demand_forecast = None
            model_status = None
            scada_status = None
        else:
            demand_forecast = self.model_status_service.get_demand_forecast_bundle()
            model_status = live_model_status
            scada_status = self.model_status_service.get_scada_status()

        snapshot = DashboardSnapshotResponse(
            snapshot_id=snapshot_id,
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
                replay_active=replay_active or previous_day_active,
                forecast_items=forecast,
            ),
            demand_forecast=demand_forecast,
            model_status=model_status,
            scada_status=scada_status,
            replay=(
                replay_context["replay"]
                if replay_context is not None and not previous_day_active
                else None
            ),
            capacity_plan=capacity_plan,
            time_context=time_context,
            inference_provenance=InferenceProvenanceResponse(
                data_mode=(
                    "HISTORICAL_REPLAY"
                    if replay_context is not None
                    else "MOCK"
                    if "mock" in grid_response.source_provider.lower()
                    else "LIVE_READ_ONLY"
                ),
                source_provider=(
                    scada_status.source_provider
                    if scada_status is not None
                    else grid_response.source_provider
                ),
                source_observation_time=(
                    scada_status.latest_snapshot
                    if scada_status is not None
                    else grid_response.timestamp
                ),
                source_available_at=(
                    scada_status.available_at
                    if scada_status is not None
                    else grid_response.timestamp
                ),
                forecast_issue_time=(
                    model_status.generated_at if model_status is not None else None
                ),
                model_version=(
                    model_status.model_version if model_status is not None else None
                ),
                artifact_hash=(
                    str(model_status.candidate_metrics.get("artifact_hash"))
                    if model_status is not None
                    and model_status.candidate_metrics.get("artifact_hash")
                    else None
                ),
                training_cutoff=(
                    model_status.training_end_at if model_status is not None else None
                ),
                status=(
                    model_status.mode if model_status is not None else "UNAVAILABLE"
                ),
            ),
        )
        if settings.SNAPSHOT_PERSISTENCE_ENABLED:
            persisted = await asyncio.to_thread(self.persistence_service.persist, snapshot)
            if not persisted:
                snapshot.data_quality.notes.append("Historical persistence unavailable")
                snapshot.data_quality.overall_status = "DEGRADED"
        return snapshot

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

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
            "risk_profile",
            "peak_risk_horizon_minutes",
            "peak_risk_timestamp",
            "forecast_lower_mw",
            "forecast_upper_mw",
            "immediate_online_capacity_mw",
            "safe_online_capacity_mw",
            "required_reserve_mw",
            "online_headroom_mw",
            "reserve_adjusted_headroom_mw",
            "severity_level",
            "urgency",
            "decision_deadline_minutes",
            "decision_deadline_at",
            "drivers",
            "increasing_factors",
            "reducing_factors",
            "quality_warnings",
            "probability_method",
            "aggregation_method",
            "capacity_basis",
            "expected_online_capacity_mw",
            "expected_available_capacity_mw",
            "expected_spinning_reserve_mw",
            "demand_ramp_mw_per_hour",
            "capacity_projection_basis",
            "capacity_risk_percent",
            "capacity_status",
            "forecast_demand_mw",
            "forecast_uncertainty_mw",
            "forecast_tra_mw",
            "projected_reserve_mw",
            "reserve_surplus_mw",
            "reserve_deficit_mw",
            "reserve_insufficient_horizon_minutes",
            "reserve_insufficient_at",
            "uncertainty_source",
            "tra_projection_basis",
            "risk_components",
            "formula_version",
        )
        return {field: payload[field] for field in fields if field in payload}

    def _anchor_capacity_risk_to_grid(
        self,
        payload: dict[str, Any],
        grid_status: dict[str, Any],
    ) -> dict[str, Any]:
        """Re-evaluate demand evidence against the TRA displayed in this snapshot."""

        if payload.get("risk_level") == "UNAVAILABLE":
            return payload
        raw_profile = payload.get("risk_profile")
        if not isinstance(raw_profile, (list, tuple)) or not raw_profile:
            return payload
        profile: list[OperatingForecastPoint] = []
        for raw in raw_profile:
            row = raw.model_dump() if hasattr(raw, "model_dump") else raw
            if not isinstance(row, dict):
                continue
            try:
                profile.append(
                    OperatingForecastPoint(
                        horizon_minutes=int(row["horizon_minutes"]),
                        forecast_demand_mw=float(row["forecast_demand_mw"]),
                        forecast_uncertainty_mw=float(
                            row["forecast_uncertainty_mw"]
                        ),
                        weather_effect_mw=float(row.get("weather_effect_mw", 0)),
                        confidence=float(row.get("forecast_confidence", 1)),
                        forecast_timestamp=self._parse_datetime(
                            row.get("forecast_timestamp")
                        ),
                        confidence_lower_mw=self._optional_float(
                            row.get("forecast_lower_mw")
                        ),
                        confidence_upper_mw=self._optional_float(
                            row.get("forecast_upper_mw")
                        ),
                        confidence_level=float(row.get("confidence_level", 0.9)),
                        uncertainty_source=str(
                            row.get("uncertainty_source")
                            or payload.get("uncertainty_source")
                            or "CALIBRATED_FORECAST_RESIDUALS"
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not profile:
            return payload

        current_demand = self._optional_float(grid_status.get("current_demand_mw"))
        current_tra = self._optional_float(grid_status.get("current_generation_mw"))
        if current_demand is None or current_tra is None:
            return payload
        available_capacity = self._optional_float(
            grid_status.get("total_available_capacity_mw")
        )
        spinning_reserve = self._optional_float(
            grid_status.get("spinning_reserve_mw")
        )
        spinning_source = str(grid_status.get("spinning_reserve_source") or "")
        result = self.recommendation_engine.risk_engine.evaluate(
            OperatingRiskInput(
                forecast_demand_mw=profile[0].forecast_demand_mw,
                forecast_uncertainty_mw=profile[0].forecast_uncertainty_mw,
                current_demand_mw=current_demand,
                online_capacity_mw=current_tra,
                available_capacity_mw=available_capacity,
                spinning_reserve_mw=(
                    None if spinning_source.startswith("DERIVED_") else spinning_reserve
                ),
                forecast_profile=tuple(profile),
                available_capacity_is_verified=(
                    available_capacity is not None
                    and available_capacity >= current_tra
                    and not bool(grid_status.get("missing_fields"))
                ),
                data_quality_status=str(grid_status.get("quality_status", "UNKNOWN")),
                data_quality_warnings=(
                    "Capacity risk was anchored to the current TRA displayed in this snapshot",
                ),
            )
        )
        factors = list(
            dict.fromkeys(
                [
                    *[str(item) for item in payload.get("factors", [])],
                    *result.reasons,
                ]
            )
        )
        return {
            **payload,
            "engine_version": result.engine_version,
            "policy_status": result.policy_status,
            "probability_score": result.probability_score,
            "risk_level": result.risk_level,
            "recommendation": result.recommendation,
            "factors": factors,
            "reason": "; ".join(factors),
            **risk_result_details(result),
        }

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if math.isfinite(parsed) else None

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
        live_forecast_mapped_to_simulation = bool(
            replay_active
            and forecast_items
            and any(
                item.get("forecast_mode")
                == "LIVE_ENSEMBLE_MAPPED_TO_SIMULATION"
                for item in forecast_items[:6]
            )
        )
        calibrated = "SCADA Calibration" in weather.provider_name
        weather_status = "STALE" if stale else ("FALLBACK" if fallback_used else "LIVE")
        if replay_active:
            weather_status = (
                "LIVE_FORECAST_SIMULATED_GRID"
                if live_forecast_mapped_to_simulation
                else "SIMULATED_REPLAY"
            )
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
            if live_forecast_mapped_to_simulation:
                notes.append(
                    "Current weather and grid measurements follow the simulation cursor; "
                    "the hourly weather forecast is a live provider ensemble mapped to "
                    "simulation time"
                )
            else:
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
