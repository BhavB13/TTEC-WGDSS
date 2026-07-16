from __future__ import annotations

import math
from typing import Any

from app.services.risk_probability_engine import (
    OperatingForecastPoint,
    OperatingRiskInput,
    RiskProbabilityEngine,
    risk_result_details,
)


class RecommendationEngine:
    """Transparent fallback forecast backed by the operating-risk probability model."""

    ENGINE_VERSION = "rules-operating-v2.1"
    MIN_UNCERTAINTY_MW = 15.0
    DEMAND_UNCERTAINTY_RATIO = 0.02

    def __init__(self, risk_engine: RiskProbabilityEngine | None = None) -> None:
        self.risk_engine = risk_engine or RiskProbabilityEngine()

    def unavailable(self, current_demand_mw: float, reason: str) -> dict[str, Any]:
        demand = self._safe_float(current_demand_mw) or 0.0
        return {
            "engine_version": self.ENGINE_VERSION,
            "policy_status": self.risk_engine.policy.status,
            "probability_score": 0.0,
            "risk_level": "UNAVAILABLE",
            "forecast_demand_30m": demand,
            "forecast_demand_60m": demand,
            "recommendation": "DATA UNAVAILABLE",
            "factors": [reason],
            "reason": reason,
        }

    def evaluate(
        self,
        weather: dict[str, Any],
        grid_status: dict[str, Any],
        calibration: dict[str, Any] | None = None,
        forecast_weather: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        temperature_c = self._safe_float(weather.get("temperature_c"))
        humidity_percent = self._safe_float(weather.get("humidity_percent"))
        rainfall_mm_hr = self._safe_float(weather.get("rainfall_mm_hr"))
        cloud_cover_percent = self._safe_float(weather.get("cloud_cover_percent"))
        current_demand_mw = self._safe_float(grid_status.get("current_demand_mw"))
        current_generation_mw = self._safe_float(
            grid_status.get("current_generation_mw")
        )
        available_capacity_mw = self._safe_float(
            grid_status.get("total_available_capacity_mw")
        )
        spinning_reserve_mw = self._safe_float(
            grid_status.get("spinning_reserve_mw")
        )
        spinning_reserve_source = str(
            grid_status.get("spinning_reserve_source") or ""
        )

        required_values = {
            "temperature": temperature_c,
            "humidity": humidity_percent,
            "rainfall": rainfall_mm_hr,
            "cloud cover": cloud_cover_percent,
            "current demand": current_demand_mw,
            "current generation": current_generation_mw,
            "available capacity": available_capacity_mw,
        }
        missing = [name for name, value in required_values.items() if value is None]
        if missing or current_demand_mw is None or current_demand_mw <= 0:
            return self.unavailable(
                current_demand_mw or 0.0,
                "Fallback forecast unavailable; invalid or missing " + ", ".join(missing),
            )
        if available_capacity_mw is None or available_capacity_mw <= 0:
            return self.unavailable(
                current_demand_mw,
                "Fallback forecast unavailable; available capacity must be positive",
            )

        assert temperature_c is not None
        assert humidity_percent is not None
        assert rainfall_mm_hr is not None
        assert cloud_cover_percent is not None
        assert current_generation_mw is not None
        has_reported_spin = (
            spinning_reserve_mw is not None
            and not spinning_reserve_source.startswith("DERIVED_")
        )

        scenario = self._scenario_inputs(calibration)
        future_weather = self._future_weather_inputs(
            forecast_weather,
            temperature_c,
            humidity_percent,
            rainfall_mm_hr,
            cloud_cover_percent,
        )
        forecast_demand_30m = self._forecast_demand(
            current_demand_mw=current_demand_mw,
            temperature_c=temperature_c,
            humidity_percent=humidity_percent,
            rainfall_mm_hr=rainfall_mm_hr,
            cloud_cover_percent=cloud_cover_percent,
            horizon_minutes=30,
            scenario_base_demand=scenario[0],
            scenario_followup_demand=scenario[1],
            scenario_confidence=scenario[2],
            forecast_temperature_c=future_weather[0],
            forecast_humidity_percent=future_weather[1],
            forecast_rainfall_mm_hr=future_weather[2],
            forecast_cloud_cover_percent=future_weather[3],
        )
        forecast_demand_60m = self._forecast_demand(
            current_demand_mw=current_demand_mw,
            temperature_c=temperature_c,
            humidity_percent=humidity_percent,
            rainfall_mm_hr=rainfall_mm_hr,
            cloud_cover_percent=cloud_cover_percent,
            horizon_minutes=60,
            scenario_base_demand=scenario[0],
            scenario_followup_demand=scenario[1],
            scenario_confidence=scenario[2],
            forecast_temperature_c=future_weather[0],
            forecast_humidity_percent=future_weather[1],
            forecast_rainfall_mm_hr=future_weather[2],
            forecast_cloud_cover_percent=future_weather[3],
        )
        uncertainty_mw = self._forecast_uncertainty(
            forecast_demand_mw=forecast_demand_60m,
            temperature_c=temperature_c,
            humidity_percent=humidity_percent,
            rainfall_mm_hr=rainfall_mm_hr,
            scenario_confidence=scenario[2],
            weather_confidence=future_weather[4],
        )
        risk = self.risk_engine.evaluate(
            OperatingRiskInput(
                forecast_demand_mw=forecast_demand_60m,
                forecast_uncertainty_mw=uncertainty_mw,
                current_demand_mw=current_demand_mw,
                online_capacity_mw=(
                    current_generation_mw
                    if has_reported_spin
                    else available_capacity_mw
                ),
                available_capacity_mw=available_capacity_mw,
                spinning_reserve_mw=(
                    spinning_reserve_mw if has_reported_spin else None
                ),
                forecast_profile=(
                    OperatingForecastPoint(
                        horizon_minutes=30,
                        forecast_demand_mw=forecast_demand_30m,
                        forecast_uncertainty_mw=max(
                            self.MIN_UNCERTAINTY_MW,
                            uncertainty_mw / math.sqrt(2.0),
                        ),
                        confidence=future_weather[4] or 0.5,
                    ),
                    OperatingForecastPoint(
                        horizon_minutes=60,
                        forecast_demand_mw=forecast_demand_60m,
                        forecast_uncertainty_mw=uncertainty_mw,
                        confidence=future_weather[4] or 0.5,
                    ),
                ),
                available_capacity_is_verified=False,
                data_quality_status=str(grid_status.get("quality_status", "UNKNOWN")),
            )
        )
        if risk.risk_level == "UNAVAILABLE":
            return self.unavailable(current_demand_mw, risk.reasons[0])

        factors = self._forecast_factors(
            temperature_c=temperature_c,
            humidity_percent=humidity_percent,
            rainfall_mm_hr=rainfall_mm_hr,
            cloud_cover_percent=cloud_cover_percent,
            current_demand_mw=current_demand_mw,
            current_generation_mw=current_generation_mw,
            scenario_label=scenario[3],
            scenario_base_demand=scenario[0],
            scenario_followup_demand=scenario[1],
            forecast_temperature_c=future_weather[0],
            forecast_humidity_percent=future_weather[1],
            forecast_rainfall_mm_hr=future_weather[2],
        )
        factors.extend(risk.reasons)
        factors = list(dict.fromkeys(factors))
        recommendation = self._dashboard_recommendation(risk.recommendation)
        return {
            "engine_version": self.ENGINE_VERSION,
            "policy_status": risk.policy_status,
            "probability_score": risk.probability_score,
            "risk_level": risk.risk_level,
            "forecast_demand_30m": round(forecast_demand_30m, 2),
            "forecast_demand_60m": round(forecast_demand_60m, 2),
            "recommendation": recommendation,
            "factors": factors,
            "reason": "; ".join(factors),
            **risk_result_details(risk),
        }

    @staticmethod
    def _scenario_inputs(
        calibration: dict[str, Any] | None,
    ) -> tuple[float | None, float | None, float | None, str | None]:
        if not calibration:
            return None, None, None, None
        return (
            RecommendationEngine._safe_float(calibration.get("selected_demand_mw")),
            RecommendationEngine._safe_float(
                calibration.get("selected_next_demand_mw")
            ),
            RecommendationEngine._safe_float(calibration.get("selection_confidence")),
            str(calibration.get("selected_scenario_label") or "scenario"),
        )

    @staticmethod
    def _future_weather_inputs(
        forecast_weather: dict[str, Any] | None,
        temperature_c: float,
        humidity_percent: float,
        rainfall_mm_hr: float,
        cloud_cover_percent: float,
    ) -> tuple[float, float, float, float, float | None]:
        payload = forecast_weather or {}
        return (
            RecommendationEngine._safe_float(payload.get("temperature_c"))
            or temperature_c,
            RecommendationEngine._safe_float(payload.get("humidity_percent"))
            or humidity_percent,
            RecommendationEngine._safe_float(payload.get("rainfall_mm_hr"))
            if RecommendationEngine._safe_float(payload.get("rainfall_mm_hr"))
            is not None
            else rainfall_mm_hr,
            RecommendationEngine._safe_float(payload.get("cloud_cover_percent"))
            if RecommendationEngine._safe_float(payload.get("cloud_cover_percent"))
            is not None
            else cloud_cover_percent,
            RecommendationEngine._safe_float(payload.get("confidence_score")),
        )

    @staticmethod
    def _forecast_demand(
        current_demand_mw: float,
        temperature_c: float,
        humidity_percent: float,
        rainfall_mm_hr: float,
        cloud_cover_percent: float,
        horizon_minutes: int,
        scenario_base_demand: float | None = None,
        scenario_followup_demand: float | None = None,
        scenario_confidence: float | None = None,
        forecast_temperature_c: float | None = None,
        forecast_humidity_percent: float | None = None,
        forecast_rainfall_mm_hr: float | None = None,
        forecast_cloud_cover_percent: float | None = None,
    ) -> float:
        horizon_fraction = max(0.0, min(1.0, horizon_minutes / 60.0))
        projected = current_demand_mw

        confidence = max(0.0, min(1.0, scenario_confidence or 0.0))
        if (
            scenario_base_demand is not None
            and scenario_base_demand > 0
            and scenario_followup_demand is not None
            and scenario_followup_demand >= 0
        ):
            profile_ratio = max(
                0.85,
                min(1.15, scenario_followup_demand / scenario_base_demand),
            )
            projected *= 1.0 + (profile_ratio - 1.0) * confidence * horizon_fraction

        future_temperature = (
            temperature_c
            if forecast_temperature_c is None
            else forecast_temperature_c
        )
        future_humidity = (
            humidity_percent
            if forecast_humidity_percent is None
            else forecast_humidity_percent
        )
        future_rainfall = (
            rainfall_mm_hr
            if forecast_rainfall_mm_hr is None
            else forecast_rainfall_mm_hr
        )
        future_cloud = (
            cloud_cover_percent
            if forecast_cloud_cover_percent is None
            else forecast_cloud_cover_percent
        )
        weather_ratio = (future_temperature - temperature_c) * 0.004
        weather_ratio += (future_humidity - humidity_percent) * 0.0003
        weather_ratio -= max(0.0, future_rainfall - rainfall_mm_hr) * 0.001
        weather_ratio += max(0.0, rainfall_mm_hr - future_rainfall) * 0.0005
        weather_ratio -= (future_cloud - cloud_cover_percent) * 0.00005
        if forecast_temperature_c is None and temperature_c > 30.0:
            weather_ratio += min((temperature_c - 30.0) * 0.00125, 0.00625)
        projected *= 1.0 + weather_ratio * horizon_fraction * (1.0 - confidence * 0.5)

        maximum_change = 0.10 if horizon_minutes <= 30 else 0.20
        return max(
            current_demand_mw * (1.0 - maximum_change),
            min(current_demand_mw * (1.0 + maximum_change), projected),
        )

    def _forecast_uncertainty(
        self,
        forecast_demand_mw: float,
        temperature_c: float,
        humidity_percent: float,
        rainfall_mm_hr: float,
        scenario_confidence: float | None,
        weather_confidence: float | None,
    ) -> float:
        confidence = max(0.0, min(1.0, scenario_confidence or 0.0))
        uncertainty_ratio = self.DEMAND_UNCERTAINTY_RATIO
        uncertainty_ratio += (1.0 - confidence) * 0.01
        if weather_confidence is None:
            uncertainty_ratio += 0.005
        else:
            uncertainty_ratio += (1.0 - max(0.0, min(1.0, weather_confidence))) * 0.01
        if temperature_c >= 32 or humidity_percent >= 85:
            uncertainty_ratio += 0.005
        if rainfall_mm_hr >= 8:
            uncertainty_ratio += 0.005
        return max(self.MIN_UNCERTAINTY_MW, forecast_demand_mw * uncertainty_ratio)

    @staticmethod
    def _forecast_factors(
        temperature_c: float,
        humidity_percent: float,
        rainfall_mm_hr: float,
        cloud_cover_percent: float,
        current_demand_mw: float,
        current_generation_mw: float,
        scenario_label: str | None,
        scenario_base_demand: float | None,
        scenario_followup_demand: float | None,
        forecast_temperature_c: float,
        forecast_humidity_percent: float,
        forecast_rainfall_mm_hr: float,
    ) -> list[str]:
        factors: list[str] = []
        if temperature_c > 30:
            factors.append("High temperature sustains cooling demand")
        if humidity_percent > 75:
            factors.append("High humidity sustains cooling demand")
        if rainfall_mm_hr >= 2:
            factors.append("Rainfall may reduce short-term demand")
        if cloud_cover_percent >= 80:
            factors.append("Dense cloud cover may slightly reduce short-term demand")
        if forecast_temperature_c > temperature_c + 0.5:
            factors.append("Forecast warming increases short-term cooling demand")
        elif forecast_temperature_c < temperature_c - 0.5:
            factors.append("Forecast cooling reduces short-term cooling demand")
        if forecast_humidity_percent > humidity_percent + 5:
            factors.append("Forecast humidity is rising")
        if forecast_rainfall_mm_hr > rainfall_mm_hr + 1:
            factors.append("Forecast rainfall may suppress short-term demand")
        if current_generation_mw < current_demand_mw:
            factors.append("Current generation is below measured demand")
        if (
            scenario_base_demand is not None
            and scenario_base_demand > 0
            and scenario_followup_demand is not None
        ):
            direction = (
                "rising"
                if scenario_followup_demand > scenario_base_demand
                else "falling"
                if scenario_followup_demand < scenario_base_demand
                else "steady"
            )
            factors.append(f"Imported {scenario_label or 'scenario'} load shape is {direction}")
        return factors

    @staticmethod
    def _dashboard_recommendation(recommendation: str) -> str:
        if recommendation == "PREPARE ADDITIONAL GENERATION / START ADDITIONAL TURBINE":
            return "START ADDITIONAL TURBINE"
        return recommendation

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            converted = float(value)
        except (TypeError, ValueError):
            return None
        return converted if math.isfinite(converted) else None
