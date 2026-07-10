from __future__ import annotations

import math
from dataclasses import dataclass, field


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
    engine_version: str = "operating-risk-v1"


class RiskProbabilityEngine:
    ENGINE_VERSION = "operating-risk-v1.3"

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
        z_score = (safe_online_capacity_mw - risk_input.forecast_demand_mw) / uncertainty
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
        recommendation = self._recommendation(risk_level)
        reasons = self._reasons(
            risk_input=risk_input,
            probability_score=probability_score,
            safe_online_capacity_mw=safe_online_capacity_mw,
            required_reserve_mw=required_reserve_mw,
            uncertainty=uncertainty,
            reserve_margin_percent=reserve_margin_percent,
        )

        return OperatingRiskResult(
            probability_score=probability_score,
            risk_level=risk_level,
            recommendation=recommendation,
            forecast_demand_mw=round(risk_input.forecast_demand_mw, 4),
            forecast_uncertainty_mw=round(uncertainty, 4),
            safe_online_capacity_mw=round(safe_online_capacity_mw, 4),
            required_reserve_mw=round(required_reserve_mw, 4),
            reserve_margin_mw=_round_or_none(reserve_margin_mw),
            reserve_margin_percent=_round_or_none(reserve_margin_percent),
            reasons=reasons,
            engine_version=self.ENGINE_VERSION,
        )

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
