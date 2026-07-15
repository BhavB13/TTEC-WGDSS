from __future__ import annotations

import math
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class OperatingForecastPoint:
    horizon_minutes: int
    forecast_demand_mw: float
    forecast_uncertainty_mw: float
    weather_effect_mw: float = 0.0
    confidence: float = 1.0


@dataclass(frozen=True)
class OperatingRiskInput:
    forecast_demand_mw: float | None
    forecast_uncertainty_mw: float | None
    current_demand_mw: float | None
    online_capacity_mw: float | None
    available_capacity_mw: float | None
    spinning_reserve_mw: float | None
    reserve_margin_threshold: float = 0.15
    fallback_uncertainty_mw: float | None = None
    forecast_profile: tuple[OperatingForecastPoint, ...] = ()


@dataclass(frozen=True)
class OperatingRiskResult:
    probability_score: float
    risk_level: str
    recommendation: str
    forecast_demand_mw: float
    forecast_uncertainty_mw: float
    safe_online_capacity_mw: float
    required_reserve_mw: float
    reserve_margin_mw: float | None
    reserve_margin_percent: float | None
    reasons: list[str] = field(default_factory=list)
    decision_action: str = "NO ACTION"
    generator_set: str = "NONE"
    recommended_capacity_mw: float = 0.0
    projected_shortfall_mw: float = 0.0
    expected_shortfall_mw: float = 0.0
    expected_load_rise_mw: float = 0.0
    expected_rise_minutes: int = 0
    startup_time_minutes: int = 0
    decision_confidence: float = 0.0
    weather_effect_mw: float = 0.0
    engine_version: str = "operating-risk-v2"


class RiskProbabilityEngine:
    ENGINE_VERSION = "operating-risk-v2.0"
    SMALL_SET_CAPACITY_MW = 30.0
    SMALL_SET_STARTUP_MINUTES = 20
    HEAVY_SET_MIN_CAPACITY_MW = 60.0
    HEAVY_SET_MAX_CAPACITY_MW = 120.0
    HEAVY_SET_STARTUP_MINUTES = 60
    CONSERVATIVE_Z = 1.2815515655446004  # 90th percentile

    def evaluate(self, risk_input: OperatingRiskInput) -> OperatingRiskResult:
        missing = self._invalid_fields(risk_input)
        if missing:
            return self._unavailable(
                risk_input,
                f"Risk probability unavailable; invalid or missing {', '.join(missing)}",
            )

        assert risk_input.forecast_demand_mw is not None
        assert risk_input.current_demand_mw is not None
        assert risk_input.online_capacity_mw is not None

        uncertainty = self._resolve_uncertainty(risk_input)
        if not _is_positive_finite(uncertainty):
            return self._unavailable(
                risk_input,
                "Risk probability unavailable; forecast uncertainty is missing or invalid",
            )

        required_reserve_mw = max(
            0.0,
            max(risk_input.current_demand_mw, risk_input.forecast_demand_mw)
            * risk_input.reserve_margin_threshold,
        )
        immediate_capacity_mw = risk_input.online_capacity_mw
        if risk_input.spinning_reserve_mw is not None:
            synchronized_capacity_mw = (
                risk_input.current_demand_mw + risk_input.spinning_reserve_mw
            )
            immediate_capacity_mw = min(
                immediate_capacity_mw,
                synchronized_capacity_mw,
            )
        safe_online_capacity_mw = immediate_capacity_mw - required_reserve_mw
        profile = self._profile(risk_input, uncertainty)
        assessments = [
            self._assess_point(
                point,
                current_demand_mw=risk_input.current_demand_mw,
                immediate_capacity_mw=immediate_capacity_mw,
                reserve_margin_threshold=risk_input.reserve_margin_threshold,
            )
            for point in profile
        ]
        selected = max(
            assessments,
            key=lambda item: (
                item["probability"],
                item["projected_shortfall_mw"],
                -item["point"].horizon_minutes,
            ),
        )
        selected_point = selected["point"]
        required_reserve_mw = selected["required_reserve_mw"]
        safe_online_capacity_mw = selected["safe_online_capacity_mw"]
        uncertainty = selected_point.forecast_uncertainty_mw
        z_score = (
            safe_online_capacity_mw - selected_point.forecast_demand_mw
        ) / uncertainty
        # Use erfc for the upper normal tail.  Subtracting a CDF close to one
        # loses meaningful low-risk precision and previously made valid values
        # appear as 0.00 after rounding.
        probability = _normal_survival(z_score)
        probability_score = max(0.0, min(1.0, probability))

        available_capacity = risk_input.available_capacity_mw
        reserve_margin_mw = (
            available_capacity - risk_input.current_demand_mw
            if available_capacity is not None
            else None
        )
        reserve_margin_percent = (
            reserve_margin_mw / risk_input.current_demand_mw * 100.0
            if reserve_margin_mw is not None and risk_input.current_demand_mw > 0
            else None
        )

        risk_level = self._risk_level(probability_score)
        dispatch = self._dispatch_decision(selected, risk_level)
        recommendation = dispatch["recommendation"]
        selected_input = replace(
            risk_input,
            forecast_demand_mw=selected_point.forecast_demand_mw,
            forecast_uncertainty_mw=selected_point.forecast_uncertainty_mw,
        )
        reasons = self._reasons(
            risk_input=selected_input,
            probability_score=probability_score,
            safe_online_capacity_mw=safe_online_capacity_mw,
            required_reserve_mw=required_reserve_mw,
            uncertainty=uncertainty,
            reserve_margin_percent=reserve_margin_percent,
        )
        reasons.extend(
            [
                f"Expected load rise is {selected['expected_load_rise_mw']:.1f} MW in "
                f"{selected_point.horizon_minutes} minutes",
                f"Conservative capacity shortfall is {selected['projected_shortfall_mw']:.1f} MW",
                f"Weather contributes {selected_point.weather_effect_mw:+.1f} MW to the forecast",
                f"Dispatch decision confidence is {selected_point.confidence * 100:.0f}%",
            ]
        )
        if dispatch["generator_set"] != "NONE":
            reasons.append(
                f"{dispatch['generator_set']} requires {dispatch['startup_time_minutes']} minutes to start"
            )

        return OperatingRiskResult(
            probability_score=probability_score,
            risk_level=risk_level,
            recommendation=recommendation,
            forecast_demand_mw=round(selected_point.forecast_demand_mw, 4),
            forecast_uncertainty_mw=round(uncertainty, 4),
            safe_online_capacity_mw=round(safe_online_capacity_mw, 4),
            required_reserve_mw=round(required_reserve_mw, 4),
            reserve_margin_mw=_round_or_none(reserve_margin_mw),
            reserve_margin_percent=_round_or_none(reserve_margin_percent),
            reasons=reasons,
            decision_action=dispatch["decision_action"],
            generator_set=dispatch["generator_set"],
            recommended_capacity_mw=dispatch["recommended_capacity_mw"],
            projected_shortfall_mw=round(selected["projected_shortfall_mw"], 2),
            expected_shortfall_mw=round(selected["expected_shortfall_mw"], 2),
            expected_load_rise_mw=round(selected["expected_load_rise_mw"], 2),
            expected_rise_minutes=selected_point.horizon_minutes,
            startup_time_minutes=dispatch["startup_time_minutes"],
            decision_confidence=round(selected_point.confidence, 2),
            weather_effect_mw=round(selected_point.weather_effect_mw, 2),
            engine_version=self.ENGINE_VERSION,
        )

    @staticmethod
    def _profile(
        risk_input: OperatingRiskInput,
        fallback_uncertainty: float,
    ) -> tuple[OperatingForecastPoint, ...]:
        valid = tuple(
            point
            for point in risk_input.forecast_profile
            if point.horizon_minutes > 0
            and _is_finite(point.forecast_demand_mw)
            and point.forecast_demand_mw >= 0
            and _is_positive_finite(point.forecast_uncertainty_mw)
        )
        if valid:
            return tuple(sorted(valid, key=lambda point: point.horizon_minutes))
        assert risk_input.forecast_demand_mw is not None
        return (
            OperatingForecastPoint(
                horizon_minutes=60,
                forecast_demand_mw=risk_input.forecast_demand_mw,
                forecast_uncertainty_mw=fallback_uncertainty,
            ),
        )

    def _assess_point(
        self,
        point: OperatingForecastPoint,
        current_demand_mw: float,
        immediate_capacity_mw: float,
        reserve_margin_threshold: float,
    ) -> dict[str, object]:
        required_reserve = max(current_demand_mw, point.forecast_demand_mw) * reserve_margin_threshold
        safe_capacity = immediate_capacity_mw - required_reserve
        z_score = (safe_capacity - point.forecast_demand_mw) / point.forecast_uncertainty_mw
        probability = max(0.0, min(1.0, _normal_survival(z_score)))
        expected_shortfall = max(0.0, point.forecast_demand_mw - safe_capacity)
        conservative_demand = (
            point.forecast_demand_mw
            + self.CONSERVATIVE_Z * point.forecast_uncertainty_mw
        )
        return {
            "point": point,
            "probability": probability,
            "required_reserve_mw": required_reserve,
            "safe_online_capacity_mw": safe_capacity,
            "expected_shortfall_mw": expected_shortfall,
            "projected_shortfall_mw": max(0.0, conservative_demand - safe_capacity),
            "expected_load_rise_mw": max(
                0.0,
                point.forecast_demand_mw - current_demand_mw,
            ),
        }

    def _dispatch_decision(
        self,
        assessment: dict[str, object],
        risk_level: str,
    ) -> dict[str, object]:
        point = assessment["point"]
        assert isinstance(point, OperatingForecastPoint)
        shortfall = float(assessment["projected_shortfall_mw"])
        if risk_level == "LOW" or shortfall <= 0:
            return {
                "recommendation": "NO ACTION REQUIRED",
                "decision_action": "NO ACTION",
                "generator_set": "NONE",
                "recommended_capacity_mw": 0.0,
                "startup_time_minutes": 0,
            }
        if risk_level == "MEDIUM":
            return {
                "recommendation": "MONITOR CONDITIONS",
                "decision_action": "MONITOR",
                "generator_set": "NONE",
                "recommended_capacity_mw": 0.0,
                "startup_time_minutes": 0,
            }
        if shortfall <= self.SMALL_SET_CAPACITY_MW:
            if point.horizon_minutes <= self.SMALL_SET_STARTUP_MINUTES:
                return {
                    "recommendation": "START SMALL GENERATOR SET",
                    "decision_action": "START SMALL SET",
                    "generator_set": "2 x 15 MW FAST-START",
                    "recommended_capacity_mw": self.SMALL_SET_CAPACITY_MW,
                    "startup_time_minutes": self.SMALL_SET_STARTUP_MINUTES,
                }
            return {
                "recommendation": "MONITOR CONDITIONS",
                "decision_action": "MONITOR SMALL-SET WINDOW",
                "generator_set": "2 x 15 MW FAST-START",
                "recommended_capacity_mw": self.SMALL_SET_CAPACITY_MW,
                "startup_time_minutes": self.SMALL_SET_STARTUP_MINUTES,
            }

        heavy_capacity = min(
            self.HEAVY_SET_MAX_CAPACITY_MW,
            max(
                self.HEAVY_SET_MIN_CAPACITY_MW,
                math.ceil(shortfall / 30.0) * 30.0,
            ),
        )
        if point.horizon_minutes <= self.HEAVY_SET_STARTUP_MINUTES:
            return {
                "recommendation": "START HEAVY GENERATOR SET",
                "decision_action": "START HEAVY SET",
                "generator_set": "HEAVY 60-120 MW SET",
                "recommended_capacity_mw": heavy_capacity,
                "startup_time_minutes": self.HEAVY_SET_STARTUP_MINUTES,
            }
        return {
            "recommendation": "MONITOR CONDITIONS",
            "decision_action": "MONITOR HEAVY-SET WINDOW",
            "generator_set": "HEAVY 60-120 MW SET",
            "recommended_capacity_mw": heavy_capacity,
            "startup_time_minutes": self.HEAVY_SET_STARTUP_MINUTES,
        }

    @staticmethod
    def _invalid_fields(risk_input: OperatingRiskInput) -> list[str]:
        required = {
            "forecast_demand_mw": risk_input.forecast_demand_mw,
            "current_demand_mw": risk_input.current_demand_mw,
            "online_capacity_mw": risk_input.online_capacity_mw,
        }
        invalid = [
            name
            for name, value in required.items()
            if value is None or not _is_finite(value)
        ]
        if risk_input.forecast_demand_mw is not None and (
            not _is_finite(risk_input.forecast_demand_mw)
            or risk_input.forecast_demand_mw < 0
        ):
            invalid.append("nonnegative forecast_demand_mw")
        if risk_input.current_demand_mw is not None and (
            not _is_finite(risk_input.current_demand_mw)
            or risk_input.current_demand_mw <= 0
        ):
            invalid.append("positive current_demand_mw")
        if risk_input.online_capacity_mw is not None and (
            not _is_finite(risk_input.online_capacity_mw)
            or risk_input.online_capacity_mw <= 0
        ):
            invalid.append("positive online_capacity_mw")
        if risk_input.available_capacity_mw is not None and (
            not _is_finite(risk_input.available_capacity_mw)
            or risk_input.available_capacity_mw < 0
        ):
            invalid.append("nonnegative available_capacity_mw")
        if risk_input.spinning_reserve_mw is not None and (
            not _is_finite(risk_input.spinning_reserve_mw)
            or risk_input.spinning_reserve_mw < 0
        ):
            invalid.append("nonnegative spinning_reserve_mw")
        if not _is_finite(risk_input.reserve_margin_threshold) or not (
            0 <= risk_input.reserve_margin_threshold <= 1
        ):
            invalid.append("reserve_margin_threshold between 0 and 1")
        if (
            risk_input.current_demand_mw is not None
            and risk_input.online_capacity_mw is not None
            and _is_finite(risk_input.current_demand_mw)
            and _is_finite(risk_input.online_capacity_mw)
            and risk_input.current_demand_mw > risk_input.online_capacity_mw
        ):
            invalid.append("current_demand_mw not above online_capacity_mw")
        if (
            risk_input.available_capacity_mw is not None
            and risk_input.online_capacity_mw is not None
            and _is_finite(risk_input.available_capacity_mw)
            and _is_finite(risk_input.online_capacity_mw)
            and risk_input.available_capacity_mw < risk_input.online_capacity_mw
        ):
            invalid.append("available_capacity_mw not below online_capacity_mw")
        return list(dict.fromkeys(invalid))

    @staticmethod
    def _resolve_uncertainty(risk_input: OperatingRiskInput) -> float:
        if (
            risk_input.forecast_uncertainty_mw is not None
            and _is_positive_finite(risk_input.forecast_uncertainty_mw)
        ):
            return risk_input.forecast_uncertainty_mw
        if (
            risk_input.fallback_uncertainty_mw is not None
            and _is_positive_finite(risk_input.fallback_uncertainty_mw)
        ):
            return risk_input.fallback_uncertainty_mw
        return 0.0

    def _unavailable(
        self,
        risk_input: OperatingRiskInput,
        reason: str,
    ) -> OperatingRiskResult:
        forecast_demand = _safe_nonnegative(
            risk_input.forecast_demand_mw,
            _safe_nonnegative(risk_input.current_demand_mw, 0.0),
        )
        uncertainty = self._resolve_uncertainty(risk_input)
        return OperatingRiskResult(
            probability_score=0.0,
            risk_level="UNAVAILABLE",
            recommendation="DATA UNAVAILABLE",
            forecast_demand_mw=round(forecast_demand, 4),
            forecast_uncertainty_mw=round(uncertainty, 4),
            safe_online_capacity_mw=0.0,
            required_reserve_mw=0.0,
            reserve_margin_mw=None,
            reserve_margin_percent=None,
            reasons=[reason],
            decision_action="DATA UNAVAILABLE",
            engine_version=self.ENGINE_VERSION,
        )

    @staticmethod
    def _risk_level(probability_score: float) -> str:
        if probability_score > 0.65:
            return "HIGH"
        if probability_score >= 0.30:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _recommendation(risk_level: str) -> str:
        if risk_level == "HIGH":
            return "PREPARE ADDITIONAL GENERATION / START ADDITIONAL TURBINE"
        if risk_level == "MEDIUM":
            return "MONITOR CONDITIONS"
        if risk_level == "LOW":
            return "NO ACTION REQUIRED"
        return "DATA UNAVAILABLE"

    @staticmethod
    def _reasons(
        risk_input: OperatingRiskInput,
        probability_score: float,
        safe_online_capacity_mw: float,
        required_reserve_mw: float,
        uncertainty: float,
        reserve_margin_percent: float | None,
    ) -> list[str]:
        assert risk_input.forecast_demand_mw is not None
        reasons: list[str] = []
        if risk_input.forecast_demand_mw > safe_online_capacity_mw:
            reasons.append("Forecast demand exceeds safe online capacity")
        else:
            reasons.append("Forecast demand remains within safe online capacity")

        margin_to_safe_capacity = safe_online_capacity_mw - risk_input.forecast_demand_mw
        if margin_to_safe_capacity < uncertainty:
            reasons.append("Forecast uncertainty overlaps the operating reserve boundary")

        if risk_input.spinning_reserve_mw is not None:
            if risk_input.spinning_reserve_mw < required_reserve_mw:
                reasons.append("Spinning reserve is below the planning threshold")
            else:
                reasons.append("Spinning reserve satisfies the planning threshold")
            synchronized_capacity = (
                risk_input.current_demand_mw + risk_input.spinning_reserve_mw
                if risk_input.current_demand_mw is not None
                else None
            )
            if (
                synchronized_capacity is not None
                and synchronized_capacity < risk_input.online_capacity_mw
            ):
                reasons.append(
                    "Immediate operating capacity is constrained by spinning reserve"
                )

        if risk_input.available_capacity_mw is not None:
            safe_available_capacity = (
                risk_input.available_capacity_mw - required_reserve_mw
            )
            if risk_input.forecast_demand_mw > safe_available_capacity:
                reasons.append(
                    "Forecast demand exceeds available capacity after reserve requirement"
                )
            else:
                reasons.append(
                    "Available capacity can satisfy forecast demand and reserve requirement"
                )

        if reserve_margin_percent is not None:
            reasons.append(f"Available reserve margin is {reserve_margin_percent:.1f}%")

        reasons.append(
            f"Safe online headroom is {margin_to_safe_capacity:.1f} MW against "
            f"+/- {uncertainty:.1f} MW forecast uncertainty"
        )
        reasons.append(
            f"Operating-risk probability is {_format_probability_percent(probability_score)}"
        )
        return reasons


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_survival(value: float) -> float:
    """Return P(Z > value) without cancellation in the upper tail."""
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def _format_probability_percent(probability: float) -> str:
    percent = probability * 100.0
    if percent == 0.0:
        return "0.000%"
    if percent < 0.001:
        return "below 0.001%"
    if percent < 0.01:
        return f"{percent:.3f}%"
    if percent < 1.0:
        return f"{percent:.2f}%"
    return f"{percent:.1f}%"


def _is_finite(value: float) -> bool:
    return math.isfinite(float(value))


def _is_positive_finite(value: float) -> bool:
    return _is_finite(value) and value > 0


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _safe_nonnegative(value: float | None, fallback: float) -> float:
    if value is None or not _is_finite(value) or value < 0:
        return fallback
    return float(value)
