from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from statistics import NormalDist

from app.core.config import settings


@dataclass(frozen=True)
class OperatingPolicy:
    status: str
    required_reserve_mw: float
    watch_probability_threshold: float
    prepare_probability_threshold: float
    add_generation_probability_threshold: float
    fast_start_unit_capacity_mw: float
    fast_start_max_capacity_mw: float
    fast_start_lead_time_minutes: int
    heavy_start_min_capacity_mw: float
    heavy_start_max_capacity_mw: float
    heavy_start_lead_time_minutes: int

    @classmethod
    def from_settings(cls) -> "OperatingPolicy":
        return cls(
            status=settings.OPERATING_POLICY_STATUS,
            required_reserve_mw=settings.CAPACITY_RISK_REQUIRED_RESERVE_MW,
            watch_probability_threshold=(
                settings.CAPACITY_RISK_WATCH_PROBABILITY_THRESHOLD
            ),
            prepare_probability_threshold=(
                settings.CAPACITY_RISK_PREPARE_PROBABILITY_THRESHOLD
            ),
            add_generation_probability_threshold=(
                settings.CAPACITY_RISK_ADD_GENERATION_PROBABILITY_THRESHOLD
            ),
            fast_start_unit_capacity_mw=settings.FAST_START_UNIT_CAPACITY_MW,
            fast_start_max_capacity_mw=settings.FAST_START_MAX_CAPACITY_MW,
            fast_start_lead_time_minutes=settings.FAST_START_LEAD_TIME_MINUTES,
            heavy_start_min_capacity_mw=settings.HEAVY_START_MIN_CAPACITY_MW,
            heavy_start_max_capacity_mw=settings.HEAVY_START_MAX_CAPACITY_MW,
            heavy_start_lead_time_minutes=settings.HEAVY_START_LEAD_TIME_MINUTES,
        )


@dataclass(frozen=True)
class OperatingForecastPoint:
    horizon_minutes: int
    forecast_demand_mw: float
    forecast_uncertainty_mw: float | None
    weather_effect_mw: float = 0.0
    confidence: float = 1.0
    forecast_timestamp: datetime | None = None
    confidence_lower_mw: float | None = None
    confidence_upper_mw: float | None = None
    confidence_level: float = 0.90
    forecast_tra_mw: float | None = None
    tra_projection_basis: str | None = None
    uncertainty_source: str | None = None


@dataclass(frozen=True)
class OperatingRiskInput:
    forecast_demand_mw: float | None
    forecast_uncertainty_mw: float | None
    current_demand_mw: float | None
    online_capacity_mw: float | None
    available_capacity_mw: float | None
    spinning_reserve_mw: float | None
    fallback_uncertainty_mw: float | None = None
    historical_validation_mae_mw: float | None = None
    historical_validation_rmse_mw: float | None = None
    forecast_profile: tuple[OperatingForecastPoint, ...] = ()
    available_capacity_is_verified: bool = True
    data_quality_status: str = "GOOD"
    data_quality_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskDriver:
    label: str
    direction: str
    category: str


@dataclass(frozen=True)
class RiskHorizonAssessment:
    horizon_minutes: int
    forecast_timestamp: datetime | None
    probability: float
    forecast_demand_mw: float
    forecast_uncertainty_mw: float
    forecast_lower_mw: float
    forecast_upper_mw: float
    confidence_level: float
    immediate_online_capacity_mw: float
    safe_online_capacity_mw: float
    required_reserve_mw: float
    online_headroom_mw: float
    reserve_adjusted_headroom_mw: float
    expected_shortfall_mw: float
    conservative_shortfall_mw: float
    expected_load_rise_mw: float
    weather_effect_mw: float
    forecast_confidence: float
    startup_lead_time_minutes: int
    decision_deadline_minutes: int | None
    decision_deadline_at: datetime | None
    urgency: str
    expected_online_capacity_mw: float
    expected_available_capacity_mw: float | None
    expected_spinning_reserve_mw: float | None
    demand_ramp_mw_per_hour: float
    capacity_projection_basis: str
    capacity_risk_percent: float
    forecast_tra_mw: float
    projected_reserve_mw: float
    reserve_surplus_mw: float
    reserve_deficit_mw: float
    capacity_status: str
    reserve_expected_insufficient: bool
    uncertainty_source: str
    tra_projection_basis: str


@dataclass(frozen=True)
class RiskBacktestSample:
    forecast_issued_at: datetime
    target_timestamp: datetime
    predicted_probability: float
    actual_demand_mw: float
    safe_online_capacity_mw: float


@dataclass(frozen=True)
class RiskBacktestResult:
    sample_count: int
    first_target_timestamp: datetime
    last_target_timestamp: datetime
    event_rate: float
    mean_probability: float
    brier_score: float
    mean_calibration_error: float


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
    available_start_capacity_mw: float | None = None
    residual_shortfall_mw: float = 0.0
    risk_profile: tuple[RiskHorizonAssessment, ...] = ()
    peak_risk_horizon_minutes: int | None = None
    peak_risk_timestamp: datetime | None = None
    forecast_lower_mw: float = 0.0
    forecast_upper_mw: float = 0.0
    immediate_online_capacity_mw: float = 0.0
    online_headroom_mw: float = 0.0
    reserve_adjusted_headroom_mw: float = 0.0
    severity_level: str = "NONE"
    urgency: str = "ROUTINE"
    decision_deadline_minutes: int | None = None
    decision_deadline_at: datetime | None = None
    drivers: tuple[RiskDriver, ...] = ()
    increasing_factors: tuple[str, ...] = ()
    reducing_factors: tuple[str, ...] = ()
    quality_warnings: tuple[str, ...] = ()
    probability_method: str = "NORMAL_RESIDUAL_EXCEEDANCE"
    aggregation_method: str = "MAX_HORIZON_PROBABILITY"
    capacity_basis: str = "TRA_ONLY"
    expected_online_capacity_mw: float = 0.0
    expected_available_capacity_mw: float | None = None
    expected_spinning_reserve_mw: float | None = None
    demand_ramp_mw_per_hour: float = 0.0
    capacity_projection_basis: str = "CURRENT_TRA_HELD_SCENARIO_NO_DISPATCH_PLAN"
    capacity_risk_percent: float = 0.0
    forecast_tra_mw: float = 0.0
    projected_reserve_mw: float = 0.0
    reserve_surplus_mw: float = 0.0
    reserve_deficit_mw: float = 0.0
    capacity_status: str = "Unavailable"
    reserve_insufficient_horizon_minutes: int | None = None
    reserve_insufficient_at: datetime | None = None
    uncertainty_source: str = "UNAVAILABLE"
    tra_projection_basis: str = "UNAVAILABLE"
    risk_components: dict[str, float | str | bool | None] = field(default_factory=dict)
    formula_version: str = "wgdss-capacity-risk-v5"
    engine_version: str = "capacity-risk-v5"
    policy_status: str = "PROTOTYPE_UNCONFIRMED"


class RiskProbabilityEngine:
    ENGINE_VERSION = "capacity-risk-v5.0"

    def __init__(self, policy: OperatingPolicy | None = None) -> None:
        self.policy = policy or OperatingPolicy.from_settings()

    @staticmethod
    def chronological_backtest(
        samples: tuple[RiskBacktestSample, ...],
    ) -> RiskBacktestResult:
        """Score historical probabilities without allowing target-time leakage."""

        if not samples:
            raise ValueError("At least one chronological risk sample is required")
        ordered = tuple(sorted(samples, key=lambda sample: sample.target_timestamp))
        for sample in ordered:
            if sample.forecast_issued_at >= sample.target_timestamp:
                raise ValueError(
                    "Risk backtest forecasts must be issued before their target timestamp"
                )
            if not 0.0 <= sample.predicted_probability <= 1.0:
                raise ValueError("Risk backtest probabilities must be between 0 and 1")
            if (
                not _is_finite(sample.actual_demand_mw)
                or not _is_finite(sample.safe_online_capacity_mw)
            ):
                raise ValueError("Risk backtest demand and capacity values must be finite")

        events = tuple(
            1.0 if sample.actual_demand_mw > sample.safe_online_capacity_mw else 0.0
            for sample in ordered
        )
        probabilities = tuple(sample.predicted_probability for sample in ordered)
        sample_count = len(ordered)
        event_rate = sum(events) / sample_count
        mean_probability = sum(probabilities) / sample_count
        brier_score = sum(
            (probability - event) ** 2
            for probability, event in zip(probabilities, events)
        ) / sample_count
        return RiskBacktestResult(
            sample_count=sample_count,
            first_target_timestamp=ordered[0].target_timestamp,
            last_target_timestamp=ordered[-1].target_timestamp,
            event_rate=event_rate,
            mean_probability=mean_probability,
            brier_score=brier_score,
            mean_calibration_error=abs(mean_probability - event_rate),
        )

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
        fallback_uncertainty, fallback_uncertainty_source = (
            self._resolve_uncertainty(risk_input)
        )
        profile = self._profile(
            risk_input,
            fallback_uncertainty,
            fallback_uncertainty_source,
        )
        if not profile:
            return self._unavailable(
                risk_input,
                "Risk probability unavailable; forecast uncertainty is missing or invalid",
            )

        immediate_capacity_mw = risk_input.online_capacity_mw
        capacity_basis = "FORECAST_TRA_MINUS_FORECAST_DEMAND"
        assessments = [
            self._assess_point(
                point,
                current_demand_mw=risk_input.current_demand_mw,
                online_capacity_mw=risk_input.online_capacity_mw,
                available_capacity_mw=risk_input.available_capacity_mw,
                spinning_reserve_mw=risk_input.spinning_reserve_mw,
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
        assert isinstance(selected_point, OperatingForecastPoint)
        required_reserve_mw = selected["required_reserve_mw"]
        safe_online_capacity_mw = selected["safe_online_capacity_mw"]
        uncertainty = float(selected["forecast_uncertainty_mw"])
        probability_score = float(selected["probability"])
        capacity_status = str(selected["capacity_status"])

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

        risk_level = self._legacy_risk_level(capacity_status)
        dispatch = self._dispatch_decision(selected, capacity_status, risk_input)
        recommendation = dispatch["recommendation"]
        reasons = self._reasons(
            risk_input=risk_input,
            selected=selected,
            reserve_margin_percent=reserve_margin_percent,
        )
        reasons.extend([
            f"Expected load rise is {float(selected['expected_load_rise_mw']):.1f} MW in "
            f"{selected_point.horizon_minutes} minutes",
            f"Conservative reserve deficit is {float(selected['projected_shortfall_mw']):.1f} MW",
            f"Weather contributes {selected_point.weather_effect_mw:+.1f} MW to the forecast",
            f"Forecast confidence is {selected_point.confidence * 100:.0f}%",
        ])
        if dispatch["generator_set"] != "NONE":
            reasons.append(
                f"{dispatch['generator_set']} requires {dispatch['startup_time_minutes']} minutes to start"
            )
        available_start_capacity = dispatch["available_start_capacity_mw"]
        if available_start_capacity is not None:
            reasons.append(
                f"TA provides {available_start_capacity:.1f} MW above current TRA for startup"
            )
        if dispatch["residual_shortfall_mw"] > 0:
            reasons.append(
                f"Recommended start capacity leaves {dispatch['residual_shortfall_mw']:.1f} MW "
                "requiring further operator action"
            )

        drivers = self._drivers(
            risk_input=risk_input,
            selected=selected,
            reserve_margin_percent=reserve_margin_percent,
            capacity_basis=capacity_basis,
        )
        increasing_factors = tuple(
            driver.label for driver in drivers if driver.direction == "INCREASES_RISK"
        )
        reducing_factors = tuple(
            driver.label for driver in drivers if driver.direction == "REDUCES_RISK"
        )
        quality_warnings = tuple(
            driver.label for driver in drivers if driver.direction == "QUALITY_WARNING"
        )
        reasons = list(dict.fromkeys([*reasons, *(driver.label for driver in drivers)]))

        risk_profile = tuple(
            self._public_assessment(assessment) for assessment in assessments
        )
        first_insufficient = next(
            (
                assessment
                for assessment in sorted(
                    assessments,
                    key=lambda item: item["point"].horizon_minutes,
                )
                if bool(assessment["reserve_expected_insufficient"])
            ),
            None,
        )
        first_insufficient_point = (
            first_insufficient["point"] if first_insufficient is not None else None
        )
        projected_shortfall = float(selected["projected_shortfall_mw"])
        severity_level = self._severity_level(projected_shortfall)
        deadline_minutes = selected["decision_deadline_minutes"]
        deadline_at = selected["decision_deadline_at"]

        return OperatingRiskResult(
            probability_score=probability_score,
            risk_level=risk_level,
            recommendation=recommendation,
            forecast_demand_mw=selected_point.forecast_demand_mw,
            forecast_uncertainty_mw=uncertainty,
            safe_online_capacity_mw=float(safe_online_capacity_mw),
            required_reserve_mw=float(required_reserve_mw),
            reserve_margin_mw=reserve_margin_mw,
            reserve_margin_percent=reserve_margin_percent,
            reasons=reasons,
            decision_action=str(dispatch["decision_action"]),
            generator_set=str(dispatch["generator_set"]),
            recommended_capacity_mw=float(dispatch["recommended_capacity_mw"]),
            projected_shortfall_mw=projected_shortfall,
            expected_shortfall_mw=float(selected["expected_shortfall_mw"]),
            expected_load_rise_mw=float(selected["expected_load_rise_mw"]),
            expected_rise_minutes=selected_point.horizon_minutes,
            startup_time_minutes=int(dispatch["startup_time_minutes"]),
            decision_confidence=selected_point.confidence,
            weather_effect_mw=selected_point.weather_effect_mw,
            available_start_capacity_mw=(
                float(available_start_capacity)
                if available_start_capacity is not None
                else None
            ),
            residual_shortfall_mw=float(dispatch["residual_shortfall_mw"]),
            risk_profile=risk_profile,
            peak_risk_horizon_minutes=selected_point.horizon_minutes,
            peak_risk_timestamp=selected_point.forecast_timestamp,
            forecast_lower_mw=float(selected["forecast_lower_mw"]),
            forecast_upper_mw=float(selected["forecast_upper_mw"]),
            immediate_online_capacity_mw=immediate_capacity_mw,
            online_headroom_mw=float(selected["online_headroom_mw"]),
            reserve_adjusted_headroom_mw=float(
                selected["reserve_adjusted_headroom_mw"]
            ),
            severity_level=severity_level,
            urgency=str(selected["urgency"]),
            decision_deadline_minutes=(
                int(deadline_minutes) if deadline_minutes is not None else None
            ),
            decision_deadline_at=(
                deadline_at if isinstance(deadline_at, datetime) else None
            ),
            drivers=drivers,
            increasing_factors=increasing_factors,
            reducing_factors=reducing_factors,
            quality_warnings=quality_warnings,
            capacity_basis=capacity_basis,
            expected_online_capacity_mw=float(selected["expected_online_capacity_mw"]),
            expected_available_capacity_mw=(
                float(selected["expected_available_capacity_mw"])
                if selected["expected_available_capacity_mw"] is not None
                else None
            ),
            expected_spinning_reserve_mw=(
                float(selected["expected_spinning_reserve_mw"])
                if selected["expected_spinning_reserve_mw"] is not None
                else None
            ),
            demand_ramp_mw_per_hour=float(selected["demand_ramp_mw_per_hour"]),
            capacity_projection_basis=str(selected["capacity_projection_basis"]),
            capacity_risk_percent=probability_score * 100.0,
            forecast_tra_mw=float(selected["forecast_tra_mw"]),
            projected_reserve_mw=float(selected["projected_reserve_mw"]),
            reserve_surplus_mw=float(selected["reserve_surplus_mw"]),
            reserve_deficit_mw=float(selected["reserve_deficit_mw"]),
            capacity_status=capacity_status,
            reserve_insufficient_horizon_minutes=(
                first_insufficient_point.horizon_minutes
                if isinstance(first_insufficient_point, OperatingForecastPoint)
                else None
            ),
            reserve_insufficient_at=(
                first_insufficient_point.forecast_timestamp
                if isinstance(first_insufficient_point, OperatingForecastPoint)
                else None
            ),
            uncertainty_source=str(selected["uncertainty_source"]),
            tra_projection_basis=str(selected["tra_projection_basis"]),
            risk_components={
                "capacity_risk_probability": probability_score,
                "capacity_risk_percent": probability_score * 100.0,
                "forecast_uncertainty_mw": uncertainty,
                "forecast_demand_mw": selected_point.forecast_demand_mw,
                "forecast_tra_mw": float(selected["forecast_tra_mw"]),
                "projected_reserve_mw": float(selected["projected_reserve_mw"]),
                "required_reserve_mw": float(required_reserve_mw),
                "reserve_surplus_mw": float(selected["reserve_surplus_mw"]),
                "reserve_deficit_mw": float(selected["reserve_deficit_mw"]),
                "demand_ramp_mw_per_hour": float(
                    selected["demand_ramp_mw_per_hour"]
                ),
                "forecast_confidence": selected_point.confidence,
                "data_quality_status": risk_input.data_quality_status,
                "capacity_projection_basis": (
                    selected["capacity_projection_basis"]
                ),
                "uncertainty_source": selected["uncertainty_source"],
                "event_definition": (
                    "TRA_MINUS_ACTUAL_DEMAND_BELOW_"
                    f"{required_reserve_mw:g}_MW"
                ),
            },
            engine_version=self.ENGINE_VERSION,
            policy_status=self.policy.status,
        )

    @classmethod
    def _profile(
        cls,
        risk_input: OperatingRiskInput,
        fallback_uncertainty: float,
        fallback_uncertainty_source: str,
    ) -> tuple[OperatingForecastPoint, ...]:
        valid: list[OperatingForecastPoint] = []
        for point in risk_input.forecast_profile:
            uncertainty, uncertainty_source = cls._point_uncertainty(point)
            if not _is_positive_finite(uncertainty):
                uncertainty = fallback_uncertainty
                uncertainty_source = fallback_uncertainty_source
            if (
                not 0 < point.horizon_minutes <= 6 * 60
                or not _is_finite(point.forecast_demand_mw)
                or point.forecast_demand_mw < 0
                or not _is_positive_finite(uncertainty)
            ):
                continue
            confidence = (
                max(0.0, min(1.0, float(point.confidence)))
                if _is_finite(point.confidence)
                else 0.0
            )
            confidence_level = (
                float(point.confidence_level)
                if _is_finite(point.confidence_level)
                and 0 < point.confidence_level < 1
                else 0.90
            )
            valid.append(
                replace(
                    point,
                    forecast_uncertainty_mw=uncertainty,
                    confidence=confidence,
                    confidence_level=confidence_level,
                    uncertainty_source=uncertainty_source,
                )
            )
        if valid:
            return tuple(sorted(valid, key=lambda point: point.horizon_minutes))
        if (
            risk_input.forecast_demand_mw is None
            or not _is_positive_finite(fallback_uncertainty)
        ):
            return ()
        return (
            OperatingForecastPoint(
                horizon_minutes=60,
                forecast_demand_mw=risk_input.forecast_demand_mw,
                forecast_uncertainty_mw=fallback_uncertainty,
                uncertainty_source=fallback_uncertainty_source,
            ),
        )

    @staticmethod
    def _point_uncertainty(point: OperatingForecastPoint) -> tuple[float, str]:
        if _is_positive_finite(point.forecast_uncertainty_mw):
            return (
                float(point.forecast_uncertainty_mw),
                point.uncertainty_source or "CALIBRATED_FORECAST_RESIDUALS",
            )
        if (
            point.confidence_lower_mw is None
            or point.confidence_upper_mw is None
            or not _is_finite(point.confidence_lower_mw)
            or not _is_finite(point.confidence_upper_mw)
            or point.confidence_upper_mw <= point.confidence_lower_mw
            or not 0 < point.confidence_level < 1
        ):
            return 0.0, "UNAVAILABLE"
        z_value = NormalDist().inv_cdf((1.0 + point.confidence_level) / 2.0)
        return (
            (point.confidence_upper_mw - point.confidence_lower_mw)
            / (2.0 * z_value),
            "PREDICTION_INTERVAL_NORMAL_EQUIVALENT",
        )

    def _assess_point(
        self,
        point: OperatingForecastPoint,
        current_demand_mw: float,
        online_capacity_mw: float,
        available_capacity_mw: float | None,
        spinning_reserve_mw: float | None,
    ) -> dict[str, object]:
        assert point.forecast_uncertainty_mw is not None
        forecast_tra_mw = (
            float(point.forecast_tra_mw)
            if _is_positive_finite(point.forecast_tra_mw)
            else online_capacity_mw
        )
        tra_projection_basis = (
            point.tra_projection_basis
            if _is_positive_finite(point.forecast_tra_mw)
            and point.tra_projection_basis
            else "FORECAST_TRA_SUPPLIED"
            if _is_positive_finite(point.forecast_tra_mw)
            else "CURRENT_TRA_HELD_SCENARIO_NO_DISPATCH_PLAN"
        )
        required_reserve = self.policy.required_reserve_mw
        projected_reserve = forecast_tra_mw - point.forecast_demand_mw
        reserve_surplus = projected_reserve - required_reserve
        reserve_deficit = max(0.0, -reserve_surplus)
        safe_capacity = forecast_tra_mw - required_reserve
        z_score = (safe_capacity - point.forecast_demand_mw) / point.forecast_uncertainty_mw
        probability = max(0.0, min(1.0, _normal_survival(z_score)))
        capacity_status = self._capacity_status(probability)
        confidence_level = (
            point.confidence_level if 0 < point.confidence_level < 1 else 0.90
        )
        confidence_z = NormalDist().inv_cdf((1.0 + confidence_level) / 2.0)
        explicit_interval_is_valid = (
            point.confidence_lower_mw is not None
            and point.confidence_upper_mw is not None
            and _is_finite(point.confidence_lower_mw)
            and _is_finite(point.confidence_upper_mw)
            and point.confidence_lower_mw <= point.forecast_demand_mw
            and point.confidence_upper_mw >= point.forecast_demand_mw
            and point.confidence_upper_mw > point.confidence_lower_mw
        )
        forecast_lower = (
            point.confidence_lower_mw
            if explicit_interval_is_valid
            else point.forecast_demand_mw
            - confidence_z * point.forecast_uncertainty_mw
        )
        forecast_upper = (
            point.confidence_upper_mw
            if explicit_interval_is_valid
            else point.forecast_demand_mw
            + confidence_z * point.forecast_uncertainty_mw
        )
        mean_gap = point.forecast_demand_mw - safe_capacity
        standardized_gap = mean_gap / point.forecast_uncertainty_mw
        expected_shortfall = (
            point.forecast_uncertainty_mw * _normal_density(standardized_gap)
            + mean_gap * _normal_cdf(standardized_gap)
        )
        conservative_demand = forecast_upper
        conservative_shortfall = max(0.0, conservative_demand - safe_capacity)
        horizon_hours = max(point.horizon_minutes / 60.0, 1.0 / 60.0)
        demand_ramp_mw_per_hour = (
            point.forecast_demand_mw - current_demand_mw
        ) / horizon_hours
        startup_lead_time = self._startup_lead_time(conservative_shortfall)
        deadline_minutes = (
            point.horizon_minutes - startup_lead_time
            if conservative_shortfall > 0 and startup_lead_time > 0
            else None
        )
        deadline_at = (
            point.forecast_timestamp - timedelta(minutes=startup_lead_time)
            if point.forecast_timestamp is not None
            and deadline_minutes is not None
            else None
        )
        return {
            "point": point,
            "probability": probability,
            "capacity_risk_percent": probability * 100.0,
            "forecast_uncertainty_mw": point.forecast_uncertainty_mw,
            "required_reserve_mw": required_reserve,
            "safe_online_capacity_mw": safe_capacity,
            "forecast_lower_mw": max(0.0, forecast_lower),
            "forecast_upper_mw": max(0.0, forecast_upper),
            "confidence_level": confidence_level,
            "immediate_online_capacity_mw": online_capacity_mw,
            "online_headroom_mw": projected_reserve,
            "reserve_adjusted_headroom_mw": reserve_surplus,
            "forecast_tra_mw": forecast_tra_mw,
            "projected_reserve_mw": projected_reserve,
            "reserve_surplus_mw": reserve_surplus,
            "reserve_deficit_mw": reserve_deficit,
            "capacity_status": capacity_status,
            "reserve_expected_insufficient": projected_reserve <= required_reserve,
            "expected_shortfall_mw": max(0.0, expected_shortfall),
            "projected_shortfall_mw": conservative_shortfall,
            "expected_load_rise_mw": max(
                0.0,
                point.forecast_demand_mw - current_demand_mw,
            ),
            "startup_lead_time_minutes": startup_lead_time,
            "decision_deadline_minutes": deadline_minutes,
            "decision_deadline_at": deadline_at,
            "urgency": self._urgency(deadline_minutes, conservative_shortfall),
            "expected_online_capacity_mw": forecast_tra_mw,
            "expected_available_capacity_mw": available_capacity_mw,
            "expected_spinning_reserve_mw": spinning_reserve_mw,
            "demand_ramp_mw_per_hour": demand_ramp_mw_per_hour,
            "capacity_projection_basis": tra_projection_basis,
            "tra_projection_basis": tra_projection_basis,
            "uncertainty_source": (
                point.uncertainty_source or "CALIBRATED_FORECAST_RESIDUALS"
            ),
        }

    def _startup_lead_time(self, conservative_shortfall_mw: float) -> int:
        if conservative_shortfall_mw <= 0:
            return 0
        if conservative_shortfall_mw <= self.policy.fast_start_max_capacity_mw:
            return self.policy.fast_start_lead_time_minutes
        return self.policy.heavy_start_lead_time_minutes

    @staticmethod
    def _urgency(deadline_minutes: int | None, shortfall_mw: float) -> str:
        if shortfall_mw <= 0 or deadline_minutes is None:
            return "ROUTINE"
        if deadline_minutes <= 0:
            return "ACTION_DUE"
        return "LEAD_TIME_AVAILABLE"

    @staticmethod
    def _public_assessment(
        assessment: dict[str, object],
    ) -> RiskHorizonAssessment:
        point = assessment["point"]
        assert isinstance(point, OperatingForecastPoint)
        deadline_at = assessment["decision_deadline_at"]
        return RiskHorizonAssessment(
            horizon_minutes=point.horizon_minutes,
            forecast_timestamp=point.forecast_timestamp,
            probability=float(assessment["probability"]),
            forecast_demand_mw=point.forecast_demand_mw,
            forecast_uncertainty_mw=point.forecast_uncertainty_mw,
            forecast_lower_mw=float(assessment["forecast_lower_mw"]),
            forecast_upper_mw=float(assessment["forecast_upper_mw"]),
            confidence_level=float(assessment["confidence_level"]),
            immediate_online_capacity_mw=float(
                assessment["immediate_online_capacity_mw"]
            ),
            safe_online_capacity_mw=float(
                assessment["safe_online_capacity_mw"]
            ),
            required_reserve_mw=float(assessment["required_reserve_mw"]),
            online_headroom_mw=float(assessment["online_headroom_mw"]),
            reserve_adjusted_headroom_mw=float(
                assessment["reserve_adjusted_headroom_mw"]
            ),
            expected_shortfall_mw=float(assessment["expected_shortfall_mw"]),
            conservative_shortfall_mw=float(
                assessment["projected_shortfall_mw"]
            ),
            expected_load_rise_mw=float(assessment["expected_load_rise_mw"]),
            weather_effect_mw=point.weather_effect_mw,
            forecast_confidence=point.confidence,
            startup_lead_time_minutes=int(
                assessment["startup_lead_time_minutes"]
            ),
            decision_deadline_minutes=(
                int(assessment["decision_deadline_minutes"])
                if assessment["decision_deadline_minutes"] is not None
                else None
            ),
            decision_deadline_at=(
                deadline_at if isinstance(deadline_at, datetime) else None
            ),
            urgency=str(assessment["urgency"]),
            expected_online_capacity_mw=float(
                assessment["expected_online_capacity_mw"]
            ),
            expected_available_capacity_mw=(
                float(assessment["expected_available_capacity_mw"])
                if assessment["expected_available_capacity_mw"] is not None
                else None
            ),
            expected_spinning_reserve_mw=(
                float(assessment["expected_spinning_reserve_mw"])
                if assessment["expected_spinning_reserve_mw"] is not None
                else None
            ),
            demand_ramp_mw_per_hour=float(
                assessment["demand_ramp_mw_per_hour"]
            ),
            capacity_projection_basis=str(
                assessment["capacity_projection_basis"]
            ),
            capacity_risk_percent=float(assessment["capacity_risk_percent"]),
            forecast_tra_mw=float(assessment["forecast_tra_mw"]),
            projected_reserve_mw=float(assessment["projected_reserve_mw"]),
            reserve_surplus_mw=float(assessment["reserve_surplus_mw"]),
            reserve_deficit_mw=float(assessment["reserve_deficit_mw"]),
            capacity_status=str(assessment["capacity_status"]),
            reserve_expected_insufficient=bool(
                assessment["reserve_expected_insufficient"]
            ),
            uncertainty_source=str(assessment["uncertainty_source"]),
            tra_projection_basis=str(assessment["tra_projection_basis"]),
        )

    def _severity_level(self, conservative_shortfall_mw: float) -> str:
        if conservative_shortfall_mw <= 0:
            return "NONE"
        if conservative_shortfall_mw <= self.policy.fast_start_unit_capacity_mw:
            return "SMALL_UNIT"
        if conservative_shortfall_mw <= self.policy.fast_start_max_capacity_mw:
            return "FAST_START"
        if conservative_shortfall_mw <= self.policy.heavy_start_max_capacity_mw:
            return "HEAVY_START"
        return "CAPACITY_DEFICIT"

    def _drivers(
        self,
        risk_input: OperatingRiskInput,
        selected: dict[str, object],
        reserve_margin_percent: float | None,
        capacity_basis: str,
    ) -> tuple[RiskDriver, ...]:
        point = selected["point"]
        assert isinstance(point, OperatingForecastPoint)
        drivers: list[RiskDriver] = []
        reserve_headroom = float(selected["reserve_adjusted_headroom_mw"])
        safe_capacity = float(selected["safe_online_capacity_mw"])
        forecast_upper = float(selected["forecast_upper_mw"])
        required_reserve = float(selected["required_reserve_mw"])
        projected_reserve = float(selected["projected_reserve_mw"])

        if reserve_headroom < 0:
            drivers.append(
                RiskDriver(
                    label=(
                        f"Projected reserve is {projected_reserve:.1f} MW, "
                        f"{abs(reserve_headroom):.1f} MW below the "
                        f"{required_reserve:.0f} MW target"
                    ),
                    direction="INCREASES_RISK",
                    category="CAPACITY",
                )
            )
        elif forecast_upper > safe_capacity:
            drivers.append(
                RiskDriver(
                    label=(
                        "Forecast uncertainty can reduce reserve below the "
                        f"{required_reserve:.0f} MW target by "
                        f"{forecast_upper - safe_capacity:.1f} MW"
                    ),
                    direction="INCREASES_RISK",
                    category="UNCERTAINTY",
                )
            )
        else:
            drivers.append(
                RiskDriver(
                    label=(
                        f"Projected reserve is {projected_reserve:.1f} MW, "
                        f"{reserve_headroom:.1f} MW above the "
                        f"{required_reserve:.0f} MW target"
                    ),
                    direction="REDUCES_RISK",
                    category="CAPACITY",
                )
            )

        if risk_input.spinning_reserve_mw is not None:
            spin_gap = risk_input.spinning_reserve_mw - required_reserve
            drivers.append(
                RiskDriver(
                    label=(
                        f"Corrected spin is {abs(spin_gap):.1f} MW "
                        f"{'above' if spin_gap >= 0 else 'below'} the target; "
                        "it remains separate observed SCADA context"
                    ),
                    direction=(
                        "REDUCES_RISK" if spin_gap >= 0 else "INCREASES_RISK"
                    ),
                    category="RESERVE",
                )
            )
        else:
            drivers.append(
                RiskDriver(
                    label="Corrected spin is unavailable; probability uses TRA only",
                    direction="QUALITY_WARNING",
                    category="DATA_QUALITY",
                )
            )

        if point.weather_effect_mw > 0.05:
            drivers.append(
                RiskDriver(
                    label=f"Forecast weather adds {point.weather_effect_mw:.1f} MW of demand",
                    direction="INCREASES_RISK",
                    category="WEATHER",
                )
            )
        elif point.weather_effect_mw < -0.05:
            drivers.append(
                RiskDriver(
                    label=f"Forecast weather reduces demand by {abs(point.weather_effect_mw):.1f} MW",
                    direction="REDUCES_RISK",
                    category="WEATHER",
                )
            )

        if float(selected["expected_load_rise_mw"]) > 0:
            drivers.append(
                RiskDriver(
                    label=(
                        f"Demand is forecast to rise {float(selected['expected_load_rise_mw']):.1f} MW "
                        f"within {point.horizon_minutes} minutes"
                    ),
                    direction="INCREASES_RISK",
                    category="DEMAND",
                )
            )

        if reserve_margin_percent is not None and reserve_margin_percent > 0:
            drivers.append(
                RiskDriver(
                    label=f"TA margin is {reserve_margin_percent:.1f}% before startup verification",
                    direction="REDUCES_RISK",
                    category="AVAILABLE_CAPACITY",
                )
            )

        if not risk_input.available_capacity_is_verified:
            drivers.append(
                RiskDriver(
                    label="TA-to-startable-capacity mapping is not verified",
                    direction="QUALITY_WARNING",
                    category="DATA_QUALITY",
                )
            )
        if self.policy.status.upper() != "CONFIRMED":
            drivers.append(
                RiskDriver(
                    label=(
                        "Reserve target, status bands, and startup policy are "
                        f"{self.policy.status.lower().replace('_', ' ')}"
                    ),
                    direction="QUALITY_WARNING",
                    category="POLICY",
                )
            )
        if risk_input.data_quality_status.upper() not in {
            "GOOD",
            "USABLE_WITH_WARNING",
        }:
            drivers.append(
                RiskDriver(
                    label=f"Input data quality is {risk_input.data_quality_status}",
                    direction="QUALITY_WARNING",
                    category="DATA_QUALITY",
                )
            )
        drivers.extend(
            RiskDriver(
                label=warning,
                direction="QUALITY_WARNING",
                category="DATA_QUALITY",
            )
            for warning in risk_input.data_quality_warnings
            if warning
        )
        if capacity_basis == "FORECAST_TRA_MINUS_FORECAST_DEMAND":
            drivers.append(
                RiskDriver(
                    label=(
                        "Capacity risk uses forecast TRA minus forecast demand; "
                        "corrected System Spin is not redefined by this calculation"
                    ),
                    direction="CONTEXT",
                    category="METHOD",
                )
            )
        if (
            selected["tra_projection_basis"]
            == "CURRENT_TRA_HELD_SCENARIO_NO_DISPATCH_PLAN"
        ):
            drivers.append(
                RiskDriver(
                    label=(
                        "No future TRA schedule is available; current TRA is held "
                        "as an explicit scenario at each forecast horizon"
                    ),
                    direction="QUALITY_WARNING",
                    category="TRA_SCENARIO",
                )
            )
        return tuple(dict.fromkeys(drivers))

    def _dispatch_decision(
        self,
        assessment: dict[str, object],
        capacity_status: str,
        risk_input: OperatingRiskInput,
    ) -> dict[str, object]:
        point = assessment["point"]
        assert isinstance(point, OperatingForecastPoint)
        shortfall = float(assessment["projected_shortfall_mw"])
        available_start_capacity = (
            max(
                0.0,
                risk_input.available_capacity_mw - risk_input.online_capacity_mw,
            )
            if risk_input.available_capacity_mw is not None
            and risk_input.online_capacity_mw is not None
            and risk_input.available_capacity_is_verified
            else None
        )
        if capacity_status == "Normal":
            return self._dispatch_payload(
                recommendation="NO ACTION REQUIRED",
                decision_action="NO ACTION",
                available_start_capacity_mw=available_start_capacity,
                projected_shortfall_mw=shortfall,
            )
        if capacity_status == "Watch":
            return self._dispatch_payload(
                recommendation="MONITOR CONDITIONS",
                decision_action="MONITOR",
                available_start_capacity_mw=available_start_capacity,
                projected_shortfall_mw=shortfall,
            )
        if capacity_status == "Prepare Generation":
            return self._dispatch_payload(
                recommendation="PREPARE ADDITIONAL GENERATION",
                decision_action="PREPARE GENERATION",
                available_start_capacity_mw=available_start_capacity,
                projected_shortfall_mw=shortfall,
            )
        if not risk_input.available_capacity_is_verified:
            return self._dispatch_payload(
                recommendation="PREPARE ADDITIONAL GENERATION",
                decision_action="VERIFY STARTABLE CAPACITY",
                available_start_capacity_mw=None,
                projected_shortfall_mw=shortfall,
            )
        if shortfall <= self.policy.fast_start_max_capacity_mw:
            requested_capacity = (
                self.policy.fast_start_unit_capacity_mw
                if shortfall <= self.policy.fast_start_unit_capacity_mw
                else self.policy.fast_start_max_capacity_mw
            )
            startable_capacity = self._startable_capacity(
                requested_capacity,
                available_start_capacity,
                self.policy.fast_start_unit_capacity_mw,
            )
            if startable_capacity < self.policy.fast_start_unit_capacity_mw:
                return self._dispatch_payload(
                    recommendation="PREPARE ADDITIONAL GENERATION",
                    decision_action="ESCALATE CAPACITY AVAILABILITY",
                    available_start_capacity_mw=available_start_capacity,
                    projected_shortfall_mw=shortfall,
                )
            one_set = startable_capacity < self.policy.fast_start_max_capacity_mw
            generator_set = (
                f"1 x {self.policy.fast_start_unit_capacity_mw:g} MW FAST-START"
                if one_set
                else f"2 x {self.policy.fast_start_unit_capacity_mw:g} MW FAST-START"
            )
            start_now = point.horizon_minutes <= self.policy.fast_start_lead_time_minutes
            return self._dispatch_payload(
                recommendation=(
                    f"START ONE {self.policy.fast_start_unit_capacity_mw:g} MW SMALL SET"
                    if start_now and one_set
                    else f"START BOTH {self.policy.fast_start_unit_capacity_mw:g} MW SMALL SETS"
                    if start_now
                    else "PREPARE ADDITIONAL GENERATION"
                ),
                decision_action=(
                    "START ONE SMALL SET"
                    if start_now and one_set
                    else "START BOTH SMALL SETS"
                    if start_now
                    else "PREPARE SMALL-SET WINDOW"
                ),
                generator_set=generator_set,
                recommended_capacity_mw=startable_capacity,
                startup_time_minutes=self.policy.fast_start_lead_time_minutes,
                available_start_capacity_mw=available_start_capacity,
                projected_shortfall_mw=shortfall,
            )

        heavy_capacity = min(
            self.policy.heavy_start_max_capacity_mw,
            max(
                self.policy.heavy_start_min_capacity_mw,
                math.ceil(
                    shortfall / self.policy.fast_start_max_capacity_mw
                )
                * self.policy.fast_start_max_capacity_mw,
            ),
        )
        startable_heavy = self._startable_capacity(
            heavy_capacity,
            available_start_capacity,
            self.policy.fast_start_max_capacity_mw,
        )
        if startable_heavy < self.policy.heavy_start_min_capacity_mw:
            startable_small = self._startable_capacity(
                self.policy.fast_start_max_capacity_mw,
                available_start_capacity,
                self.policy.fast_start_unit_capacity_mw,
            )
            if startable_small >= self.policy.fast_start_unit_capacity_mw:
                start_now = point.horizon_minutes <= self.policy.fast_start_lead_time_minutes
                return self._dispatch_payload(
                    recommendation=(
                        f"START ONE {self.policy.fast_start_unit_capacity_mw:g} MW SMALL SET"
                        if start_now
                        and startable_small < self.policy.fast_start_max_capacity_mw
                        else f"START BOTH {self.policy.fast_start_unit_capacity_mw:g} MW SMALL SETS"
                        if start_now
                        else "PREPARE ADDITIONAL GENERATION"
                    ),
                    decision_action=(
                        "START AVAILABLE SMALL SETS AND ESCALATE"
                        if start_now
                        else "ESCALATE CAPACITY AVAILABILITY"
                    ),
                    generator_set=(
                        f"1 x {self.policy.fast_start_unit_capacity_mw:g} MW FAST-START"
                        if startable_small < self.policy.fast_start_max_capacity_mw
                        else f"2 x {self.policy.fast_start_unit_capacity_mw:g} MW FAST-START"
                    ),
                    recommended_capacity_mw=startable_small,
                    startup_time_minutes=self.policy.fast_start_lead_time_minutes,
                    available_start_capacity_mw=available_start_capacity,
                    projected_shortfall_mw=shortfall,
                )
            return self._dispatch_payload(
                recommendation="PREPARE ADDITIONAL GENERATION",
                decision_action="ESCALATE CAPACITY AVAILABILITY",
                available_start_capacity_mw=available_start_capacity,
                projected_shortfall_mw=shortfall,
            )
        start_now = point.horizon_minutes <= self.policy.heavy_start_lead_time_minutes
        return self._dispatch_payload(
            recommendation=(
                "START HEAVY GENERATOR SET"
                if start_now
                else "PREPARE ADDITIONAL GENERATION"
            ),
            decision_action=(
                "START HEAVY SET"
                if start_now
                else "PREPARE HEAVY-SET WINDOW"
            ),
            generator_set=(
                "HEAVY "
                f"{self.policy.heavy_start_min_capacity_mw:g}-"
                f"{self.policy.heavy_start_max_capacity_mw:g} MW SET"
            ),
            recommended_capacity_mw=startable_heavy,
            startup_time_minutes=self.policy.heavy_start_lead_time_minutes,
            available_start_capacity_mw=available_start_capacity,
            projected_shortfall_mw=shortfall,
        )

    @staticmethod
    def _startable_capacity(
        requested_capacity_mw: float,
        available_start_capacity_mw: float | None,
        unit_increment_mw: float,
    ) -> float:
        if available_start_capacity_mw is None:
            return requested_capacity_mw
        bounded = min(requested_capacity_mw, available_start_capacity_mw)
        return max(0.0, math.floor(bounded / unit_increment_mw) * unit_increment_mw)

    @staticmethod
    def _dispatch_payload(
        recommendation: str,
        decision_action: str,
        available_start_capacity_mw: float | None,
        projected_shortfall_mw: float,
        generator_set: str = "NONE",
        recommended_capacity_mw: float = 0.0,
        startup_time_minutes: int = 0,
    ) -> dict[str, object]:
        return {
            "recommendation": recommendation,
            "decision_action": decision_action,
            "generator_set": generator_set,
            "recommended_capacity_mw": recommended_capacity_mw,
            "startup_time_minutes": startup_time_minutes,
            "available_start_capacity_mw": available_start_capacity_mw,
            "residual_shortfall_mw": max(
                0.0,
                projected_shortfall_mw - recommended_capacity_mw,
            ),
        }

    def _invalid_fields(self, risk_input: OperatingRiskInput) -> list[str]:
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
        if not _is_positive_finite(self.policy.required_reserve_mw):
            invalid.append("positive required operating reserve target")
        if not (
            0 <= self.policy.watch_probability_threshold
            < self.policy.prepare_probability_threshold
            < self.policy.add_generation_probability_threshold
            <= 1
        ):
            invalid.append("ordered capacity-status probability thresholds between 0 and 1")
        if min(
            self.policy.fast_start_unit_capacity_mw,
            self.policy.fast_start_max_capacity_mw,
            self.policy.heavy_start_min_capacity_mw,
            self.policy.heavy_start_max_capacity_mw,
            self.policy.fast_start_lead_time_minutes,
            self.policy.heavy_start_lead_time_minutes,
        ) <= 0:
            invalid.append("positive configured generator capacities and lead times")
        if (
            self.policy.fast_start_max_capacity_mw
            < self.policy.fast_start_unit_capacity_mw
        ):
            invalid.append("fast-start maximum capacity not below unit capacity")
        if (
            self.policy.heavy_start_max_capacity_mw
            < self.policy.heavy_start_min_capacity_mw
        ):
            invalid.append("heavy-start maximum capacity not below minimum capacity")
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
    def _resolve_uncertainty(risk_input: OperatingRiskInput) -> tuple[float, str]:
        if (
            risk_input.forecast_uncertainty_mw is not None
            and _is_positive_finite(risk_input.forecast_uncertainty_mw)
        ):
            return (
                risk_input.forecast_uncertainty_mw,
                "CALIBRATED_FORECAST_RESIDUALS",
            )
        if (
            risk_input.fallback_uncertainty_mw is not None
            and _is_positive_finite(risk_input.fallback_uncertainty_mw)
        ):
            return risk_input.fallback_uncertainty_mw, "VALIDATED_FALLBACK_STD"
        if (
            risk_input.historical_validation_rmse_mw is not None
            and _is_positive_finite(risk_input.historical_validation_rmse_mw)
        ):
            return (
                risk_input.historical_validation_rmse_mw,
                "HISTORICAL_VALIDATION_RMSE_AS_SIGMA",
            )
        if (
            risk_input.historical_validation_mae_mw is not None
            and _is_positive_finite(risk_input.historical_validation_mae_mw)
        ):
            return (
                risk_input.historical_validation_mae_mw * math.sqrt(math.pi / 2.0),
                "HISTORICAL_VALIDATION_MAE_NORMAL_EQUIVALENT",
            )
        return 0.0, "UNAVAILABLE"

    def _unavailable(
        self,
        risk_input: OperatingRiskInput,
        reason: str,
    ) -> OperatingRiskResult:
        forecast_demand = _safe_nonnegative(
            risk_input.forecast_demand_mw,
            _safe_nonnegative(risk_input.current_demand_mw, 0.0),
        )
        uncertainty, uncertainty_source = self._resolve_uncertainty(risk_input)
        forecast_tra = _safe_nonnegative(risk_input.online_capacity_mw, 0.0)
        projected_reserve = forecast_tra - forecast_demand
        reserve_surplus = projected_reserve - self.policy.required_reserve_mw
        return OperatingRiskResult(
            probability_score=0.0,
            risk_level="UNAVAILABLE",
            recommendation="DATA UNAVAILABLE",
            forecast_demand_mw=forecast_demand,
            forecast_uncertainty_mw=uncertainty,
            safe_online_capacity_mw=max(
                0.0,
                forecast_tra - self.policy.required_reserve_mw,
            ),
            required_reserve_mw=self.policy.required_reserve_mw,
            reserve_margin_mw=None,
            reserve_margin_percent=None,
            reasons=[reason],
            decision_action="DATA UNAVAILABLE",
            capacity_risk_percent=0.0,
            forecast_tra_mw=forecast_tra,
            projected_reserve_mw=projected_reserve,
            reserve_surplus_mw=reserve_surplus,
            reserve_deficit_mw=max(0.0, -reserve_surplus),
            capacity_status="Unavailable",
            uncertainty_source=uncertainty_source,
            tra_projection_basis="CURRENT_TRA_HELD_SCENARIO_NO_DISPATCH_PLAN",
            engine_version=self.ENGINE_VERSION,
            policy_status=self.policy.status,
        )

    def _capacity_status(self, probability_score: float) -> str:
        # Stabilize exact policy-boundary comparisons against harmless floating
        # point noise from the normal CDF while preserving the raw probability.
        status_score = round(probability_score, 12)
        if status_score >= self.policy.add_generation_probability_threshold:
            return "Add Generation"
        if status_score >= self.policy.prepare_probability_threshold:
            return "Prepare Generation"
        if status_score >= self.policy.watch_probability_threshold:
            return "Watch"
        return "Normal"

    @staticmethod
    def _legacy_risk_level(capacity_status: str) -> str:
        if capacity_status in {"Prepare Generation", "Add Generation"}:
            return "HIGH"
        if capacity_status == "Watch":
            return "MEDIUM"
        if capacity_status == "Normal":
            return "LOW"
        return "UNAVAILABLE"

    @staticmethod
    def _reasons(
        risk_input: OperatingRiskInput,
        selected: dict[str, object],
        reserve_margin_percent: float | None,
    ) -> list[str]:
        point = selected["point"]
        assert isinstance(point, OperatingForecastPoint)
        probability_score = float(selected["probability"])
        required_reserve_mw = float(selected["required_reserve_mw"])
        projected_reserve_mw = float(selected["projected_reserve_mw"])
        reserve_surplus_mw = float(selected["reserve_surplus_mw"])
        safe_online_capacity_mw = float(selected["safe_online_capacity_mw"])
        uncertainty = float(selected["forecast_uncertainty_mw"])
        reasons: list[str] = []
        if reserve_surplus_mw < 0:
            reasons.append(
                f"Projected reserve is {projected_reserve_mw:.1f} MW, "
                f"{abs(reserve_surplus_mw):.1f} MW below the "
                f"{required_reserve_mw:.0f} MW target"
            )
        else:
            reasons.append(
                f"Projected reserve is {projected_reserve_mw:.1f} MW, "
                f"{reserve_surplus_mw:.1f} MW above the "
                f"{required_reserve_mw:.0f} MW target"
            )

        margin_to_safe_capacity = safe_online_capacity_mw - point.forecast_demand_mw
        if (
            margin_to_safe_capacity >= 0
            and margin_to_safe_capacity < uncertainty * 1.6448536269514722
        ):
            reasons.append(
                "Forecast uncertainty overlaps the 30 MW projected-reserve boundary"
            )

        if risk_input.spinning_reserve_mw is not None:
            reasons.append(
                f"Current corrected System Spin is {risk_input.spinning_reserve_mw:.1f} MW; "
                "it is retained as observed context and is not redefined as TRA minus demand"
            )

        if risk_input.available_capacity_mw is not None:
            safe_available_capacity = (
                risk_input.available_capacity_mw - required_reserve_mw
            )
            if point.forecast_demand_mw > safe_available_capacity:
                reasons.append(
                    "Forecast demand exceeds available capacity after reserve requirement"
                )
            else:
                reasons.append(
                    "TA could satisfy forecast demand and reserve after verified startup; "
                    "it is not counted as immediate online capacity"
                )

        if reserve_margin_percent is not None:
            reasons.append(
                f"TA headroom relative to current demand is {reserve_margin_percent:.1f}%"
            )

        reasons.append(
            f"Demand uncertainty sigma is {uncertainty:.1f} MW from "
            f"{str(selected['uncertainty_source']).lower().replace('_', ' ')}"
        )
        if selected["tra_projection_basis"] == "CURRENT_TRA_HELD_SCENARIO_NO_DISPATCH_PLAN":
            reasons.append(
                "Current TRA is held across the horizon because no future dispatch schedule is available"
            )
        reasons.append(
            "Probability that TRA minus actual demand falls below "
            f"{required_reserve_mw:.0f} MW is "
            f"{_format_probability_percent(probability_score)}"
        )
        return reasons


def risk_result_details(result: OperatingRiskResult) -> dict[str, object]:
    """Serialize the unrounded evidence shared by API-producing services."""

    payload = asdict(result)
    summary_fields = {
        "probability_score",
        "risk_level",
        "recommendation",
        "reserve_margin_mw",
        "reserve_margin_percent",
        "reasons",
        "engine_version",
        "policy_status",
    }
    return {key: value for key, value in payload.items() if key not in summary_fields}


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_density(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


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


def _is_finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _is_positive_finite(value: float) -> bool:
    return _is_finite(value) and value > 0


def _safe_nonnegative(value: float | None, fallback: float) -> float:
    if value is None or not _is_finite(value) or value < 0:
        return fallback
    return float(value)
