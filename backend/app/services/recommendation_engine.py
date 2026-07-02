from __future__ import annotations

from typing import Any


class RecommendationEngine:
    """
    Rule-based probability engine for the WGDSS MVP.
    """

    ENGINE_VERSION = "rules-v1.1"

    def unavailable(self, current_demand_mw: float, reason: str) -> dict[str, Any]:
        return {
            "engine_version": self.ENGINE_VERSION,
            "probability_score": 0.0,
            "risk_level": "UNAVAILABLE",
            "forecast_demand_30m": current_demand_mw,
            "forecast_demand_60m": current_demand_mw,
            "recommendation": "DATA UNAVAILABLE",
            "factors": [reason],
            "reason": reason,
        }

    def evaluate(
        self,
        weather: dict[str, Any],
        grid_status: dict[str, Any],
        calibration: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        live_temperature_c = self._safe_float(weather.get("temperature_c"))
        temperature_c = live_temperature_c or 0.0
        humidity_percent = float(weather.get("humidity_percent", 0.0))
        rainfall_mm_hr = float(weather.get("rainfall_mm_hr", 0.0))
        cloud_cover_percent = float(weather.get("cloud_cover_percent", 0.0))

        selected_scenario_label = None
        selected_demand_mw = None
        selected_next_demand_mw = None
        selected_spin_mw = None
        selected_temperature_c = None
        selection_confidence = None
        if calibration:
            selected_scenario_label = calibration.get("selected_scenario_label")
            selected_demand_mw = self._safe_float(calibration.get("selected_demand_mw"))
            selected_next_demand_mw = self._safe_float(calibration.get("selected_next_demand_mw"))
            selected_spin_mw = self._safe_float(calibration.get("selected_spin_mw"))
            selected_temperature_c = self._safe_float(calibration.get("selected_temperature_c"))
            selection_confidence = self._safe_float(
                calibration.get("selection_confidence")
            )
            if (
                (live_temperature_c is None or live_temperature_c <= 0)
                and selected_temperature_c is not None
            ):
                temperature_c = selected_temperature_c

        current_demand_mw = float(grid_status.get("current_demand_mw", 0.0))
        current_generation_mw = float(grid_status.get("current_generation_mw", 0.0))
        reserve_margin_percent = float(grid_status.get("reserve_margin_percent", 0.0))
        total_available_capacity_mw = float(grid_status.get("total_available_capacity_mw", 0.0))

        factors: list[str] = []
        score = 0.25
        if (
            (live_temperature_c is None or live_temperature_c <= 0)
            and selected_temperature_c is not None
        ):
            factors.append(
                "Historical SCADA calibration supplied missing ambient temperature"
            )

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

        if selected_demand_mw is not None:
            scenario_gap = max(0.0, selected_demand_mw - current_generation_mw)
            if scenario_gap > 0:
                scenario_pressure = min(
                    (scenario_gap / max(current_generation_mw, 1.0)) * 0.22,
                    0.22,
                )
                score += scenario_pressure
                factors.append(
                    f"Imported {selected_scenario_label or 'scenario'} profile indicates higher load"
                )

        if selected_spin_mw is not None and selected_spin_mw > 0:
            spin_ratio = selected_spin_mw / max(
                selected_demand_mw or current_demand_mw,
                1.0,
            )
            spin_shortfall = max(0.0, 0.15 - spin_ratio)
            spin_pressure = min((spin_shortfall / 0.15) * 0.12, 0.12)
            if spin_pressure > 0:
                score += spin_pressure
                factors.append("Imported spinning reserve is below the 15% planning threshold")

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
                scenario_base_demand=selected_demand_mw,
                scenario_followup_demand=selected_next_demand_mw,
                scenario_confidence=selection_confidence,
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
                scenario_base_demand=selected_demand_mw,
                scenario_followup_demand=selected_next_demand_mw,
                scenario_confidence=selection_confidence,
            ),
            2,
        )
        recommendation = self._recommendation(probability_score, reserve_margin_percent)

        reason = "; ".join(factors) if factors else "Conditions remain within normal bounds"
        return {
            "engine_version": self.ENGINE_VERSION,
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
        if probability_score >= 0.45 or reserve_margin_percent < 25:
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
        scenario_base_demand: float | None = None,
        scenario_followup_demand: float | None = None,
        scenario_confidence: float | None = None,
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
        if scenario_base_demand is not None:
            scenario_anchor = scenario_base_demand
            if horizon_minutes > 30 and scenario_followup_demand is not None:
                scenario_anchor = (scenario_base_demand + scenario_followup_demand) / 2.0
            confidence = 1.0 if scenario_confidence is None else max(
                0.0,
                min(1.0, scenario_confidence),
            )
            scenario_weight = 0.5 * confidence
            projected = projected * (1.0 - scenario_weight) + scenario_anchor * scenario_weight
        floor = current_demand_mw * 0.92
        return max(floor, projected)

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
