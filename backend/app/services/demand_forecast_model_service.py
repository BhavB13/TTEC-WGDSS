from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

from sqlalchemy import delete, select

from app.core.config import settings
from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.demand_forecast import DemandForecastResult, ForecastTrainingRow
from app.services.demand_forecast_baselines import (
    hourly_average_forecast,
    hourly_average_lookup,
    persistence_forecast,
    rolling_trend_forecast,
    same_hour_yesterday_forecast,
    seasonal_naive_weekly_forecast,
    target_same_hour_average_forecast,
    trend_adjusted_persistence_forecast,
)
from app.services.forecast_dataset_service import ForecastDatasetService
from app.services.forecast_calendar_service import (
    calendar_context,
    calendar_feature_vector,
)
from app.services.similar_period_service import similar_period_forecast
from app.services.data_period_policy import DataPeriodPolicy

logger = logging.getLogger(__name__)

MODEL_VERSION = "demand-forecast-v5.0"
FEATURE_PROFILE = "demand_weather_grid_state_v5"
MIN_FORECAST_UNCERTAINTY_MW = 5.0
MIN_FORECAST_UNCERTAINTY_DEMAND_RATIO = 0.015
MIN_ML_TRAIN_ROWS = 48
MIN_ML_IMPROVEMENT_RATIO = 0.02
WALK_FORWARD_FOLDS = 3
RECENCY_HALF_LIFE_HOURS = 14 * 24
WEATHER_DEGRADED_WEIGHT = 0.7
LEGACY_DEGRADED_WEIGHT = 0.5
SCADA_ACCEPTED_WEIGHT = 0.8
SCADA_PARTIAL_WEIGHT = 0.65
TRUSTED_HISTORY_HOURS = 60 * 24
FORECAST_INTERVAL_LEVEL = 0.80
FORECAST_INTERVAL_Z = 1.2815515655446004
FEATURE_COLUMNS = (
    "current_demand_mw",
    "lag_1h_demand_mw",
    "lag_2h_demand_mw",
    "lag_3h_demand_mw",
    "lag_6h_demand_mw",
    "lag_24h_demand_mw",
    "lag_48h_demand_mw",
    "lag_168h_demand_mw",
    "target_lag_24h_demand_mw",
    "target_lag_48h_demand_mw",
    "target_lag_168h_demand_mw",
    "rolling_3h_demand_mw",
    "rolling_6h_demand_mw",
    "rolling_12h_demand_mw",
    "rolling_24h_demand_mw",
    "rolling_168h_demand_mw",
    "same_hour_7d_average_mw",
    "target_same_hour_7d_average_mw",
    "demand_volatility_6h_mw",
    "demand_rate_1h_mw",
    "demand_rate_3h_mw",
    "demand_rate_6h_mw",
    "spinning_reserve_mw",
    "available_capacity_mw",
    "online_capacity_mw",
    "reserve_margin_mw",
    "online_spare_mw",
    "spinning_reserve_lag_1h_mw",
    "available_capacity_lag_1h_mw",
    "online_capacity_lag_1h_mw",
    "spinning_reserve_rate_1h_mw",
    "available_capacity_rate_1h_mw",
    "online_capacity_rate_1h_mw",
    "temperature_c",
    "scada_temperature_c",
    "temperature_lag_1h_c",
    "rolling_3h_temperature_c",
    "temperature_rate_1h_c",
    "humidity_percent",
    "rainfall_mm_hr",
    "cloud_cover_percent",
    "wind_speed_kmh",
    "pressure_hpa",
    "forecast_temperature_c",
    "forecast_humidity_percent",
    "forecast_rainfall_mm_hr",
    "forecast_cloud_cover_percent",
    "forecast_wind_speed_kmh",
    "forecast_precipitation_probability_percent",
)
FEATURE_DEFAULTS = {
    "temperature_c": 28.0,
    "humidity_percent": 70.0,
    "rainfall_mm_hr": 0.0,
    "cloud_cover_percent": 50.0,
    "wind_speed_kmh": 0.0,
    "pressure_hpa": 1013.25,
    "forecast_temperature_c": 28.0,
    "forecast_humidity_percent": 70.0,
    "forecast_rainfall_mm_hr": 0.0,
    "forecast_cloud_cover_percent": 50.0,
    "forecast_wind_speed_kmh": 0.0,
    "forecast_precipitation_probability_percent": 0.0,
    "scada_temperature_c": 28.0,
    "temperature_lag_1h_c": 28.0,
    "rolling_3h_temperature_c": 28.0,
    "temperature_rate_1h_c": 0.0,
    "spinning_reserve_mw": 0.0,
    "available_capacity_mw": 0.0,
    "online_capacity_mw": 0.0,
    "reserve_margin_mw": 0.0,
    "online_spare_mw": 0.0,
    "spinning_reserve_lag_1h_mw": 0.0,
    "available_capacity_lag_1h_mw": 0.0,
    "online_capacity_lag_1h_mw": 0.0,
    "spinning_reserve_rate_1h_mw": 0.0,
    "available_capacity_rate_1h_mw": 0.0,
    "online_capacity_rate_1h_mw": 0.0,
}


@dataclass(frozen=True)
class ForecastMetrics:
    mae: float
    rmse: float
    mape: float
    residual_std: float
    peak_error_mw: float = 0.0


@dataclass(frozen=True)
class HorizonModelResult:
    horizon_hours: int
    mode: str
    active_model: str
    best_baseline: str
    forecast_timestamp: datetime
    forecast_demand_mw: float
    forecast_uncertainty_mw: float
    baseline_forecast_mw: float
    metrics: ForecastMetrics
    ml_metrics: ForecastMetrics | None
    ml_beats_baseline: bool
    train_rows: int
    test_rows: int
    feature_profile: str = FEATURE_PROFILE
    validation_status: str = "PROTOTYPE"
    training_span_hours: int = 0
    candidate_metrics: dict[str, object] | None = None
    confidence_lower_mw: float = 0.0
    confidence_upper_mw: float = 0.0
    confidence_level: float = FORECAST_INTERVAL_LEVEL
    p10_demand_mw: float = 0.0
    p50_demand_mw: float = 0.0
    p90_demand_mw: float = 0.0
    training_start_at: datetime | None = None
    training_end_at: datetime | None = None
    feature_importance: dict[str, float] | None = None
    fallback_reason: str | None = None
    temperature_load_correlation: float | None = None
    similar_period_forecast_mw: float | None = None
    similar_examples: tuple[dict[str, object], ...] = ()
    contributing_factors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ModelCandidate:
    candidate_id: str
    model_name: str
    family: str
    params: dict[str, Any]
    similarity_weight: float = 0.0
    target_mode: str = "absolute"


@dataclass(frozen=True)
class _MLPredictionResult:
    predictions: list[float]
    latest_prediction: float
    selected_candidate: _ModelCandidate
    validation_metrics: ForecastMetrics
    validation_bias_mw: float
    candidate_metrics: dict[str, dict[str, float | str | bool | int]]
    calibration_residuals: tuple[float, ...]


@dataclass(frozen=True)
class _TemperatureProfile:
    balance_point_c: float
    global_normal_c: float
    normal_by_hour: dict[int, float]
    normal_by_season_hour: dict[tuple[str, int], float]
    selection_mae_mw: float | None
    no_temperature_mae_mw: float | None
    candidate_metrics: dict[str, dict[str, float]]
    sample_count: int

    def normal_for(self, timestamp: datetime) -> float:
        context = calendar_context(
            timestamp,
            settings.FORECAST_EXTRA_HOLIDAY_DATES,
        )
        return self.normal_by_season_hour.get(
            (context.season, timestamp.hour),
            self.normal_by_hour.get(timestamp.hour, self.global_normal_c),
        )

    def as_json_object(self) -> dict[str, object]:
        improvement = None
        if (
            self.selection_mae_mw is not None
            and self.no_temperature_mae_mw is not None
        ):
            improvement = self.no_temperature_mae_mw - self.selection_mae_mw
        return {
            "balance_point_c": round(self.balance_point_c, 3),
            "selection_mae_mw": self.selection_mae_mw,
            "no_temperature_mae_mw": self.no_temperature_mae_mw,
            "temperature_mae_improvement_mw": (
                round(improvement, 4) if improvement is not None else None
            ),
            "sample_count": self.sample_count,
            "candidate_metrics": self.candidate_metrics,
        }


@dataclass(frozen=True)
class _FeatureTransform:
    fill_values: dict[str, float]
    lower_bounds: dict[str, float]
    upper_bounds: dict[str, float]
    temperature_profile: _TemperatureProfile

    def value(self, row: ForecastTrainingRow, column: str) -> float:
        raw = getattr(row, column)
        value = self.fill_values[column] if raw is None else float(raw)
        lower = self.lower_bounds.get(column)
        upper = self.upper_bounds.get(column)
        if lower is not None:
            value = max(lower, value)
        if upper is not None:
            value = min(upper, value)
        return value


@dataclass(frozen=True)
class _PreparedModelData:
    x_train: list[list[float]]
    y_absolute: list[float]
    y_load_state_residual: list[float]
    x_test: list[list[float]]
    test_anchors: list[float]
    sample_weights: list[float]


@dataclass(frozen=True)
class DemandForecastTrainingResult:
    results: list[HorizonModelResult]


class DemandForecastModelService:
    def __init__(
        self,
        session_factory=SessionLocal,
        enforce_period_policy: bool | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.period_policy = DataPeriodPolicy.from_settings()
        self.enforce_period_policy = (
            session_factory is SessionLocal
            if enforce_period_policy is None
            else enforce_period_policy
        )

    def train_and_store(
        self,
        replace_existing: bool = True,
    ) -> DemandForecastTrainingResult:
        if self.session_factory is SessionLocal:
            initialize_database()

        inference_rows = ForecastDatasetService(
            session_factory=self.session_factory
        ).build_inference_rows()

        with self.session_factory() as session:
            rows = list(
                session.scalars(
                    select(ForecastTrainingRow).order_by(
                        ForecastTrainingRow.horizon_hours,
                        ForecastTrainingRow.feature_timestamp,
                    )
                )
            )
            excluded = (
                [
                    row for row in rows
                    if not self.period_policy.is_training_timestamp(row.feature_timestamp)
                    or not self.period_policy.is_training_timestamp(row.target_timestamp)
                ]
                if self.enforce_period_policy
                else []
            )
            if excluded:
                logger.warning(
                    "Excluded %s forecast rows outside configured October-May "
                    "training period; June remains simulated-live only",
                    len(excluded),
                )
            if self.enforce_period_policy:
                rows = [
                    row for row in rows
                    if self.period_policy.is_training_timestamp(row.feature_timestamp)
                    and self.period_policy.is_training_timestamp(row.target_timestamp)
                ]
            results = self.evaluate_rows(rows, inference_rows=inference_rows)
            if replace_existing:
                session.execute(delete(DemandForecastResult))
                session.flush()

            generated_at = datetime.now(timezone.utc)
            for result in results:
                session.add(
                    DemandForecastResult(
                        forecast_timestamp=result.forecast_timestamp,
                        generated_at=generated_at,
                        horizon_hours=result.horizon_hours,
                        forecast_demand_mw=result.forecast_demand_mw,
                        forecast_uncertainty_mw=result.forecast_uncertainty_mw,
                        model_name=result.active_model,
                        model_version=MODEL_VERSION,
                        baseline_name=result.best_baseline,
                        baseline_forecast_mw=result.baseline_forecast_mw,
                        mae=result.metrics.mae,
                        rmse=result.metrics.rmse,
                        mape=result.metrics.mape,
                        residual_std=result.metrics.residual_std,
                        ml_beats_baseline=result.ml_beats_baseline,
                        quality_status=result.mode,
                        feature_profile=result.feature_profile,
                        validation_status=result.validation_status,
                        training_span_hours=result.training_span_hours,
                        train_row_count=result.train_rows,
                        test_row_count=result.test_rows,
                        candidate_metrics=json.dumps(
                            result.candidate_metrics or {},
                            sort_keys=True,
                        ),
                        confidence_lower_mw=result.confidence_lower_mw,
                        confidence_upper_mw=result.confidence_upper_mw,
                        confidence_level=result.confidence_level,
                        p10_demand_mw=result.p10_demand_mw,
                        p50_demand_mw=result.p50_demand_mw,
                        p90_demand_mw=result.p90_demand_mw,
                        training_start_at=result.training_start_at,
                        training_end_at=result.training_end_at,
                        feature_importance=json.dumps(
                            result.feature_importance or {}, sort_keys=True
                        ),
                        fallback_reason=result.fallback_reason,
                        temperature_load_correlation=(
                            result.temperature_load_correlation
                        ),
                        similar_period_forecast_mw=(
                            result.similar_period_forecast_mw
                        ),
                        similar_examples=json.dumps(
                            result.similar_examples,
                            sort_keys=True,
                        ),
                        contributing_factors=json.dumps(
                            result.contributing_factors,
                        ),
                    )
                )
            session.commit()

        return DemandForecastTrainingResult(results=results)

    def evaluate_rows(
        self,
        rows: list[ForecastTrainingRow],
        inference_rows: dict[int, ForecastTrainingRow] | None = None,
    ) -> list[HorizonModelResult]:
        results: list[HorizonModelResult] = []
        horizons = sorted({row.horizon_hours for row in rows})
        for horizon in horizons:
            horizon_rows = sorted(
                (
                    row
                    for row in rows
                    if row.horizon_hours == horizon
                    and row.source_quality_status.upper()
                    not in {"SCADA_DEGRADED", "BAD", "INACTIVE"}
                ),
                key=lambda row: row.feature_timestamp,
            )
            if len(horizon_rows) < 3:
                continue
            results.append(
                self._evaluate_horizon(
                    horizon,
                    horizon_rows,
                    inference_row=(inference_rows or {}).get(horizon),
                )
            )
        return results

    def _evaluate_horizon(
        self,
        horizon_hours: int,
        rows: list[ForecastTrainingRow],
        inference_row: ForecastTrainingRow | None = None,
    ) -> HorizonModelResult:
        split_index = max(1, int(len(rows) * 0.8))
        if split_index >= len(rows):
            split_index = len(rows) - 1
        train_rows = rows[:split_index]
        test_rows = rows[split_index:]

        baseline_validation_actual, baseline_validation_predictions = (
            self._walk_forward_baseline_predictions(train_rows)
        )
        baseline_biases = {
            name: _median_residual(
                baseline_validation_actual,
                predictions,
            )
            for name, predictions in baseline_validation_predictions.items()
        }
        corrected_baseline_validation = {
            name: _apply_bias(predictions, baseline_biases[name])
            for name, predictions in baseline_validation_predictions.items()
        }
        best_baseline, _, _ = _select_best_baseline(
            baseline_validation_actual,
            corrected_baseline_validation,
        )
        baseline_bias = baseline_biases[best_baseline]
        baseline_predictions = self._baseline_predictions(train_rows, test_rows)
        best_predictions = _apply_bias(
            baseline_predictions[best_baseline],
            baseline_bias,
        )
        baseline_metrics = _metrics(_targets(test_rows), best_predictions)
        calibration_residuals = tuple(
            observed - predicted
            for observed, predicted in zip(
                baseline_validation_actual,
                corrected_baseline_validation[best_baseline],
            )
        )

        active_model = best_baseline
        mode = "BASELINE_ACTIVE"
        forecast_prediction = best_predictions[-1]
        active_predictions = best_predictions
        active_metrics = baseline_metrics
        ml_metrics = None
        ml_beats_baseline = False
        selected_candidate: _ModelCandidate | None = None
        selected_ml_bias = 0.0
        candidate_metrics: dict[str, object] = {}
        fallback_reason: str | None = None

        ml_prediction_result = self._try_ml_model(
            train_rows,
            test_rows,
            validation_similarity_values=baseline_validation_predictions.get(
                "similar_periods"
            ),
            test_similarity_values=baseline_predictions.get("similar_periods"),
        )
        if ml_prediction_result is not None:
            if isinstance(ml_prediction_result, _MLPredictionResult):
                ml_predictions = ml_prediction_result.predictions
                latest_prediction = ml_prediction_result.latest_prediction
                selected_candidate = ml_prediction_result.selected_candidate
                selected_ml_bias = ml_prediction_result.validation_bias_mw
                candidate_metrics = ml_prediction_result.candidate_metrics
                selected_model_name = selected_candidate.model_name
            else:
                # Backwards-compatible path for small test doubles and callers
                # that used the former private tuple return value.
                ml_predictions, latest_prediction = ml_prediction_result
                selected_model_name = "HistGradientBoostingRegressor"
            ml_metrics = _metrics(_targets(test_rows), ml_predictions)
            improvement_threshold = 1.0 - MIN_ML_IMPROVEMENT_RATIO
            ml_beats_baseline = (
                ml_metrics.mae < baseline_metrics.mae * improvement_threshold
                and ml_metrics.rmse < baseline_metrics.rmse * improvement_threshold
            )
            if ml_beats_baseline:
                active_model = selected_model_name
                mode = "ML_ACTIVE"
                forecast_prediction = latest_prediction
                active_predictions = ml_predictions
                active_metrics = ml_metrics
                if isinstance(ml_prediction_result, _MLPredictionResult):
                    calibration_residuals = (
                        ml_prediction_result.calibration_residuals
                    )
            else:
                fallback_reason = (
                    "ML did not beat the selected baseline on both MAE and RMSE "
                    "for the newest chronological holdout"
                )
        else:
            fallback_reason = (
                "ML unavailable or insufficient training history; selected validated baseline"
            )

        latest_row = test_rows[-1]
        forecast_timestamp = latest_row.target_timestamp
        baseline_forecast = best_predictions[-1]
        if inference_row is not None:
            forecast_timestamp = inference_row.target_timestamp
            inference_baseline_bias = _median_residual(
                baseline_validation_actual + _targets(test_rows),
                baseline_validation_predictions[best_baseline]
                + baseline_predictions[best_baseline],
            )
            inference_baselines = self._baseline_predictions(
                rows,
                [inference_row],
            )
            raw_baseline_forecast = inference_baselines[best_baseline][0]
            baseline_forecast = max(
                0.0,
                raw_baseline_forecast + inference_baseline_bias,
            )
            forecast_prediction = baseline_forecast
            if ml_beats_baseline:
                if selected_candidate is not None:
                    forecast_prediction = max(
                        0.0,
                        self._fit_candidate_predictions(
                            selected_candidate,
                            rows,
                            [inference_row],
                            similarity_predictions=inference_baselines.get(
                                "similar_periods"
                            ),
                        )[0]
                        + selected_ml_bias,
                    )
                else:
                    inference_result = self._try_ml_model(rows, [inference_row])
                    if inference_result is not None:
                        forecast_prediction = (
                            inference_result.predictions[0]
                            if isinstance(inference_result, _MLPredictionResult)
                            else inference_result[0][0]
                        )
            if inference_row.source_quality_status != "GOOD":
                mode = f"{mode}_DEGRADED"

        explanation_row = inference_row or latest_row
        explanation_history = rows if inference_row is not None else train_rows
        similar_periods = similar_period_forecast(
            explanation_history,
            explanation_row,
            extra_holiday_dates=settings.FORECAST_EXTRA_HOLIDAY_DATES,
        )
        input_quality = _input_quality_diagnostics(
            explanation_row,
            explanation_history,
        )
        guarded_prediction = _guard_forecast_for_input_quality(
            forecast_prediction,
            similar_periods.forecast_mw,
            similar_periods.spread_mw,
            active_metrics,
            input_quality,
        )
        if abs(guarded_prediction - forecast_prediction) > 1e-9:
            forecast_prediction = guarded_prediction
            mode = f"{mode}_INPUT_GUARDED"

        uncertainty = _calibrated_uncertainty(
            metrics=active_metrics,
            actual=_targets(test_rows),
            predicted=active_predictions,
            forecast_demand_mw=forecast_prediction,
            horizon_hours=horizon_hours,
        )
        if (
            inference_row is not None
            and inference_row.source_quality_status != "GOOD"
        ):
            uncertainty *= 1.25

        temperature_correlation = _temperature_load_correlation(
            explanation_history,
        )
        contributing_factors = _contributing_factors(
            row=explanation_row,
            history=explanation_history,
            active_model=active_model,
            best_baseline=best_baseline,
            forecast_demand_mw=forecast_prediction,
            baseline_forecast_mw=baseline_forecast,
            temperature_correlation=temperature_correlation,
            similar_forecast_mw=similar_periods.forecast_mw,
            similar_count=len(similar_periods.examples),
        )
        confidence_level = FORECAST_INTERVAL_LEVEL
        confidence_lower, confidence_upper = _empirical_prediction_interval(
            forecast_prediction,
            calibration_residuals,
            minimum_half_width=FORECAST_INTERVAL_Z * uncertainty,
        )
        interval_coverage = _interval_coverage(
            _targets(test_rows),
            active_predictions,
            calibration_residuals,
            minimum_half_width=FORECAST_INTERVAL_Z * uncertainty,
        )

        training_span_hours = max(
            0,
            int(
                (
                    train_rows[-1].feature_timestamp
                    - train_rows[0].feature_timestamp
                ).total_seconds()
                / 3600.0
            ),
        )
        validation_status = (
            "VALIDATED"
            if training_span_hours >= TRUSTED_HISTORY_HOURS
            else "PROTOTYPE"
        )
        feature_importance = self._forecast_feature_importance(
            active_model=active_model,
            selected_candidate=selected_candidate if ml_beats_baseline else None,
            best_baseline=best_baseline,
            train_rows=train_rows,
            test_rows=test_rows,
        )
        temperature_analysis = _fit_feature_transform(
            train_rows
        ).temperature_profile.as_json_object()
        temperature_feature_names = {
            name
            for name in _feature_names()
            if "temperature" in name
            or "cooling" in name
            or "heating" in name
        }
        temperature_analysis["active_feature_importance"] = round(
            sum(
                importance
                for name, importance in feature_importance.items()
                if name in temperature_feature_names
            ),
            6,
        )

        logger.info(
            "Demand forecast evaluated",
            extra={
                "horizon_hours": horizon_hours,
                "active_model": active_model,
                "mode": mode,
                "mae_mw": active_metrics.mae,
                "rmse_mw": active_metrics.rmse,
                "peak_error_mw": active_metrics.peak_error_mw,
                "interval_coverage": interval_coverage,
                "forecast_demand_mw": round(forecast_prediction, 4),
                "input_quality_status": input_quality["status"],
                "temperature_balance_point_c": temperature_analysis[
                    "balance_point_c"
                ],
            },
        )

        return HorizonModelResult(
            horizon_hours=horizon_hours,
            mode=mode,
            active_model=active_model,
            best_baseline=best_baseline,
            forecast_timestamp=forecast_timestamp,
            forecast_demand_mw=round(max(0.0, forecast_prediction), 4),
            forecast_uncertainty_mw=round(uncertainty, 4),
            baseline_forecast_mw=round(baseline_forecast, 4),
            metrics=active_metrics,
            ml_metrics=ml_metrics,
            ml_beats_baseline=ml_beats_baseline,
            train_rows=len(train_rows),
            test_rows=len(test_rows),
            training_span_hours=training_span_hours,
            validation_status=validation_status,
            candidate_metrics={
                **candidate_metrics,
                **{
                    f"baseline_{name}": {
                        "model": name,
                        "mae": metrics.mae,
                        "rmse": metrics.rmse,
                        "mape": metrics.mape,
                        "peak_error_mw": metrics.peak_error_mw,
                        "selected": False,
                        "active_baseline": name == best_baseline,
                    }
                    for name, metrics in self._baseline_metric_summary(
                        train_rows,
                        test_rows,
                        baseline_biases,
                    ).items()
                },
                "active": {
                    "model": active_model,
                    "mae": active_metrics.mae,
                    "rmse": active_metrics.rmse,
                    "mape": active_metrics.mape,
                    "peak_error_mw": active_metrics.peak_error_mw,
                    "interval_coverage": interval_coverage,
                },
                "baseline": {
                    "model": best_baseline,
                    "mae": baseline_metrics.mae,
                    "rmse": baseline_metrics.rmse,
                    "mape": baseline_metrics.mape,
                    "peak_error_mw": baseline_metrics.peak_error_mw,
                },
                "similarity_analysis": {
                    "forecast_mw": similar_periods.forecast_mw,
                    "spread_mw": similar_periods.spread_mw,
                    "example_count": len(similar_periods.examples),
                    "temperature_load_correlation": temperature_correlation,
                    "selected": False,
                },
                "temperature_analysis": temperature_analysis,
                "input_quality": input_quality,
            },
            confidence_lower_mw=round(confidence_lower, 4),
            confidence_upper_mw=round(confidence_upper, 4),
            confidence_level=confidence_level,
            p10_demand_mw=round(confidence_lower, 4),
            p50_demand_mw=round(max(0.0, forecast_prediction), 4),
            p90_demand_mw=round(confidence_upper, 4),
            training_start_at=train_rows[0].feature_timestamp,
            training_end_at=train_rows[-1].feature_timestamp,
            feature_importance=feature_importance,
            fallback_reason=fallback_reason,
            temperature_load_correlation=temperature_correlation,
            similar_period_forecast_mw=similar_periods.forecast_mw,
            similar_examples=tuple(
                example.as_json_object() for example in similar_periods.examples
            ),
            contributing_factors=tuple(contributing_factors),
        )

    @staticmethod
    def _baseline_predictions(
        train_rows: list[ForecastTrainingRow],
        test_rows: list[ForecastTrainingRow],
    ) -> dict[str, list[float]]:
        hourly_lookup = hourly_average_lookup(train_rows)
        fallback_average = mean(row.target_demand_mw for row in train_rows)
        predictions = {
            "persistence": [],
            "trend_adjusted_persistence": [],
            "rolling_trend": [],
            "same_hour_yesterday": [],
            "seasonal_naive_weekly": [],
            "hourly_average": [],
            "target_same_hour_7d_average": [],
            "similar_periods": [],
        }
        for row in test_rows:
            predictions["persistence"].append(persistence_forecast(row))
            predictions["trend_adjusted_persistence"].append(
                _fallback_if_none(
                    trend_adjusted_persistence_forecast(row),
                    fallback_average,
                )
            )
            predictions["rolling_trend"].append(
                _fallback_if_none(rolling_trend_forecast(row), fallback_average)
            )
            predictions["same_hour_yesterday"].append(
                _fallback_if_none(
                    same_hour_yesterday_forecast(row),
                    fallback_average,
                )
            )
            predictions["seasonal_naive_weekly"].append(
                _fallback_if_none(
                    seasonal_naive_weekly_forecast(row),
                    fallback_average,
                )
            )
            predictions["hourly_average"].append(
                _fallback_if_none(
                    hourly_average_forecast(row, hourly_lookup),
                    fallback_average,
                )
            )
            predictions["target_same_hour_7d_average"].append(
                _fallback_if_none(
                    target_same_hour_average_forecast(row),
                    fallback_average,
                )
            )
            similarity = similar_period_forecast(
                train_rows,
                row,
                extra_holiday_dates=settings.FORECAST_EXTRA_HOLIDAY_DATES,
            )
            predictions["similar_periods"].append(
                _fallback_if_none(similarity.forecast_mw, fallback_average)
            )
        return predictions

    def _baseline_metric_summary(
        self,
        train_rows: list[ForecastTrainingRow],
        test_rows: list[ForecastTrainingRow],
        baseline_biases: dict[str, float] | None = None,
    ) -> dict[str, ForecastMetrics]:
        predictions = self._baseline_predictions(train_rows, test_rows)
        actual = _targets(test_rows)
        if baseline_biases is None:
            validation_actual, validation_predictions = (
                self._walk_forward_baseline_predictions(train_rows)
            )
            baseline_biases = {
                name: _median_residual(validation_actual, values)
                for name, values in validation_predictions.items()
            }
        summary: dict[str, ForecastMetrics] = {}
        for name, values in predictions.items():
            summary[name] = _metrics(
                actual,
                _apply_bias(values, baseline_biases.get(name, 0.0)),
            )
        return summary

    def _walk_forward_baseline_predictions(
        self,
        rows: list[ForecastTrainingRow],
    ) -> tuple[list[float], dict[str, list[float]]]:
        actual: list[float] = []
        combined_predictions: dict[str, list[float]] = {}
        for fold_train, fold_validation in _walk_forward_splits(rows):
            fold_predictions = self._baseline_predictions(
                fold_train,
                fold_validation,
            )
            actual.extend(_targets(fold_validation))
            for name, values in fold_predictions.items():
                combined_predictions.setdefault(name, []).extend(values)
        return actual, combined_predictions

    def _select_baseline_walk_forward(
        self,
        rows: list[ForecastTrainingRow],
    ) -> tuple[str, float]:
        actual, combined_predictions = self._walk_forward_baseline_predictions(rows)
        corrected_predictions = {
            name: _apply_bias(values, _median_residual(actual, values))
            for name, values in combined_predictions.items()
        }
        best_baseline, _, _ = _select_best_baseline(actual, corrected_predictions)
        return best_baseline, _median_residual(
            actual,
            combined_predictions[best_baseline],
        )

    def _baseline_bias_walk_forward(
        self,
        rows: list[ForecastTrainingRow],
        baseline_name: str,
    ) -> tuple[list[float], float]:
        actual, predictions = self._walk_forward_baseline_predictions(rows)
        predicted = predictions[baseline_name]
        return predicted, _median_residual(actual, predicted)

    def _try_ml_model(
        self,
        train_rows: list[ForecastTrainingRow],
        test_rows: list[ForecastTrainingRow],
        validation_similarity_values: list[float] | None = None,
        test_similarity_values: list[float] | None = None,
    ) -> _MLPredictionResult | tuple[list[float], float] | None:
        if len(train_rows) < MIN_ML_TRAIN_ROWS:
            return None
        try:
            import sklearn  # noqa: F401
        except Exception:
            return None

        validation_folds = _walk_forward_splits(train_rows)
        smallest_fold = min(len(fold_train) for fold_train, _ in validation_folds)
        min_samples_leaf = max(5, min(20, smallest_fold // 12))
        candidates = self._model_candidates(min_samples_leaf)
        prepared_folds = [
            _prepare_model_data(fold_train, fold_validation)
            for fold_train, fold_validation in validation_folds
        ]
        similarity_values: list[float | None] = (
            list(validation_similarity_values)
            if validation_similarity_values is not None
            else self._walk_forward_similarity_values(validation_folds)
        )
        scored: list[
            tuple[_ModelCandidate, ForecastMetrics, float, list[float], list[float]]
        ] = []
        for candidate in candidates:
            actual, raw_predictions = self._walk_forward_candidate_predictions(
                candidate,
                validation_folds,
                prepared_folds=prepared_folds,
            )
            similarity_predictions = [
                value if value is not None else fallback
                for value, fallback in zip(similarity_values, raw_predictions)
            ]
            for similarity_weight in (0.0, 0.25, 0.5, 0.75):
                scored_candidate = _ModelCandidate(
                    candidate_id=(
                        candidate.candidate_id
                        if similarity_weight == 0
                        else f"{candidate.candidate_id}_similarity_{int(similarity_weight * 100)}"
                    ),
                    model_name=(
                        candidate.model_name
                        if similarity_weight == 0
                        else f"{candidate.model_name}+SimilarPeriods"
                    ),
                    family=candidate.family,
                    params=candidate.params,
                    similarity_weight=similarity_weight,
                    target_mode=candidate.target_mode,
                )
                blended = [
                    (1.0 - similarity_weight) * model_prediction
                    + similarity_weight * similarity_prediction
                    for model_prediction, similarity_prediction in zip(
                        raw_predictions,
                        similarity_predictions,
                    )
                ]
                bias = _median_residual(actual, blended)
                corrected = _apply_bias(blended, bias)
                scored.append(
                    (
                        scored_candidate,
                        _metrics(actual, corrected),
                        bias,
                        actual,
                        corrected,
                    )
                )
        (
            selected_candidate,
            validation_metrics,
            bias,
            selected_actual,
            selected_corrected,
        ) = min(
            scored,
            key=lambda item: (
                item[1].mae,
                item[1].rmse,
                item[1].mape,
                item[0].candidate_id,
            ),
        )
        predictions = self._fit_candidate_predictions(
            selected_candidate,
            train_rows,
            test_rows,
            similarity_predictions=test_similarity_values,
        )
        corrected = _apply_bias(predictions, bias)
        candidate_metrics = {
            candidate.candidate_id: {
                "model": candidate.model_name,
                "family": candidate.family,
                "validation_mae": metrics.mae,
                "validation_rmse": metrics.rmse,
                "validation_mape": metrics.mape,
                "validation_residual_std": metrics.residual_std,
                "validation_peak_error_mw": metrics.peak_error_mw,
                "similarity_weight": candidate.similarity_weight,
                "target_mode": candidate.target_mode,
                "selected": candidate.candidate_id == selected_candidate.candidate_id,
            }
            for candidate, metrics, _, _, _ in scored
        }
        return _MLPredictionResult(
            predictions=corrected,
            latest_prediction=corrected[-1],
            selected_candidate=selected_candidate,
            validation_metrics=validation_metrics,
            validation_bias_mw=bias,
            candidate_metrics=candidate_metrics,
            calibration_residuals=tuple(
                observed - predicted
                for observed, predicted in zip(
                    selected_actual,
                    selected_corrected,
                )
            ),
        )

    @staticmethod
    def _model_candidates(min_samples_leaf: int) -> tuple[_ModelCandidate, ...]:
        return (
            _ModelCandidate(
                candidate_id="ridge_alpha_10",
                model_name="Ridge",
                family="ridge",
                params={"alpha": 10.0},
            ),
            _ModelCandidate(
                candidate_id="ridge_load_state_residual",
                model_name="LoadStateResidualRidge",
                family="ridge",
                params={"alpha": 10.0},
                target_mode="load_state_residual",
            ),
            _ModelCandidate(
                candidate_id="hist_gradient_boosting",
                model_name="HistGradientBoostingRegressor",
                family="hist_gradient_boosting",
                params={
                    "loss": "absolute_error",
                    "learning_rate": 0.05,
                    "max_iter": 250,
                    "max_leaf_nodes": 15,
                    "min_samples_leaf": min_samples_leaf,
                    "l2_regularization": 1.0,
                },
            ),
            _ModelCandidate(
                candidate_id="hist_gradient_boosting_load_state_residual",
                model_name="LoadStateResidualHistGradientBoosting",
                family="hist_gradient_boosting",
                params={
                    "loss": "absolute_error",
                    "learning_rate": 0.05,
                    "max_iter": 250,
                    "max_leaf_nodes": 15,
                    "min_samples_leaf": min_samples_leaf,
                    "l2_regularization": 1.0,
                },
                target_mode="load_state_residual",
            ),
            _ModelCandidate(
                candidate_id="random_forest",
                model_name="RandomForestRegressor",
                family="random_forest",
                params={
                    "n_estimators": 160,
                    "max_depth": 10,
                    "min_samples_leaf": max(2, min_samples_leaf // 2),
                    "max_features": 0.75,
                    "n_jobs": -1,
                },
            ),
            _ModelCandidate(
                candidate_id="extra_trees",
                model_name="ExtraTreesRegressor",
                family="extra_trees",
                params={
                    "n_estimators": 180,
                    "max_depth": 12,
                    "min_samples_leaf": max(2, min_samples_leaf // 2),
                    "max_features": 0.8,
                    "n_jobs": -1,
                },
            ),
        )

    def _walk_forward_candidate_predictions(
        self,
        candidate: _ModelCandidate,
        folds: list[tuple[list[ForecastTrainingRow], list[ForecastTrainingRow]]],
        prepared_folds: list[_PreparedModelData] | None = None,
    ) -> tuple[list[float], list[float]]:
        actual: list[float] = []
        predicted: list[float] = []
        for fold_index, (fold_train, fold_validation) in enumerate(folds):
            actual.extend(_targets(fold_validation))
            prepared = (
                prepared_folds[fold_index]
                if prepared_folds is not None
                else _prepare_model_data(fold_train, fold_validation)
            )
            predicted.extend(_fit_prepared_model_predictions(candidate, prepared))
        return actual, predicted

    @staticmethod
    def _walk_forward_similarity_values(
        folds: list[tuple[list[ForecastTrainingRow], list[ForecastTrainingRow]]],
    ) -> list[float | None]:
        predictions: list[float | None] = []
        for fold_train, fold_validation in folds:
            for row in fold_validation:
                similarity = similar_period_forecast(
                    fold_train,
                    row,
                    extra_holiday_dates=settings.FORECAST_EXTRA_HOLIDAY_DATES,
                )
                predictions.append(similarity.forecast_mw)
        return predictions

    @staticmethod
    def _fit_candidate_predictions(
        candidate: _ModelCandidate,
        train_rows: list[ForecastTrainingRow],
        test_rows: list[ForecastTrainingRow],
        similarity_predictions: list[float] | None = None,
    ) -> list[float]:
        prepared = _prepare_model_data(train_rows, test_rows)
        model_predictions = _fit_prepared_model_predictions(candidate, prepared)
        if candidate.similarity_weight <= 0:
            return model_predictions
        blended: list[float] = []
        for index, (row, model_prediction) in enumerate(
            zip(test_rows, model_predictions)
        ):
            if similarity_predictions is not None:
                similarity_prediction = similarity_predictions[index]
            else:
                similarity = similar_period_forecast(
                    train_rows,
                    row,
                    extra_holiday_dates=settings.FORECAST_EXTRA_HOLIDAY_DATES,
                )
                similarity_prediction = (
                    similarity.forecast_mw
                    if similarity.forecast_mw is not None
                    else model_prediction
                )
            blended.append(
                (1.0 - candidate.similarity_weight) * model_prediction
                + candidate.similarity_weight * similarity_prediction
            )
        return blended

    def _forecast_feature_importance(
        self,
        *,
        active_model: str,
        selected_candidate: _ModelCandidate | None,
        best_baseline: str,
        train_rows: list[ForecastTrainingRow],
        test_rows: list[ForecastTrainingRow],
    ) -> dict[str, float]:
        if selected_candidate is None:
            baseline_features = {
                "persistence": "current_demand_mw",
                "trend_adjusted_persistence": "demand_rate_1h_mw",
                "rolling_trend": "demand_rate_3h_mw",
                "same_hour_yesterday": "target_lag_24h_demand_mw",
                "seasonal_naive_weekly": "target_lag_168h_demand_mw",
                "hourly_average": "target_hour_cycle",
                "target_same_hour_7d_average": "target_same_hour_7d_average_mw",
                "similar_periods": "similar_period_match",
            }
            return {baseline_features.get(best_baseline, active_model): 1.0}
        try:
            return _candidate_permutation_importance(
                selected_candidate,
                train_rows,
                test_rows,
            )
        except Exception:
            return {"importance_unavailable": 1.0}


def _prepare_model_data(
    train_rows: list[ForecastTrainingRow],
    test_rows: list[ForecastTrainingRow],
) -> _PreparedModelData:
    """Fit cutoff-safe preprocessing once for every candidate in a fold."""

    transform = _fit_feature_transform(train_rows)
    train_anchors = [_load_state_anchor(row) for row in train_rows]
    return _PreparedModelData(
        x_train=[_feature_vector(row, transform) for row in train_rows],
        y_absolute=[float(row.target_demand_mw) for row in train_rows],
        y_load_state_residual=[
            float(row.target_demand_mw) - anchor
            for row, anchor in zip(train_rows, train_anchors)
        ],
        x_test=[_feature_vector(row, transform) for row in test_rows],
        test_anchors=[_load_state_anchor(row) for row in test_rows],
        sample_weights=_training_sample_weights(train_rows),
    )


def _fit_prepared_model_predictions(
    candidate: _ModelCandidate,
    prepared: _PreparedModelData,
) -> list[float]:
    y_train = (
        prepared.y_load_state_residual
        if candidate.target_mode == "load_state_residual"
        else prepared.y_absolute
    )
    if candidate.family == "ridge":
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        scaled_train = scaler.fit_transform(prepared.x_train)
        scaled_test = scaler.transform(prepared.x_test)
        model = Ridge(**candidate.params)
        model.fit(
            scaled_train,
            y_train,
            sample_weight=prepared.sample_weights,
        )
        predicted = model.predict(scaled_test)
    elif candidate.family == "hist_gradient_boosting":
        from sklearn.ensemble import HistGradientBoostingRegressor

        model = HistGradientBoostingRegressor(
            random_state=42,
            **candidate.params,
        )
        model.fit(
            prepared.x_train,
            y_train,
            sample_weight=prepared.sample_weights,
        )
        predicted = model.predict(prepared.x_test)
    elif candidate.family == "random_forest":
        from sklearn.ensemble import RandomForestRegressor

        model = RandomForestRegressor(random_state=42, **candidate.params)
        model.fit(
            prepared.x_train,
            y_train,
            sample_weight=prepared.sample_weights,
        )
        predicted = model.predict(prepared.x_test)
    elif candidate.family == "extra_trees":
        from sklearn.ensemble import ExtraTreesRegressor

        model = ExtraTreesRegressor(random_state=42, **candidate.params)
        model.fit(
            prepared.x_train,
            y_train,
            sample_weight=prepared.sample_weights,
        )
        predicted = model.predict(prepared.x_test)
    else:
        raise ValueError(f"Unsupported model family: {candidate.family}")

    values = [float(value) for value in predicted]
    if candidate.target_mode == "load_state_residual":
        values = [
            prediction + anchor
            for prediction, anchor in zip(values, prepared.test_anchors)
        ]
    return [max(0.0, value) for value in values]


def _targets(rows: list[ForecastTrainingRow]) -> list[float]:
    return [row.target_demand_mw for row in rows]


def _candidate_permutation_importance(
    candidate: _ModelCandidate,
    train_rows: list[ForecastTrainingRow],
    test_rows: list[ForecastTrainingRow],
) -> dict[str, float]:
    """Return model evidence without using it for model selection."""

    transform = _fit_feature_transform(train_rows)
    x_train = [_feature_vector(row, transform) for row in train_rows]
    y_train = [
        row.target_demand_mw - _load_state_anchor(row)
        if candidate.target_mode == "load_state_residual"
        else row.target_demand_mw
        for row in train_rows
    ]
    evaluation_rows = test_rows[-min(200, len(test_rows)) :]
    x_evaluate = [_feature_vector(row, transform) for row in evaluation_rows]
    y_evaluate = [
        row.target_demand_mw - _load_state_anchor(row)
        if candidate.target_mode == "load_state_residual"
        else row.target_demand_mw
        for row in evaluation_rows
    ]
    sample_weights = _training_sample_weights(train_rows)

    if candidate.family == "ridge":
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        x_train = scaler.fit_transform(x_train)
        x_evaluate = scaler.transform(x_evaluate)
        model = Ridge(**candidate.params)
        model.fit(x_train, y_train, sample_weight=sample_weights)
        raw_importance = [abs(float(value)) for value in model.coef_]
    elif candidate.family in {
        "hist_gradient_boosting",
        "random_forest",
        "extra_trees",
    }:
        from sklearn.inspection import permutation_importance

        if candidate.family == "hist_gradient_boosting":
            from sklearn.ensemble import HistGradientBoostingRegressor

            model = HistGradientBoostingRegressor(
                random_state=42,
                **candidate.params,
            )
        elif candidate.family == "random_forest":
            from sklearn.ensemble import RandomForestRegressor

            model = RandomForestRegressor(random_state=42, **candidate.params)
        else:
            from sklearn.ensemble import ExtraTreesRegressor

            model = ExtraTreesRegressor(random_state=42, **candidate.params)
        model.fit(x_train, y_train, sample_weight=sample_weights)
        result = permutation_importance(
            model,
            x_evaluate,
            y_evaluate,
            scoring="neg_mean_absolute_error",
            n_repeats=3,
            random_state=42,
        )
        raw_importance = [
            max(0.0, float(value)) for value in result.importances_mean
        ]
    else:
        return {}

    names = _feature_names()
    if len(names) != len(raw_importance):
        return {}
    model_weight = max(0.0, 1.0 - candidate.similarity_weight)
    weighted = {
        name: importance * model_weight
        for name, importance in zip(names, raw_importance)
        if importance > 0
    }
    if candidate.similarity_weight > 0:
        weighted["similar_period_blend"] = candidate.similarity_weight
    total = sum(weighted.values())
    if total <= 0:
        return {}
    normalized = {
        name: round(value / total, 6) for name, value in weighted.items()
    }
    return dict(
        sorted(normalized.items(), key=lambda item: (-item[1], item[0]))[:12]
    )


def _feature_names() -> tuple[str, ...]:
    engineered = (
        "target_hour_sin",
        "target_hour_cos",
        "target_day_sin",
        "target_day_cos",
        "target_weekend",
        "cooling_degree",
        "heating_degree",
        "forecast_cooling_degree",
        "forecast_heating_degree",
        "temperature_normal_c",
        "temperature_deviation_c",
        "forecast_temperature_deviation_c",
        "cooling_humidity_interaction",
        "forecast_cooling_humidity_interaction",
        "cooling_demand_interaction",
        "forecast_cooling_demand_interaction",
        "temperature_rate_positive",
        "temperature_rate_negative",
        "temperature_demand_rate_interaction",
        "forecast_temperature_delta",
        "forecast_humidity_delta",
        "forecast_wind_delta",
        "pressure_delta",
        "rain_probability",
        "rainfall_log",
        "forecast_rainfall_log",
        "current_vs_target_same_hour_average",
        "current_vs_rolling_24h",
        "spin_to_demand_ratio",
        "available_to_demand_ratio",
        "online_to_demand_ratio",
        "online_spare_to_demand_ratio",
        "strict_good_quality",
        "clipped_input_count",
        "missing_input_ratio",
    )
    calendar = (
        "month_sin",
        "month_cos",
        "day_of_year_sin",
        "day_of_year_cos",
        "weekday",
        "weekend",
        "holiday",
        "dry_season",
        "wet_season",
    )
    calendar_interactions = (
        "weekend_hour_sin",
        "weekend_hour_cos",
        "holiday_hour_sin",
        "holiday_hour_cos",
    )
    missing_indicators = tuple(f"{column}_missing" for column in FEATURE_COLUMNS)
    return FEATURE_COLUMNS + engineered + calendar + calendar_interactions + missing_indicators


def _walk_forward_splits(
    rows: list[ForecastTrainingRow],
    fold_count: int = WALK_FORWARD_FOLDS,
) -> list[tuple[list[ForecastTrainingRow], list[ForecastTrainingRow]]]:
    if len(rows) < 2:
        return [(rows, rows)]
    validation_size = max(1, len(rows) // (fold_count + 2))
    initial_train_size = len(rows) - validation_size * fold_count
    if initial_train_size < 1:
        validation_size = 1
        initial_train_size = max(1, len(rows) - fold_count)

    folds: list[tuple[list[ForecastTrainingRow], list[ForecastTrainingRow]]] = []
    for fold_index in range(fold_count):
        validation_start = initial_train_size + fold_index * validation_size
        if validation_start >= len(rows):
            break
        validation_end = min(len(rows), validation_start + validation_size)
        folds.append((rows[:validation_start], rows[validation_start:validation_end]))
    if not folds:
        folds.append((rows[:-1], rows[-1:]))
    return folds


def _select_best_baseline(
    actual: list[float],
    baseline_predictions: dict[str, list[float]],
) -> tuple[str, list[float], ForecastMetrics]:
    scored: list[tuple[str, list[float], ForecastMetrics]] = []
    for name, predictions in baseline_predictions.items():
        metrics = _metrics(actual, predictions)
        scored.append((name, predictions, metrics))
    return min(scored, key=lambda item: (item[2].mae, item[2].rmse, item[2].mape))


def _metrics(actual: list[float], predicted: list[float]) -> ForecastMetrics:
    residuals = [a - p for a, p in zip(actual, predicted)]
    mae = _mae(actual, predicted)
    rmse = math.sqrt(sum(residual * residual for residual in residuals) / len(residuals))
    mape_values = [
        abs((a - p) / a) * 100.0
        for a, p in zip(actual, predicted)
        if a != 0
    ]
    mape = sum(mape_values) / len(mape_values) if mape_values else 0.0
    residual_std = _stddev(residuals)
    peak_error = abs(max(actual) - max(predicted))
    return ForecastMetrics(
        mae=round(mae, 4),
        rmse=round(rmse, 4),
        mape=round(mape, 4),
        residual_std=round(residual_std, 4),
        peak_error_mw=round(peak_error, 4),
    )


def _calibrated_uncertainty(
    metrics: ForecastMetrics,
    actual: list[float],
    predicted: list[float],
    forecast_demand_mw: float,
    horizon_hours: int,
) -> float:
    demand_floor = abs(forecast_demand_mw) * MIN_FORECAST_UNCERTAINTY_DEMAND_RATIO
    horizon_floor = MIN_FORECAST_UNCERTAINTY_MW * math.sqrt(max(1, horizon_hours))
    statistical_floor = max(metrics.mae, metrics.rmse * 0.5)
    absolute_errors = sorted(abs(a - p) for a, p in zip(actual, predicted))
    empirical_sigma = _quantile(absolute_errors, 0.90) / 1.6448536269514722
    uncertainty = max(
        metrics.residual_std,
        statistical_floor,
        empirical_sigma,
        demand_floor,
        horizon_floor,
        MIN_FORECAST_UNCERTAINTY_MW,
    )
    return round(uncertainty, 4)


def _empirical_prediction_interval(
    forecast_demand_mw: float,
    calibration_residuals: tuple[float, ...],
    minimum_half_width: float,
) -> tuple[float, float]:
    lower_offset, upper_offset = _interval_offsets(
        calibration_residuals,
        minimum_half_width,
    )
    return (
        max(0.0, forecast_demand_mw + lower_offset),
        forecast_demand_mw + upper_offset,
    )


def _interval_offsets(
    calibration_residuals: tuple[float, ...],
    minimum_half_width: float,
) -> tuple[float, float]:
    if not calibration_residuals:
        return -minimum_half_width, minimum_half_width
    ordered = sorted(float(value) for value in calibration_residuals)
    absolute = sorted(abs(value) for value in ordered)
    conformal_half_width = _quantile(absolute, FORECAST_INTERVAL_LEVEL)
    half_width = max(minimum_half_width, conformal_half_width)
    return (
        min(_quantile(ordered, 0.10), -half_width),
        max(_quantile(ordered, 0.90), half_width),
    )


def _interval_coverage(
    actual: list[float],
    predicted: list[float],
    calibration_residuals: tuple[float, ...],
    minimum_half_width: float,
) -> float:
    if not actual:
        return 0.0
    lower_offset, upper_offset = _interval_offsets(
        calibration_residuals,
        minimum_half_width,
    )
    covered = sum(
        1
        for observed, estimate in zip(actual, predicted)
        if estimate + lower_offset <= observed <= estimate + upper_offset
    )
    return round(covered / len(actual), 4)


def _input_quality_diagnostics(
    row: ForecastTrainingRow,
    history: list[ForecastTrainingRow],
) -> dict[str, object]:
    missing = [
        column for column in FEATURE_COLUMNS if getattr(row, column) is None
    ]
    outliers: list[str] = []
    for column in FEATURE_COLUMNS:
        raw = getattr(row, column)
        if raw is None or not math.isfinite(float(raw)):
            continue
        values = sorted(
            float(value)
            for historical in history
            if (value := getattr(historical, column)) is not None
            and math.isfinite(float(value))
        )
        if len(values) < 20:
            continue
        if not (
            _quantile(values, 0.005)
            <= float(raw)
            <= _quantile(values, 0.995)
        ):
            outliers.append(column)

    recent = [
        float(value)
        for value in (
            row.lag_1h_demand_mw,
            row.lag_2h_demand_mw,
            row.lag_3h_demand_mw,
        )
        if value is not None and math.isfinite(float(value))
    ]
    abnormal_current = False
    if recent:
        recent_center = median(recent)
        volatility = max(
            15.0,
            float(row.demand_volatility_6h_mw or 0.0),
        )
        abnormal_current = abs(row.current_demand_mw - recent_center) > max(
            4.0 * volatility,
            0.15 * max(1.0, abs(recent_center)),
        )
    if abnormal_current and "current_demand_mw" not in outliers:
        outliers.append("current_demand_mw")

    status = (
        "OUTLIER_GUARDED"
        if abnormal_current
        else "OUTLIER_CLIPPED"
        if outliers
        else "DEGRADED"
        if row.source_quality_status != "GOOD" or len(missing) > len(FEATURE_COLUMNS) // 4
        else "GOOD"
    )
    return {
        "status": status,
        "source_quality_status": row.source_quality_status,
        "missing_feature_count": len(missing),
        "missing_features": missing,
        "outlier_feature_count": len(outliers),
        "outlier_features": sorted(outliers),
        "abnormal_current_demand": abnormal_current,
    }


def _guard_forecast_for_input_quality(
    forecast_demand_mw: float,
    similar_forecast_mw: float | None,
    similar_spread_mw: float | None,
    metrics: ForecastMetrics,
    input_quality: dict[str, object],
) -> float:
    if (
        not bool(input_quality.get("abnormal_current_demand"))
        or similar_forecast_mw is None
    ):
        return forecast_demand_mw
    maximum_deviation = max(
        25.0,
        2.0 * metrics.rmse,
        2.0 * float(similar_spread_mw or 0.0),
    )
    return max(
        0.0,
        min(
            similar_forecast_mw + maximum_deviation,
            max(
                similar_forecast_mw - maximum_deviation,
                forecast_demand_mw,
            ),
        ),
    )


def _mae(actual: list[float], predicted: list[float]) -> float:
    return sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual)


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = sum(values) / len(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _feature_fill_values(rows: list[ForecastTrainingRow]) -> dict[str, float]:
    fill_values: dict[str, float] = {}
    for column in FEATURE_COLUMNS:
        values = [
            float(value)
            for row in rows
            if (value := getattr(row, column)) is not None
        ]
        fill_values[column] = (
            sum(values) / len(values)
            if values
            else FEATURE_DEFAULTS.get(column, 0.0)
        )
    return fill_values


def _fit_feature_transform(rows: list[ForecastTrainingRow]) -> _FeatureTransform:
    fill_values = _feature_fill_values(rows)
    lower_bounds: dict[str, float] = {}
    upper_bounds: dict[str, float] = {}
    for column in FEATURE_COLUMNS:
        values = sorted(
            float(value)
            for row in rows
            if (value := getattr(row, column)) is not None
            and math.isfinite(float(value))
        )
        if len(values) < 20:
            continue
        lower = _quantile(values, 0.005)
        upper = _quantile(values, 0.995)
        if upper > lower:
            lower_bounds[column] = lower
            upper_bounds[column] = upper
    return _FeatureTransform(
        fill_values=fill_values,
        lower_bounds=lower_bounds,
        upper_bounds=upper_bounds,
        temperature_profile=_fit_temperature_profile(rows),
    )


def _fit_temperature_profile(
    rows: list[ForecastTrainingRow],
) -> _TemperatureProfile:
    ordered = sorted(rows, key=lambda row: row.feature_timestamp)
    samples = [
        row
        for row in ordered
        if _row_temperature(row) is not None
        and math.isfinite(float(_row_temperature(row)))
    ]
    temperatures = sorted(float(_row_temperature(row)) for row in samples)
    global_normal = median(temperatures) if temperatures else 28.0
    normal_by_hour = _temperature_normals_by_hour(samples, global_normal)
    normal_by_season_hour = _temperature_normals_by_season_hour(samples)
    if len(samples) < 48:
        return _TemperatureProfile(
            balance_point_c=global_normal,
            global_normal_c=global_normal,
            normal_by_hour=normal_by_hour,
            normal_by_season_hour=normal_by_season_hour,
            selection_mae_mw=None,
            no_temperature_mae_mw=None,
            candidate_metrics={},
            sample_count=len(samples),
        )

    split_index = min(len(samples) - 12, max(36, int(len(samples) * 0.8)))
    selection_train = samples[:split_index]
    selection_validation = samples[split_index:]
    train_temperatures = sorted(
        float(_row_temperature(row)) for row in selection_train
    )
    candidate_quantiles = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60)
    candidates = sorted(
        {
            round(_quantile(train_temperatures, quantile), 2)
            for quantile in candidate_quantiles
        }
    )
    baseline_lookup, baseline_hour_lookup, baseline_global = (
        _temperature_selection_baselines(selection_train)
    )
    no_temperature_predictions = [
        _temperature_baseline_prediction(
            row,
            baseline_lookup,
            baseline_hour_lookup,
            baseline_global,
        )
        for row in selection_validation
    ]
    no_temperature_metrics = _metrics(
        _targets(selection_validation),
        no_temperature_predictions,
    )
    scored: list[tuple[float, ForecastMetrics]] = []
    for balance_point in candidates:
        predictions = _temperature_adjusted_predictions(
            selection_train,
            selection_validation,
            balance_point,
            baseline_lookup,
            baseline_hour_lookup,
            baseline_global,
        )
        scored.append(
            (
                balance_point,
                _metrics(_targets(selection_validation), predictions),
            )
        )
    selected_balance, selected_metrics = min(
        scored,
        key=lambda item: (item[1].mae, item[1].rmse, item[0]),
    )
    return _TemperatureProfile(
        balance_point_c=selected_balance,
        global_normal_c=global_normal,
        normal_by_hour=normal_by_hour,
        normal_by_season_hour=normal_by_season_hour,
        selection_mae_mw=selected_metrics.mae,
        no_temperature_mae_mw=no_temperature_metrics.mae,
        candidate_metrics={
            f"{balance_point:.2f}C": {
                "mae": metrics.mae,
                "rmse": metrics.rmse,
            }
            for balance_point, metrics in scored
        },
        sample_count=len(samples),
    )


def _row_temperature(row: ForecastTrainingRow) -> float | None:
    value = (
        row.forecast_temperature_c
        if row.forecast_temperature_c is not None
        else row.temperature_c
    )
    return float(value) if value is not None else None


def _temperature_normals_by_hour(
    rows: list[ForecastTrainingRow],
    fallback: float,
) -> dict[int, float]:
    result: dict[int, float] = {}
    for hour in range(24):
        values = [
            float(value)
            for row in rows
            if row.target_timestamp.hour == hour
            and (value := _row_temperature(row)) is not None
        ]
        result[hour] = median(values) if values else fallback
    return result


def _temperature_normals_by_season_hour(
    rows: list[ForecastTrainingRow],
) -> dict[tuple[str, int], float]:
    grouped: dict[tuple[str, int], list[float]] = {}
    for row in rows:
        temperature = _row_temperature(row)
        if temperature is None:
            continue
        season = calendar_context(
            row.target_timestamp,
            settings.FORECAST_EXTRA_HOLIDAY_DATES,
        ).season
        grouped.setdefault((season, row.target_timestamp.hour), []).append(
            temperature
        )
    return {
        key: median(values)
        for key, values in grouped.items()
        if len(values) >= 3
    }


def _temperature_selection_baselines(
    rows: list[ForecastTrainingRow],
) -> tuple[dict[tuple[int, str, str], float], dict[int, float], float]:
    grouped: dict[tuple[int, str, str], list[float]] = {}
    hourly: dict[int, list[float]] = {}
    for row in rows:
        context = calendar_context(
            row.target_timestamp,
            settings.FORECAST_EXTRA_HOLIDAY_DATES,
        )
        key = (row.target_timestamp.hour, context.day_type, context.season)
        grouped.setdefault(key, []).append(float(row.target_demand_mw))
        hourly.setdefault(row.target_timestamp.hour, []).append(
            float(row.target_demand_mw)
        )
    global_average = mean(float(row.target_demand_mw) for row in rows)
    return (
        {key: mean(values) for key, values in grouped.items()},
        {hour: mean(values) for hour, values in hourly.items()},
        global_average,
    )


def _temperature_baseline_prediction(
    row: ForecastTrainingRow,
    grouped: dict[tuple[int, str, str], float],
    hourly: dict[int, float],
    fallback: float,
) -> float:
    context = calendar_context(
        row.target_timestamp,
        settings.FORECAST_EXTRA_HOLIDAY_DATES,
    )
    return grouped.get(
        (row.target_timestamp.hour, context.day_type, context.season),
        hourly.get(row.target_timestamp.hour, fallback),
    )


def _temperature_adjusted_predictions(
    train_rows: list[ForecastTrainingRow],
    validation_rows: list[ForecastTrainingRow],
    balance_point_c: float,
    baseline_lookup: dict[tuple[int, str, str], float],
    baseline_hour_lookup: dict[int, float],
    baseline_global: float,
) -> list[float]:
    import numpy as np

    temperatures = sorted(float(_row_temperature(row)) for row in train_rows)
    global_normal = median(temperatures)
    normal_by_hour = _temperature_normals_by_hour(train_rows, global_normal)
    normal_by_season_hour = _temperature_normals_by_season_hour(train_rows)

    def effect_vector(row: ForecastTrainingRow) -> list[float]:
        temperature = float(_row_temperature(row))
        humidity = _fallback_if_none(
            row.forecast_humidity_percent,
            _fallback_if_none(row.humidity_percent, 70.0),
        )
        context = calendar_context(
            row.target_timestamp,
            settings.FORECAST_EXTRA_HOLIDAY_DATES,
        )
        normal = normal_by_season_hour.get(
            (context.season, row.target_timestamp.hour),
            normal_by_hour.get(row.target_timestamp.hour, global_normal),
        )
        cooling = max(0.0, temperature - balance_point_c)
        heating = max(0.0, balance_point_c - temperature)
        return [
            cooling,
            heating,
            cooling * humidity / 100.0,
            temperature - normal,
            _fallback_if_none(row.temperature_rate_1h_c, 0.0),
        ]

    x_train = np.asarray([effect_vector(row) for row in train_rows], dtype=float)
    baselines = np.asarray(
        [
            _temperature_baseline_prediction(
                row,
                baseline_lookup,
                baseline_hour_lookup,
                baseline_global,
            )
            for row in train_rows
        ],
        dtype=float,
    )
    targets = np.asarray(_targets(train_rows), dtype=float) - baselines
    feature_mean = x_train.mean(axis=0)
    feature_scale = x_train.std(axis=0)
    feature_scale[feature_scale < 1e-9] = 1.0
    normalized = (x_train - feature_mean) / feature_scale
    design = np.column_stack((np.ones(len(normalized)), normalized))
    penalty = np.eye(design.shape[1]) * 10.0
    penalty[0, 0] = 0.0
    try:
        coefficients = np.linalg.solve(
            design.T @ design + penalty,
            design.T @ targets,
        )
    except np.linalg.LinAlgError:
        coefficients = np.linalg.lstsq(design, targets, rcond=None)[0]

    x_validation = np.asarray(
        [effect_vector(row) for row in validation_rows],
        dtype=float,
    )
    validation_design = np.column_stack(
        (
            np.ones(len(x_validation)),
            (x_validation - feature_mean) / feature_scale,
        )
    )
    adjustments = validation_design @ coefficients
    return [
        max(
            0.0,
            _temperature_baseline_prediction(
                row,
                baseline_lookup,
                baseline_hour_lookup,
                baseline_global,
            )
            + float(adjustment),
        )
        for row, adjustment in zip(validation_rows, adjustments)
    ]


def _feature_vector(
    row: ForecastTrainingRow,
    transform_or_fill_values: _FeatureTransform | dict[str, float],
) -> list[float]:
    transform = (
        transform_or_fill_values
        if isinstance(transform_or_fill_values, _FeatureTransform)
        else _FeatureTransform(
            fill_values=transform_or_fill_values,
            lower_bounds={},
            upper_bounds={},
            temperature_profile=_TemperatureProfile(
                balance_point_c=transform_or_fill_values["temperature_c"],
                global_normal_c=transform_or_fill_values["temperature_c"],
                normal_by_hour={},
                normal_by_season_hour={},
                selection_mae_mw=None,
                no_temperature_mae_mw=None,
                candidate_metrics={},
                sample_count=0,
            ),
        )
    )
    fill_values = transform.fill_values
    vector: list[float] = []
    for column in FEATURE_COLUMNS:
        vector.append(transform.value(row, column))
    target_hour_angle = 2.0 * math.pi * row.target_timestamp.hour / 24.0
    target_day_angle = 2.0 * math.pi * row.target_timestamp.weekday() / 7.0
    current_demand = max(0.0, transform.value(row, "current_demand_mw"))
    demand_scale = current_demand / 1000.0
    temperature = transform.value(row, "temperature_c")
    humidity = transform.value(row, "humidity_percent")
    forecast_temperature = (
        temperature
        if row.forecast_temperature_c is None
        else transform.value(row, "forecast_temperature_c")
    )
    forecast_humidity = (
        humidity
        if row.forecast_humidity_percent is None
        else transform.value(row, "forecast_humidity_percent")
    )
    wind_speed = max(0.0, transform.value(row, "wind_speed_kmh"))
    forecast_wind_speed = max(
        0.0,
        wind_speed
        if row.forecast_wind_speed_kmh is None
        else transform.value(row, "forecast_wind_speed_kmh"),
    )
    pressure = transform.value(row, "pressure_hpa")
    rain_probability = max(
        0.0,
        min(
            100.0,
            transform.value(row, "forecast_precipitation_probability_percent"),
        ),
    )
    rainfall = max(0.0, transform.value(row, "rainfall_mm_hr"))
    forecast_rainfall = max(
        0.0,
        transform.value(row, "forecast_rainfall_mm_hr"),
    )
    balance_point = transform.temperature_profile.balance_point_c
    normal_temperature = transform.temperature_profile.normal_for(
        row.target_timestamp
    )
    cooling_degree = max(0.0, temperature - balance_point)
    heating_degree = max(0.0, balance_point - temperature)
    forecast_cooling_degree = max(0.0, forecast_temperature - balance_point)
    forecast_heating_degree = max(0.0, balance_point - forecast_temperature)
    demand_rate = transform.value(row, "demand_rate_1h_mw")
    temperature_rate = transform.value(row, "temperature_rate_1h_c")
    target_same_hour = (
        current_demand
        if row.target_same_hour_7d_average_mw is None
        else transform.value(row, "target_same_hour_7d_average_mw")
    )
    rolling_24h = (
        current_demand
        if row.rolling_24h_demand_mw is None
        else transform.value(row, "rolling_24h_demand_mw")
    )
    demand_denominator = max(1.0, current_demand)
    clipped_input_count = sum(
        1
        for column in FEATURE_COLUMNS
        if getattr(row, column) is not None
        and abs(float(getattr(row, column)) - transform.value(row, column)) > 1e-9
    )
    missing_input_count = sum(
        1 for column in FEATURE_COLUMNS if getattr(row, column) is None
    )
    vector.extend(
        (
            math.sin(target_hour_angle),
            math.cos(target_hour_angle),
            math.sin(target_day_angle),
            math.cos(target_day_angle),
            1.0 if row.target_timestamp.weekday() >= 5 else 0.0,
            cooling_degree,
            heating_degree,
            forecast_cooling_degree,
            forecast_heating_degree,
            normal_temperature,
            temperature - normal_temperature,
            forecast_temperature - normal_temperature,
            cooling_degree * humidity / 100.0,
            forecast_cooling_degree * forecast_humidity / 100.0,
            cooling_degree * demand_scale,
            forecast_cooling_degree * demand_scale,
            max(0.0, temperature_rate),
            min(0.0, temperature_rate),
            temperature_rate * demand_rate / 100.0,
            forecast_temperature - temperature,
            forecast_humidity - humidity,
            forecast_wind_speed - wind_speed,
            pressure - 1013.25,
            rain_probability / 100.0,
            math.log1p(rainfall),
            math.log1p(forecast_rainfall),
            current_demand - target_same_hour,
            current_demand - rolling_24h,
            transform.value(row, "spinning_reserve_mw") / demand_denominator,
            transform.value(row, "available_capacity_mw") / demand_denominator,
            transform.value(row, "online_capacity_mw") / demand_denominator,
            transform.value(row, "online_spare_mw") / demand_denominator,
            1.0 if row.source_quality_status == "GOOD" else 0.0,
            float(clipped_input_count),
            missing_input_count / len(FEATURE_COLUMNS),
        )
    )
    vector.extend(
        calendar_feature_vector(
            row.target_timestamp,
            settings.FORECAST_EXTRA_HOLIDAY_DATES,
        )
    )
    target_context = calendar_context(
        row.target_timestamp,
        settings.FORECAST_EXTRA_HOLIDAY_DATES,
    )
    vector.extend(
        (
            math.sin(target_hour_angle)
            * (1.0 if target_context.day_type == "WEEKEND" else 0.0),
            math.cos(target_hour_angle)
            * (1.0 if target_context.day_type == "WEEKEND" else 0.0),
            math.sin(target_hour_angle)
            * (1.0 if target_context.day_type == "HOLIDAY" else 0.0),
            math.cos(target_hour_angle)
            * (1.0 if target_context.day_type == "HOLIDAY" else 0.0),
        )
    )
    for column in FEATURE_COLUMNS:
        vector.append(1.0 if getattr(row, column) is None else 0.0)
    return vector


def _fallback_if_none(value: float | None, fallback: float) -> float:
    return fallback if value is None else value


def _load_state_anchor(row: ForecastTrainingRow) -> float:
    historical_values = [
        float(value)
        for value in (
            row.target_same_hour_7d_average_mw,
            row.target_lag_24h_demand_mw,
            row.target_lag_48h_demand_mw,
            row.target_lag_168h_demand_mw,
        )
        if value is not None and math.isfinite(float(value))
    ]
    if historical_values:
        return max(0.0, median(historical_values))
    return max(0.0, float(row.current_demand_mw))


def _filled(value: float | None, fallback: float) -> float:
    return fallback if value is None else float(value)


def _quantile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * max(0.0, min(1.0, quantile))
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _median_residual(actual: list[float], predicted: list[float]) -> float:
    residuals = [a - p for a, p in zip(actual, predicted)]
    return median(residuals) if residuals else 0.0


def _apply_bias(predictions: list[float], bias: float) -> list[float]:
    return [max(0.0, prediction + bias) for prediction in predictions]


def _training_sample_weights(rows: list[ForecastTrainingRow]) -> list[float]:
    if not rows:
        return []
    latest_timestamp = max(row.feature_timestamp for row in rows)
    weights: list[float] = []
    for row in rows:
        age_hours = max(
            0.0,
            (latest_timestamp - row.feature_timestamp).total_seconds() / 3600.0,
        )
        recency_weight = 0.5 ** (age_hours / RECENCY_HALF_LIFE_HOURS)
        quality = row.source_quality_status.upper()
        if quality == "GOOD":
            quality_weight = 1.0
        elif quality.startswith("SCADA_PARTIAL"):
            quality_weight = SCADA_PARTIAL_WEIGHT
        elif quality in {"SCADA_ACCEPTED", "USABLE_WITH_WARNING"}:
            quality_weight = SCADA_ACCEPTED_WEIGHT
        elif quality in {
            "WEATHER_DEGRADED",
            "SCADA_ACCEPTED_WEATHER_DEGRADED",
            "WEATHER_BASELINE",
            "SCADA_ACCEPTED_WEATHER_BASELINE",
        }:
            quality_weight = WEATHER_DEGRADED_WEIGHT
        else:
            quality_weight = LEGACY_DEGRADED_WEIGHT
        weights.append(recency_weight * quality_weight)
    average_weight = sum(weights) / len(weights)
    if average_weight <= 0:
        return [1.0 for _ in rows]
    return [weight / average_weight for weight in weights]


def _temperature_load_correlation(
    rows: list[ForecastTrainingRow],
) -> float | None:
    samples = [
        (
            float(row.forecast_temperature_c or row.temperature_c),
            float(row.target_demand_mw),
            (
                row.target_timestamp.hour,
                calendar_context(
                    row.target_timestamp,
                    settings.FORECAST_EXTRA_HOLIDAY_DATES,
                ).day_type,
            ),
        )
        for row in rows
        if (row.forecast_temperature_c is not None or row.temperature_c is not None)
    ]
    if len(samples) < 3:
        return None
    grouped: dict[tuple[int, str], list[tuple[float, float]]] = {}
    for temperature, demand, key in samples:
        grouped.setdefault(key, []).append((temperature, demand))
    centered: list[tuple[float, float]] = []
    for values in grouped.values():
        if len(values) < 2:
            continue
        average_temperature = mean(value[0] for value in values)
        average_demand = mean(value[1] for value in values)
        centered.extend(
            (
                temperature - average_temperature,
                demand - average_demand,
            )
            for temperature, demand in values
        )
    if len(centered) >= 3:
        centered_correlation = _pearson_correlation(centered)
        if centered_correlation is not None:
            return centered_correlation
    return _pearson_correlation([(row[0], row[1]) for row in samples])


def _pearson_correlation(values: list[tuple[float, float]]) -> float | None:
    if len(values) < 3:
        return None
    temperatures = [value[0] for value in values]
    demands = [value[1] for value in values]
    average_temperature = mean(temperatures)
    average_demand = mean(demands)
    covariance = sum(
        (temperature - average_temperature) * (demand - average_demand)
        for temperature, demand in values
    )
    temperature_variance = sum(
        (temperature - average_temperature) ** 2 for temperature in temperatures
    )
    demand_variance = sum((demand - average_demand) ** 2 for demand in demands)
    denominator = math.sqrt(temperature_variance * demand_variance)
    if denominator <= 0:
        return None
    return round(max(-1.0, min(1.0, covariance / denominator)), 4)


def _contributing_factors(
    row: ForecastTrainingRow,
    history: list[ForecastTrainingRow],
    active_model: str,
    best_baseline: str,
    forecast_demand_mw: float,
    baseline_forecast_mw: float,
    temperature_correlation: float | None,
    similar_forecast_mw: float | None,
    similar_count: int,
) -> list[str]:
    factors: list[str] = []
    context = calendar_context(
        row.target_timestamp,
        settings.FORECAST_EXTRA_HOLIDAY_DATES,
    )
    calendar_label = context.day_type.lower()
    if context.holiday_name:
        calendar_label = context.holiday_name
    factors.append(
        f"Target is a {calendar_label} hour in the {context.season.lower()} season."
    )

    forecast_temperature = row.forecast_temperature_c or row.temperature_c
    historical_temperatures = [
        value
        for historical_row in history
        if (
            value := historical_row.forecast_temperature_c
            or historical_row.temperature_c
        )
        is not None
    ]
    if forecast_temperature is not None and historical_temperatures:
        temperature_delta = float(forecast_temperature) - median(historical_temperatures)
        direction = "above" if temperature_delta >= 0 else "below"
        correlation_text = (
            f"; adjusted temperature/load correlation is {temperature_correlation:+.2f}"
            if temperature_correlation is not None
            else ""
        )
        factors.append(
            f"Forecast temperature is {abs(temperature_delta):.1f}C {direction} the historical median{correlation_text}."
        )

    demand_rate = row.demand_rate_1h_mw
    if demand_rate is not None:
        direction = "rising" if demand_rate > 0 else "falling" if demand_rate < 0 else "steady"
        factors.append(
            f"Recent demand is {direction} at {abs(demand_rate):.1f} MW per hour."
        )

    if similar_forecast_mw is not None and similar_count:
        factors.append(
            f"{similar_count} comparable historical periods indicate approximately {similar_forecast_mw:.0f} MW."
        )

    model_delta = forecast_demand_mw - baseline_forecast_mw
    factors.append(
        f"{active_model} is {model_delta:+.0f} MW relative to the selected {best_baseline} baseline."
    )
    return factors
