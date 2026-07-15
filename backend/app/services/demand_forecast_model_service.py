from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

from sqlalchemy import delete, select

from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.demand_forecast import DemandForecastResult, ForecastTrainingRow
from app.services.demand_forecast_baselines import (
    hourly_average_forecast,
    hourly_average_lookup,
    persistence_forecast,
    rolling_trend_forecast,
    same_hour_yesterday_forecast,
    trend_adjusted_persistence_forecast,
)
from app.services.forecast_dataset_service import ForecastDatasetService

MODEL_VERSION = "demand-forecast-v2.0"
FEATURE_PROFILE = "demand_weather_v2"
MIN_FORECAST_UNCERTAINTY_MW = 5.0
MIN_FORECAST_UNCERTAINTY_DEMAND_RATIO = 0.015
MIN_ML_TRAIN_ROWS = 48
MIN_ML_IMPROVEMENT_RATIO = 0.02
WALK_FORWARD_FOLDS = 3
RECENCY_HALF_LIFE_HOURS = 14 * 24
WEATHER_DEGRADED_WEIGHT = 0.7
LEGACY_DEGRADED_WEIGHT = 0.5
SCADA_ACCEPTED_WEIGHT = 0.8
TRUSTED_HISTORY_HOURS = 60 * 24
FEATURE_COLUMNS = (
    "current_demand_mw",
    "lag_1h_demand_mw",
    "lag_2h_demand_mw",
    "lag_3h_demand_mw",
    "lag_6h_demand_mw",
    "lag_24h_demand_mw",
    "rolling_3h_demand_mw",
    "rolling_6h_demand_mw",
    "rolling_24h_demand_mw",
    "demand_rate_1h_mw",
    "demand_rate_3h_mw",
    "demand_rate_6h_mw",
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
}


@dataclass(frozen=True)
class ForecastMetrics:
    mae: float
    rmse: float
    mape: float
    residual_std: float


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
    candidate_metrics: dict[str, dict[str, float | str]] | None = None


@dataclass(frozen=True)
class DemandForecastTrainingResult:
    results: list[HorizonModelResult]


class DemandForecastModelService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

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

        best_baseline, baseline_bias = self._select_baseline_walk_forward(train_rows)
        baseline_predictions = self._baseline_predictions(train_rows, test_rows)
        best_predictions = _apply_bias(
            baseline_predictions[best_baseline],
            baseline_bias,
        )
        baseline_metrics = _metrics(_targets(test_rows), best_predictions)

        active_model = best_baseline
        mode = "BASELINE_ACTIVE"
        forecast_prediction = best_predictions[-1]
        active_predictions = best_predictions
        active_metrics = baseline_metrics
        ml_metrics = None
        ml_beats_baseline = False

        ml_prediction_result = self._try_ml_model(train_rows, test_rows)
        if ml_prediction_result is not None:
            ml_predictions, latest_prediction = ml_prediction_result
            ml_metrics = _metrics(_targets(test_rows), ml_predictions)
            improvement_threshold = 1.0 - MIN_ML_IMPROVEMENT_RATIO
            ml_beats_baseline = (
                ml_metrics.mae < baseline_metrics.mae * improvement_threshold
                and ml_metrics.rmse < baseline_metrics.rmse * improvement_threshold
            )
            if ml_beats_baseline:
                active_model = "HistGradientBoostingRegressor"
                mode = "ML_ACTIVE"
                forecast_prediction = latest_prediction
                active_predictions = ml_predictions
                active_metrics = ml_metrics

        latest_row = test_rows[-1]
        forecast_timestamp = latest_row.target_timestamp
        baseline_forecast = best_predictions[-1]
        if inference_row is not None:
            forecast_timestamp = inference_row.target_timestamp
            _, inference_baseline_bias = self._baseline_bias_walk_forward(
                rows,
                best_baseline,
            )
            raw_baseline_forecast = self._baseline_predictions(
                rows,
                [inference_row],
            )[best_baseline][0]
            baseline_forecast = max(
                0.0,
                raw_baseline_forecast + inference_baseline_bias,
            )
            forecast_prediction = baseline_forecast
            if ml_beats_baseline:
                inference_result = self._try_ml_model(rows, [inference_row])
                if inference_result is not None:
                    forecast_prediction = inference_result[0][0]
            if inference_row.source_quality_status != "GOOD":
                mode = f"{mode}_DEGRADED"

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
                "active": {
                    "model": active_model,
                    "mae": active_metrics.mae,
                    "rmse": active_metrics.rmse,
                    "mape": active_metrics.mape,
                },
                "baseline": {
                    "model": best_baseline,
                    "mae": baseline_metrics.mae,
                    "rmse": baseline_metrics.rmse,
                    "mape": baseline_metrics.mape,
                },
            },
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
            "hourly_average": [],
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
            predictions["hourly_average"].append(
                _fallback_if_none(
                    hourly_average_forecast(row, hourly_lookup),
                    fallback_average,
                )
            )
        return predictions

    def _select_baseline_walk_forward(
        self,
        rows: list[ForecastTrainingRow],
    ) -> tuple[str, float]:
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
        actual: list[float] = []
        predicted: list[float] = []
        for fold_train, fold_validation in _walk_forward_splits(rows):
            fold_predictions = self._baseline_predictions(
                fold_train,
                fold_validation,
            )
            actual.extend(_targets(fold_validation))
            predicted.extend(fold_predictions[baseline_name])
        return predicted, _median_residual(actual, predicted)

    def _try_ml_model(
        self,
        train_rows: list[ForecastTrainingRow],
        test_rows: list[ForecastTrainingRow],
    ) -> tuple[list[float], float] | None:
        if len(train_rows) < MIN_ML_TRAIN_ROWS:
            return None
        try:
            from sklearn.ensemble import HistGradientBoostingRegressor
        except Exception:
            return None

        validation_folds = _walk_forward_splits(train_rows)
        smallest_fold = min(len(fold_train) for fold_train, _ in validation_folds)
        min_samples_leaf = max(5, min(20, smallest_fold // 12))
        candidates = (
            {
                "loss": "absolute_error",
                "learning_rate": 0.05,
                "max_iter": 250,
                "max_leaf_nodes": 15,
                "min_samples_leaf": min_samples_leaf,
                "l2_regularization": 1.0,
            },
            {
                "loss": "squared_error",
                "learning_rate": 0.05,
                "max_iter": 250,
                "max_leaf_nodes": 15,
                "min_samples_leaf": min_samples_leaf,
                "l2_regularization": 2.0,
            },
        )
        selected_params = min(
            candidates,
            key=lambda params: self._walk_forward_ml_score(
                HistGradientBoostingRegressor,
                validation_folds,
                params,
            ),
        )
        validation_actual, validation_predictions = self._walk_forward_ml_predictions(
            HistGradientBoostingRegressor,
            validation_folds,
            selected_params,
        )
        bias = _median_residual(validation_actual, validation_predictions)
        predictions = self._fit_ml_predictions(
            HistGradientBoostingRegressor,
            train_rows,
            test_rows,
            selected_params,
        )
        corrected = _apply_bias(predictions, bias)
        return corrected, corrected[-1]

    def _walk_forward_ml_score(
        self,
        model_class: Any,
        folds: list[tuple[list[ForecastTrainingRow], list[ForecastTrainingRow]]],
        params: dict[str, Any],
    ) -> tuple[float, float, float]:
        actual, predicted = self._walk_forward_ml_predictions(
            model_class,
            folds,
            params,
        )
        corrected = _apply_bias(predicted, _median_residual(actual, predicted))
        metrics = _metrics(actual, corrected)
        return metrics.mae, metrics.rmse, metrics.mape

    def _walk_forward_ml_predictions(
        self,
        model_class: Any,
        folds: list[tuple[list[ForecastTrainingRow], list[ForecastTrainingRow]]],
        params: dict[str, Any],
    ) -> tuple[list[float], list[float]]:
        actual: list[float] = []
        predicted: list[float] = []
        for fold_train, fold_validation in folds:
            actual.extend(_targets(fold_validation))
            predicted.extend(
                self._fit_ml_predictions(
                    model_class,
                    fold_train,
                    fold_validation,
                    params,
                )
            )
        return actual, predicted

    @staticmethod
    def _fit_ml_predictions(
        model_class: Any,
        train_rows: list[ForecastTrainingRow],
        test_rows: list[ForecastTrainingRow],
        params: dict[str, Any],
    ) -> list[float]:
        fill_values = _feature_fill_values(train_rows)
        x_train = [_feature_vector(row, fill_values) for row in train_rows]
        y_train = [row.target_demand_mw for row in train_rows]
        x_test = [_feature_vector(row, fill_values) for row in test_rows]
        sample_weights = _training_sample_weights(train_rows)

        model = model_class(random_state=42, **params)
        model.fit(x_train, y_train, sample_weight=sample_weights)
        return [max(0.0, float(value)) for value in model.predict(x_test)]


def _targets(rows: list[ForecastTrainingRow]) -> list[float]:
    return [row.target_demand_mw for row in rows]


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
    return ForecastMetrics(
        mae=round(mae, 4),
        rmse=round(rmse, 4),
        mape=round(mape, 4),
        residual_std=round(residual_std, 4),
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


def _feature_vector(
    row: ForecastTrainingRow,
    fill_values: dict[str, float],
) -> list[float]:
    vector: list[float] = []
    for column in FEATURE_COLUMNS:
        value = getattr(row, column)
        vector.append(float(value) if value is not None else fill_values[column])
    target_hour_angle = 2.0 * math.pi * row.target_timestamp.hour / 24.0
    target_day_angle = 2.0 * math.pi * row.target_timestamp.weekday() / 7.0
    temperature = _filled(row.temperature_c, fill_values["temperature_c"])
    humidity = _filled(row.humidity_percent, fill_values["humidity_percent"])
    forecast_temperature = _filled(row.forecast_temperature_c, temperature)
    forecast_humidity = _filled(row.forecast_humidity_percent, humidity)
    wind_speed = max(0.0, _filled(row.wind_speed_kmh, 0.0))
    forecast_wind_speed = max(
        0.0,
        _filled(row.forecast_wind_speed_kmh, wind_speed),
    )
    pressure = _filled(row.pressure_hpa, 1013.25)
    rain_probability = max(
        0.0,
        min(
            100.0,
            _filled(row.forecast_precipitation_probability_percent, 0.0),
        ),
    )
    rainfall = max(0.0, _filled(row.rainfall_mm_hr, 0.0))
    forecast_rainfall = max(0.0, _filled(row.forecast_rainfall_mm_hr, 0.0))
    vector.extend(
        (
            math.sin(target_hour_angle),
            math.cos(target_hour_angle),
            math.sin(target_day_angle),
            math.cos(target_day_angle),
            1.0 if row.target_timestamp.weekday() >= 5 else 0.0,
            max(0.0, temperature - 24.0),
            max(0.0, forecast_temperature - 24.0),
            max(0.0, temperature - 24.0) * humidity / 100.0,
            forecast_temperature - temperature,
            forecast_humidity - humidity,
            forecast_wind_speed - wind_speed,
            pressure - 1013.25,
            rain_probability / 100.0,
            math.log1p(rainfall),
            math.log1p(forecast_rainfall),
            1.0 if row.source_quality_status == "GOOD" else 0.0,
        )
    )
    for column in FEATURE_COLUMNS:
        vector.append(1.0 if getattr(row, column) is None else 0.0)
    return vector


def _fallback_if_none(value: float | None, fallback: float) -> float:
    return fallback if value is None else value


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
        elif quality in {"SCADA_ACCEPTED", "USABLE_WITH_WARNING"}:
            quality_weight = SCADA_ACCEPTED_WEIGHT
        elif quality in {
            "WEATHER_DEGRADED",
            "SCADA_ACCEPTED_WEATHER_DEGRADED",
        }:
            quality_weight = WEATHER_DEGRADED_WEIGHT
        else:
            quality_weight = LEGACY_DEGRADED_WEIGHT
        weights.append(recency_weight * quality_weight)
    average_weight = sum(weights) / len(weights)
    if average_weight <= 0:
        return [1.0 for _ in rows]
    return [weight / average_weight for weight in weights]
