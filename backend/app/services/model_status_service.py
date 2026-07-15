from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database.session import SessionLocal
from app.core.config import settings
from app.models.demand_forecast import DemandForecastResult
from app.models.scada import ScadaGridSnapshot
from app.schemas.model_status import (
    BaselineComparisonResponse,
    DemandForecastBundleResponse,
    DemandForecastHorizonResponse,
    ModelMetricsResponse,
    ModelStatusResponse,
    ScadaStatusResponse,
)
from app.services.risk_probability_engine import (
    OperatingForecastPoint,
    OperatingRiskInput,
    RiskProbabilityEngine,
)


class ModelStatusService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def get_demand_forecast_bundle(self) -> DemandForecastBundleResponse | None:
        try:
            with self.session_factory() as session:
                rows = list(
                    session.scalars(
                        select(DemandForecastResult).order_by(
                            DemandForecastResult.horizon_hours,
                            DemandForecastResult.generated_at.desc(),
                        )
                    )
                )
        except SQLAlchemyError:
            return None

        latest_by_horizon: dict[int, DemandForecastResult] = {}
        newest_generated_at = max(_as_utc(row.generated_at) for row in rows)
        for row in rows:
            if _as_utc(row.generated_at) != newest_generated_at:
                continue
            latest_by_horizon.setdefault(row.horizon_hours, row)

        if not latest_by_horizon:
            return None

        return DemandForecastBundleResponse(
            horizons=[
                DemandForecastHorizonResponse(
                    horizon_hours=row.horizon_hours,
                    forecast_timestamp=row.forecast_timestamp,
                    forecast_demand_mw=row.forecast_demand_mw,
                    forecast_uncertainty_mw=row.forecast_uncertainty_mw,
                    model_name=row.model_name,
                    model_version=row.model_version,
                    baseline_name=row.baseline_name,
                    baseline_forecast_mw=row.baseline_forecast_mw,
                    quality_status=row.quality_status,
                    feature_timestamp=(
                        row.forecast_timestamp
                        - _horizon_delta(row.horizon_hours)
                    ),
                    generated_at=row.generated_at,
                    feature_profile=row.feature_profile,
                    validation_status=row.validation_status,
                    training_rows=row.train_row_count + row.test_row_count,
                )
                for row in latest_by_horizon.values()
            ]
        )

    def get_model_status(self) -> ModelStatusResponse | None:
        try:
            with self.session_factory() as session:
                latest = session.scalar(
                    select(DemandForecastResult).order_by(
                        DemandForecastResult.generated_at.desc(),
                        DemandForecastResult.horizon_hours,
                    )
                )
        except SQLAlchemyError:
            return None

        if latest is None:
            return None

        return ModelStatusResponse(
            active_model=latest.model_name,
            model_version=latest.model_version,
            mode=latest.quality_status,
            trained_through=(
                latest.forecast_timestamp
                - _horizon_delta(latest.horizon_hours)
            ),
            generated_at=latest.generated_at,
            feature_profile=latest.feature_profile,
            validation_status=latest.validation_status,
            training_span_hours=latest.training_span_hours,
            train_row_count=latest.train_row_count,
            test_row_count=latest.test_row_count,
            candidate_metrics=_json_object(latest.candidate_metrics),
            metrics=ModelMetricsResponse(
                mae=latest.mae,
                rmse=latest.rmse,
                mape=latest.mape,
                residual_std=latest.residual_std,
            ),
            baseline_comparison=BaselineComparisonResponse(
                best_baseline=latest.baseline_name,
                ml_beats_baseline=latest.ml_beats_baseline,
            ),
        )

    def get_scada_status(self) -> ScadaStatusResponse | None:
        latest = self.get_latest_scada_snapshot()

        if latest is None:
            return None

        return ScadaStatusResponse(
            source=latest.source,
            latest_snapshot=latest.timestamp,
            available_at=latest.available_at or latest.timestamp,
            quality_status=latest.quality_status,
            missing_fields=latest.missing_fields,
        )

    def get_operating_risk_payload(
        self,
        reference_time: datetime | None = None,
    ) -> dict[str, object] | None:
        try:
            with self.session_factory() as session:
                forecasts = list(
                    session.scalars(
                        select(DemandForecastResult).order_by(
                            DemandForecastResult.generated_at.desc(),
                            DemandForecastResult.horizon_hours,
                        )
                    )
                )
                scada = session.scalar(
                    select(ScadaGridSnapshot).order_by(ScadaGridSnapshot.timestamp.desc())
                )
        except SQLAlchemyError:
            return None

        if not forecasts or scada is None:
            return None
        newest_generated_at = max(_as_utc(row.generated_at) for row in forecasts)
        forecast_cohort = [
            row
            for row in forecasts
            if _as_utc(row.generated_at) == newest_generated_at
            and self._is_live_forecast_pair(row, scada, reference_time)
        ]
        one_hour = next(
            (row for row in forecast_cohort if row.horizon_hours == 1),
            None,
        )
        if one_hour is None:
            return None

        profile = tuple(
            OperatingForecastPoint(
                horizon_minutes=row.horizon_hours * 60,
                forecast_demand_mw=row.forecast_demand_mw,
                forecast_uncertainty_mw=row.forecast_uncertainty_mw,
                confidence=(
                    0.9 if row.validation_status == "VALIDATED" else 0.75
                ),
            )
            for row in sorted(forecast_cohort, key=lambda item: item.horizon_hours)
        )

        result = RiskProbabilityEngine().evaluate(
            OperatingRiskInput(
                forecast_demand_mw=one_hour.forecast_demand_mw,
                forecast_uncertainty_mw=one_hour.forecast_uncertainty_mw,
                current_demand_mw=scada.current_demand_mw,
                online_capacity_mw=scada.online_capacity_mw,
                available_capacity_mw=scada.available_capacity_mw,
                spinning_reserve_mw=scada.spinning_reserve_mw,
                forecast_profile=profile,
                available_capacity_is_verified=not bool(
                    scada.missing_fields.strip()
                ),
            )
        )
        forecast_demand_30m = (
            round(
                scada.current_demand_mw
                + (one_hour.forecast_demand_mw - scada.current_demand_mw) * 0.5,
                4,
            )
            if scada.current_demand_mw is not None
            else one_hour.forecast_demand_mw
        )
        forecast_demand_60m = one_hour.forecast_demand_mw
        return {
            "engine_version": result.engine_version,
            "probability_score": result.probability_score,
            "risk_level": result.risk_level,
            "forecast_demand_30m": forecast_demand_30m,
            "forecast_demand_60m": forecast_demand_60m,
            "recommendation": _dashboard_recommendation(result.recommendation),
            "factors": result.reasons,
            "reason": "; ".join(result.reasons),
            "decision_action": result.decision_action,
            "generator_set": result.generator_set,
            "recommended_capacity_mw": result.recommended_capacity_mw,
            "projected_shortfall_mw": result.projected_shortfall_mw,
            "expected_shortfall_mw": result.expected_shortfall_mw,
            "expected_load_rise_mw": result.expected_load_rise_mw,
            "expected_rise_minutes": result.expected_rise_minutes,
            "startup_time_minutes": result.startup_time_minutes,
            "decision_confidence": result.decision_confidence,
            "weather_effect_mw": result.weather_effect_mw,
            "available_start_capacity_mw": result.available_start_capacity_mw,
            "residual_shortfall_mw": result.residual_shortfall_mw,
        }

    @staticmethod
    def _is_live_forecast_pair(
        forecast: DemandForecastResult,
        scada: ScadaGridSnapshot,
        reference_time: datetime | None,
    ) -> bool:
        now = _as_utc(reference_time or datetime.now(timezone.utc))
        generated_at = _as_utc(forecast.generated_at)
        forecast_timestamp = _as_utc(forecast.forecast_timestamp)
        scada_timestamp = _as_utc(scada.available_at or scada.timestamp)
        max_age = settings.MODEL_FORECAST_STALE_AFTER_SECONDS

        if forecast.quality_status not in {"BASELINE_ACTIVE", "ML_ACTIVE"}:
            return False
        if scada.quality_status != "GOOD" or bool(scada.missing_fields.strip()):
            return False
        if generated_at > now or (now - generated_at).total_seconds() > max_age:
            return False
        if scada_timestamp > now or (now - scada_timestamp).total_seconds() > max_age:
            return False
        if forecast_timestamp <= scada_timestamp:
            return False
        expected_seconds = forecast.horizon_hours * 3600
        actual_seconds = (forecast_timestamp - scada_timestamp).total_seconds()
        return 0 < actual_seconds <= expected_seconds + 900

    def get_latest_scada_snapshot(self) -> ScadaGridSnapshot | None:
        try:
            with self.session_factory() as session:
                return session.scalar(
                    select(ScadaGridSnapshot).order_by(ScadaGridSnapshot.timestamp.desc())
                )
        except SQLAlchemyError:
            return None


def _dashboard_recommendation(recommendation: str) -> str:
    if recommendation == "PREPARE ADDITIONAL GENERATION / START ADDITIONAL TURBINE":
        return "START ADDITIONAL TURBINE"
    return recommendation


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _horizon_delta(horizon_hours: int) -> timedelta:
    return timedelta(hours=horizon_hours)


def _json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
