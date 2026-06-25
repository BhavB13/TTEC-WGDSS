from __future__ import annotations

from typing import Any


class RecommendationEngine:
    """
    Rule-based probability engine for the WGDSS MVP.
    """

    def evaluate(
        self,
        weather: dict[str, Any],
        grid_status: dict[str, Any],
    ) -> dict[str, Any]:
        temperature_c = float(weather.get("temperature_c", 0.0))
        humidity_percent = float(weather.get("humidity_percent", 0.0))
        rainfall_mm_hr = float(weather.get("rainfall_mm_hr", 0.0))
        cloud_cover_percent = float(weather.get("cloud_cover_percent", 0.0))

        current_demand_mw = float(grid_status.get("current_demand_mw", 0.0))
        current_generation_mw = float(grid_status.get("current_generation_mw", 0.0))
        reserve_margin_percent = float(grid_status.get("reserve_margin_percent", 0.0))
        total_available_capacity_mw = float(grid_status.get("total_available_capacity_mw", 0.0))

        factors: list[str] = []
        score = 0.25

        if temperature_c >= 30:
            temp_boost = min((temperature_c - 29.0) * 0.05, 0.22)
            score += temp_boost
            factors.append("High temperature increased expected demand")

        if humidity_percent >= 70:
            humidity_boost = min((humidity_percent - 68.0) * 0.015, 0.18)
            score += humidity_boost
            factors.append("High humidity increased cooling load")

        if rainfall_mm_hr >= 2:
            rain_reduction = min(rainfall_mm_hr * 0.03, 0.12)
            score -= rain_reduction
            factors.append("Rainfall reduced short-term demand pressure")

        if cloud_cover_percent >= 50:
            cloud_reduction = min((cloud_cover_percent - 50.0) * 0.0015, 0.06)
            score -= cloud_reduction
            factors.append("Cloud cover slightly reduced expected load")

        demand_gap_mw = max(0.0, current_demand_mw - current_generation_mw)
        if demand_gap_mw > 0:
            demand_pressure = min(
                demand_gap_mw / max(current_generation_mw, 1.0) * 0.45,
                0.35,
            )
            score += demand_pressure
            factors.append("Demand is approaching current generation")

        if reserve_margin_percent < 30:
            reserve_pressure = min((30.0 - reserve_margin_percent) / 30.0 * 0.30, 0.30)
            score += reserve_pressure
            factors.append("Reserve margin below threshold")

        if total_available_capacity_mw and current_demand_mw > total_available_capacity_mw:
            score += 0.20
            factors.append("Demand is projected to exceed available capacity")

        probability_score = max(0.0, min(1.0, round(score, 2)))
        risk_level = self._risk_level(probability_score, reserve_margin_percent)
        forecast_demand_30m = round(
            self._forecast_demand(
                current_demand_mw,
                temperature_c,
                humidity_percent,
                rainfall_mm_hr,
                cloud_cover_percent,
                horizon_minutes=30,
            ),
            2,
        )
        forecast_demand_60m = round(
            self._forecast_demand(
                current_demand_mw,
                temperature_c,
                humidity_percent,
                rainfall_mm_hr,
                cloud_cover_percent,
                horizon_minutes=60,
            ),
            2,
        )
        recommendation = self._recommendation(probability_score, reserve_margin_percent)

        reason = "; ".join(factors) if factors else "Conditions remain within normal bounds"
        return {
            "probability_score": probability_score,
            "risk_level": risk_level,
            "forecast_demand_30m": forecast_demand_30m,
            "forecast_demand_60m": forecast_demand_60m,
            "recommendation": recommendation,
            "factors": factors,
            "reason": reason,
        }

    @staticmethod
    def _risk_level(probability_score: float, reserve_margin_percent: float) -> str:
        if probability_score >= 0.75 or reserve_margin_percent < 15:
            return "HIGH"
        if probability_score >= 0.45 or reserve_margin_percent < 25:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _recommendation(probability_score: float, reserve_margin_percent: float) -> str:
        if probability_score >= 0.75 or reserve_margin_percent < 15:
            return "START ADDITIONAL TURBINE"
        if probability_score >= 0.45:
            return "MONITOR CONDITIONS"
        return "NO ACTION REQUIRED"

    @staticmethod
    def _forecast_demand(
        current_demand_mw: float,
        temperature_c: float,
        humidity_percent: float,
        rainfall_mm_hr: float,
        cloud_cover_percent: float,
        horizon_minutes: int,
    ) -> float:
        weather_pressure = 0.0
        if temperature_c > 29:
            weather_pressure += (temperature_c - 29.0) * 4.5
        if humidity_percent > 70:
            weather_pressure += (humidity_percent - 70.0) * 0.8
        if rainfall_mm_hr >= 2:
            weather_pressure -= rainfall_mm_hr * 1.5
        if cloud_cover_percent >= 50:
            weather_pressure -= (cloud_cover_percent - 50.0) * 0.12

        horizon_modifier = 1.0 if horizon_minutes <= 30 else 1.25
        projected = current_demand_mw + weather_pressure * horizon_modifier
        floor = current_demand_mw * 0.92
        return max(floor, projected)
