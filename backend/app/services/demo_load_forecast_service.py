from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean, median, pstdev
from typing import Any, Protocol, Sequence

import numpy as np


logger = logging.getLogger(__name__)


# Replay is a prototype and some cursor positions expose only a short history.
# Seven completed days are enough to tune Ridge, while activation still requires
# an improvement on a separate newest chronological holdout.
MIN_TRAIN_ROWS = 24 * 7
MIN_MODEL_IMPROVEMENT = 0.02
MIN_MODEL_IMPROVEMENT_MW = 0.1
MIN_UNCERTAINTY_MW = 12.0
FORECAST_INTERVAL_COVERAGE = 0.90
MIN_REQUIRED_HISTORY_ROWS = 48
MIN_LOAD_HISTORY_ROWS = 24
RIDGE_PENALTIES = (8.0, 16.0, 32.0, 64.0)
ENSEMBLE_RIDGE_WEIGHTS = (0.25, 0.4, 0.5, 0.6, 0.75)
DEMO_FORECAST_MODEL_VERSION = "demo-load-forecast-v3.1"
ML_MODEL_NAMES = (
    "LoadStateWeatherRidge",
    "LoadStateWeatherEnsemble",
)


class DemandWeatherObservation(Protocol):
    timestamp: datetime
    demand_mw: float
    temperature_c: float
    humidity_percent: float
    rainfall_mm_hr: float
    cloud_cover_percent: float
    wind_speed_kmh: float
    pressure_hpa: float


@dataclass(frozen=True)
class DemoForecastPoint:
    timestamp: datetime
    forecast_demand_mw: float
    historical_average_mw: float
    actual_demand_mw: float | None
    uncertainty_mw: float
    weather_impact_mw: float
    weather_confidence: float
    weather_source_count: int


@dataclass(frozen=True)
class DemoForecastResult:
    points: list[DemoForecastPoint]
    model_name: str
    model_mode: str
    mae_mw: float
    baseline_mae_mw: float
    residual_std_mw: float
    trained_through: datetime
    training_rows: int
    weather_features: tuple[str, ...]


class DemoLoadForecastService:
    """Chronological load-state and weather forecasting for replay data."""

    WEATHER_FEATURES = (
        "temperature_c",
        "humidity_percent",
        "rainfall_mm_hr",
        "cloud_cover_percent",
        "wind_speed_kmh",
        "pressure_hpa",
    )
    LOAD_STATE_FEATURES = (
        "lag_1h_demand_mw",
        "lag_2h_demand_mw",
        "lag_3h_demand_mw",
        "lag_6h_demand_mw",
        "lag_24h_demand_mw",
        "lag_48h_demand_mw",
        "lag_168h_demand_mw",
        "rolling_3h_demand_mw",
        "rolling_6h_demand_mw",
        "rolling_12h_demand_mw",
        "rolling_24h_demand_mw",
        "demand_rate_1h_mw",
        "demand_rate_3h_mw",
        "demand_rate_6h_mw",
        "recent_profile_residual_mw",
        "same_hour_7d_average_mw",
    )
    GRID_STATE_FEATURES = (
        "spinning_reserve_mw",
        "available_capacity_mw",
        "online_capacity_mw",
        "generation_tra_mw",
    )
    MODEL_FEATURES = LOAD_STATE_FEATURES + GRID_STATE_FEATURES + WEATHER_FEATURES

    def forecast_day(
        self,
        history: Sequence[DemandWeatherObservation],
        day_rows: Sequence[DemandWeatherObservation],
        weather_forecast: Sequence[dict[str, Any]],
        cursor_at: datetime,
        actual_reveal_at: datetime | None = None,
    ) -> DemoForecastResult:
        reveal_at = actual_reveal_at or cursor_at
        training = sorted(
            (row for row in history if row.timestamp <= cursor_at),
            key=lambda row: row.timestamp,
        )
        if len(training) < MIN_REQUIRED_HISTORY_ROWS:
            raise ValueError(
                f"At least {MIN_REQUIRED_HISTORY_ROWS} chronological observations "
                "are required"
            )

        fit_rows, tuning_rows, holdout_rows = _chronological_three_way_split(
            training
        )
        fit_baseline = _hourly_demand_lookup(fit_rows)
        tuning_features = _validation_features(
            fit_rows,
            tuning_rows,
            fit_baseline,
        )
        tuning_actual = [row.demand_mw for row in tuning_rows]
        tuning_hourly = [
            _baseline_for(row.timestamp.hour, fit_baseline, fit_rows)
            for row in tuning_rows
        ]
        tuning_candidates: dict[str, list[float]] = {
            "HourlyHistoricalAverage": tuning_hourly,
            "MovingAverageProfile": [
                _moving_average_profile_baseline(base, feature.load_state)
                for base, feature in zip(tuning_hourly, tuning_features)
            ],
        }

        model: _RidgeModel | None = None
        ridge_alpha = RIDGE_PENALTIES[0]
        ensemble_weight = ENSEMBLE_RIDGE_WEIGHTS[0]
        tuned_ml_name: str | None = None
        if len(fit_rows) >= MIN_TRAIN_ROWS:
            fit_features, fit_targets = _supervised_features(
                fit_rows,
                fit_baseline,
            )
            fit_moving = [
                _moving_average_profile_baseline(
                    feature.profile_baseline_mw,
                    feature.load_state,
                )
                for feature in fit_features
            ]
            residual_targets = [
                target - moving
                for target, moving in zip(fit_targets, fit_moving)
            ]
            tuning_moving = tuning_candidates["MovingAverageProfile"]
            ridge_options: list[tuple[float, _RidgeModel, list[float]]] = []
            for alpha in RIDGE_PENALTIES:
                fitted = _fit_load_state_ridge(
                    fit_features,
                    residual_targets,
                    alpha,
                )
                if fitted is not None:
                    residual_predictions = fitted.predict(
                        _feature_matrix(tuning_features)
                    )
                    ridge_options.append(
                        (
                            alpha,
                            fitted,
                            [
                                moving + float(residual)
                                for moving, residual in zip(
                                    tuning_moving,
                                    residual_predictions,
                                )
                            ],
                        )
                    )
            if ridge_options:
                ridge_alpha, model, ridge_predictions = min(
                    ridge_options,
                    key=lambda option: _metric_sort_key(
                        _forecast_metrics(tuning_actual, option[2])
                    ),
                )
                tuning_candidates["LoadStateWeatherRidge"] = ridge_predictions
                ensemble_options = [
                    (
                        weight,
                        [
                            weight * ridge + (1.0 - weight) * moving
                            for ridge, moving in zip(
                                ridge_predictions,
                                tuning_moving,
                            )
                        ],
                    )
                    for weight in ENSEMBLE_RIDGE_WEIGHTS
                ]
                ensemble_weight, ensemble_predictions = min(
                    ensemble_options,
                    key=lambda option: _metric_sort_key(
                        _forecast_metrics(tuning_actual, option[1])
                    ),
                )
                tuning_candidates[
                    "LoadStateWeatherEnsemble"
                ] = ensemble_predictions

                tuned_ml_name = min(
                    ML_MODEL_NAMES,
                    key=lambda name: _metric_sort_key(
                        _forecast_metrics(tuning_actual, tuning_candidates[name])
                    ),
                )

        tuning_metrics = {
            name: _forecast_metrics(tuning_actual, predictions)
            for name, predictions in tuning_candidates.items()
        }
        # Candidate order is the deterministic tie-breaker. Prefer the adaptive
        # moving profile when validation metrics are identical instead of
        # allowing Python hash randomization to choose the baseline family.
        statistical_names = (
            "MovingAverageProfile",
            "HourlyHistoricalAverage",
        )
        best_statistical = min(
            (name for name in statistical_names if name in tuning_metrics),
            key=lambda name: _metric_sort_key(tuning_metrics[name]),
        )

        # Hyperparameters and candidate family are fixed using only the tuning
        # partition. The newest chronological partition remains untouched until
        # this final activation comparison.
        development_rows = [*fit_rows, *tuning_rows]
        development_baseline = _hourly_demand_lookup(development_rows)
        holdout_features = _validation_features(
            development_rows,
            holdout_rows,
            development_baseline,
        )
        actual = [row.demand_mw for row in holdout_rows]
        raw_predictions = [
            _baseline_for(row.timestamp.hour, development_baseline, development_rows)
            for row in holdout_rows
        ]
        candidate_predictions: dict[str, list[float]] = {
            "HourlyHistoricalAverage": raw_predictions,
            "MovingAverageProfile": [
                _moving_average_profile_baseline(base, feature.load_state)
                for base, feature in zip(raw_predictions, holdout_features)
            ],
        }
        if tuned_ml_name is not None:
            development_features, development_targets = _supervised_features(
                development_rows,
                development_baseline,
            )
            development_moving = [
                _moving_average_profile_baseline(
                    feature.profile_baseline_mw,
                    feature.load_state,
                )
                for feature in development_features
            ]
            model = _fit_load_state_ridge(
                development_features,
                [
                    target - moving
                    for target, moving in zip(
                        development_targets,
                        development_moving,
                    )
                ],
                ridge_alpha,
            )
            if model is not None:
                holdout_moving = candidate_predictions["MovingAverageProfile"]
                holdout_ridge = [
                    moving + float(residual)
                    for moving, residual in zip(
                        holdout_moving,
                        model.predict(_feature_matrix(holdout_features)),
                    )
                ]
                candidate_predictions["LoadStateWeatherRidge"] = holdout_ridge
                candidate_predictions["LoadStateWeatherEnsemble"] = [
                    ensemble_weight * ridge + (1.0 - ensemble_weight) * moving
                    for ridge, moving in zip(holdout_ridge, holdout_moving)
                ]

        metrics = {
            name: _forecast_metrics(actual, predictions)
            for name, predictions in candidate_predictions.items()
        }
        baseline_metrics = metrics["HourlyHistoricalAverage"]
        best_statistical_metrics = metrics[best_statistical]
        selected_name = best_statistical
        if tuned_ml_name is not None and tuned_ml_name in metrics:
            ml_metrics = metrics[tuned_ml_name]
            required_mae_gain = max(
                MIN_MODEL_IMPROVEMENT_MW,
                best_statistical_metrics[0] * MIN_MODEL_IMPROVEMENT,
            )
            required_rmse_gain = max(
                MIN_MODEL_IMPROVEMENT_MW,
                best_statistical_metrics[1] * MIN_MODEL_IMPROVEMENT,
            )
            if (
                best_statistical_metrics[0] - ml_metrics[0]
                >= required_mae_gain
                and best_statistical_metrics[1] - ml_metrics[1]
                >= required_rmse_gain
            ):
                selected_name = tuned_ml_name

        # Refit the selected ML model on all observations available at issue time.
        all_baseline = _hourly_demand_lookup(training)
        if selected_name in ML_MODEL_NAMES:
            all_features, all_targets = _supervised_features(training, all_baseline)
            all_residual_targets = [
                target
                - _moving_average_profile_baseline(
                    feature.profile_baseline_mw,
                    feature.load_state,
                )
                for feature, target in zip(all_features, all_targets)
            ]
            model = _fit_load_state_ridge(
                all_features,
                all_residual_targets,
                ridge_alpha,
            )
            if model is None:
                selected_name = best_statistical

        selected_validation = candidate_predictions.get(
            selected_name,
            candidate_predictions["MovingAverageProfile"],
        )
        selected_metrics = _forecast_metrics(actual, selected_validation)
        residuals = [
            observed - predicted
            for observed, predicted in zip(actual, selected_validation)
        ]
        residual_std = max(
            MIN_UNCERTAINTY_MW,
            pstdev(residuals) if len(residuals) > 1 else 0.0,
        )
        interval_half_width = max(
            MIN_UNCERTAINTY_MW,
            float(
                np.quantile(
                    np.abs(np.asarray(residuals, dtype=float)),
                    FORECAST_INTERVAL_COVERAGE,
                )
            ),
        )

        all_hourly_means = _hourly_weather_means(training)
        forecast_by_hour = {
            _hour_key(item.get("forecast_timestamp")): item
            for item in weather_forecast
            if _hour_key(item.get("forecast_timestamp")) is not None
        }
        points: list[DemoForecastPoint] = []
        demand_history = {
            _hour_key(row.timestamp): float(row.demand_mw)
            for row in training
            if _hour_key(row.timestamp) is not None
        }
        observed_weather = {
            _hour_key(row.timestamp): row
            for row in training
            if _hour_key(row.timestamp) is not None
        }
        latest_observed_weather = training[-1]
        for row in sorted(day_rows, key=lambda item: item.timestamp):
            base = _baseline_for(row.timestamp.hour, all_baseline, training)
            weather_payload = forecast_by_hour.get(row.timestamp)
            load_state = _load_state(
                row.timestamp,
                demand_history,
                all_baseline,
                training,
            )
            target = _ForecastFeature.from_sources(
                row.timestamp,
                observed_weather.get(
                    (_hour_key(row.timestamp) or row.timestamp) - timedelta(hours=1),
                    latest_observed_weather,
                ),
                weather_payload,
                load_state,
                base,
            )
            neutral = _ForecastFeature.from_hourly_mean(
                row.timestamp,
                all_hourly_means[row.timestamp.hour],
                load_state,
                base,
                observed_weather.get(
                    (_hour_key(row.timestamp) or row.timestamp) - timedelta(hours=1),
                    latest_observed_weather,
                ),
            )
            if row.timestamp > cursor_at and weather_payload is None:
                # A missing forecast is represented by the historical weather
                # profile, not by holding the last observation indefinitely.
                target = neutral
            moving_value = _moving_average_profile_baseline(base, load_state)
            if (
                selected_name in ML_MODEL_NAMES
                and model is not None
            ):
                ridge_value = moving_value + float(
                    model.predict(_feature_matrix([target]))[0]
                )
                neutral_ridge = moving_value + float(
                    model.predict(_feature_matrix([neutral]))[0]
                )
                if selected_name == "LoadStateWeatherEnsemble":
                    forecast_value = (
                        ensemble_weight * ridge_value
                        + (1.0 - ensemble_weight) * moving_value
                    )
                    neutral_value = (
                        ensemble_weight * neutral_ridge
                        + (1.0 - ensemble_weight) * moving_value
                    )
                else:
                    forecast_value = ridge_value
                    neutral_value = neutral_ridge
            elif selected_name == "MovingAverageProfile":
                forecast_value = moving_value
                neutral_value = moving_value
            else:
                forecast_value = base
                neutral_value = base

            forecast_value = max(0.0, forecast_value)
            if row.timestamp > cursor_at:
                key = _hour_key(row.timestamp)
                if key is not None:
                    # Recursive forecasts use prior predictions, never the unrevealed
                    # demand carried by the replay source row.
                    demand_history[key] = forecast_value

            confidence = _safe_float(
                weather_payload.get("confidence_score") if weather_payload else None,
                0.72 if row.timestamp > cursor_at else 1.0,
            )
            source_count = int(
                _safe_float(
                    weather_payload.get("source_count") if weather_payload else None,
                    0 if row.timestamp > cursor_at else 1,
                )
            )
            horizon_hours = max(
                1.0,
                (row.timestamp - cursor_at).total_seconds() / 3600.0,
            )
            horizon_growth = min(2.5, math.sqrt(horizon_hours))
            uncertainty = max(
                MIN_UNCERTAINTY_MW,
                interval_half_width
                * horizon_growth
                * (1.0 + (1.0 - confidence) * 0.75),
            )
            points.append(
                DemoForecastPoint(
                    timestamp=row.timestamp,
                    forecast_demand_mw=round(forecast_value, 2),
                    historical_average_mw=round(base, 2),
                    actual_demand_mw=(
                        row.demand_mw if row.timestamp <= reveal_at else None
                    ),
                    uncertainty_mw=round(uncertainty, 2),
                    weather_impact_mw=round(forecast_value - neutral_value, 2),
                    weather_confidence=round(max(0.0, min(1.0, confidence)), 2),
                    weather_source_count=source_count,
                )
            )

        mode = (
            "ML_ACTIVE"
            if selected_name in ML_MODEL_NAMES
            else "STATISTICAL_ACTIVE"
        )
        logger.info(
            "Replay demand forecast evaluated",
            extra={
                "forecast_model": selected_name,
                "forecast_mode": mode,
                "forecast_mae_mw": round(selected_metrics[0], 3),
                "forecast_rmse_mw": round(selected_metrics[1], 3),
                "hourly_baseline_mae_mw": round(baseline_metrics[0], 3),
                "fit_rows": len(fit_rows),
                "tuning_rows": len(tuning_rows),
                "holdout_rows": len(holdout_rows),
                "ridge_alpha": ridge_alpha if tuned_ml_name is not None else None,
                "ensemble_weight": (
                    ensemble_weight
                    if tuned_ml_name == "LoadStateWeatherEnsemble"
                    else None
                ),
            },
        )
        return DemoForecastResult(
            points=points,
            model_name=selected_name,
            model_mode=mode,
            mae_mw=round(selected_metrics[0], 2),
            baseline_mae_mw=round(baseline_metrics[0], 2),
            residual_std_mw=round(residual_std, 2),
            trained_through=cursor_at,
            training_rows=len(training),
            weather_features=self.MODEL_FEATURES,
        )


@dataclass(frozen=True)
class _DemandState:
    lag_1h_mw: float
    lag_2h_mw: float
    lag_3h_mw: float
    lag_6h_mw: float
    lag_24h_mw: float
    lag_48h_mw: float
    lag_168h_mw: float
    rolling_3h_mw: float
    rolling_6h_mw: float
    rolling_12h_mw: float
    rolling_24h_mw: float
    rate_1h_mw: float
    rate_3h_mw: float
    rate_6h_mw: float
    recent_profile_average_mw: float
    recent_profile_residual_mw: float
    same_hour_7d_average_mw: float


@dataclass(frozen=True)
class _ForecastFeature:
    timestamp: datetime
    profile_baseline_mw: float
    load_state: _DemandState
    spinning_reserve_mw: float
    available_capacity_mw: float
    online_capacity_mw: float
    generation_tra_mw: float
    temperature_c: float
    humidity_percent: float
    rainfall_mm_hr: float
    cloud_cover_percent: float
    wind_speed_kmh: float
    pressure_hpa: float

    @classmethod
    def from_sources(
        cls,
        timestamp: datetime,
        weather_observation: DemandWeatherObservation,
        forecast: dict[str, Any] | None,
        load_state: _DemandState,
        profile_baseline_mw: float,
    ) -> _ForecastFeature:
        payload = forecast or {}
        return cls(
            timestamp=timestamp,
            profile_baseline_mw=profile_baseline_mw,
            load_state=load_state,
            spinning_reserve_mw=_attribute_float(
                weather_observation,
                "spinning_reserve_mw",
            ),
            available_capacity_mw=_attribute_float(
                weather_observation,
                "available_capacity_mw",
            ),
            online_capacity_mw=_attribute_float(
                weather_observation,
                "online_capacity_mw",
            ),
            generation_tra_mw=_attribute_float(
                weather_observation,
                "generation_mw",
            ),
            temperature_c=_safe_float(
                payload.get("temperature_c"),
                weather_observation.temperature_c,
            ),
            humidity_percent=_safe_float(
                payload.get("humidity_percent"),
                weather_observation.humidity_percent,
            ),
            rainfall_mm_hr=_safe_float(
                payload.get("rainfall_mm_hr"),
                weather_observation.rainfall_mm_hr,
            ),
            cloud_cover_percent=_safe_float(
                payload.get("cloud_cover_percent"),
                weather_observation.cloud_cover_percent,
            ),
            wind_speed_kmh=_safe_float(
                payload.get("wind_speed_kmh"),
                weather_observation.wind_speed_kmh,
            ),
            pressure_hpa=_safe_float(
                payload.get("pressure_hpa"),
                weather_observation.pressure_hpa,
            ),
        )

    @classmethod
    def from_hourly_mean(
        cls,
        timestamp: datetime,
        values: tuple[float, float, float, float, float, float],
        load_state: _DemandState,
        profile_baseline_mw: float,
        operational_source: DemandWeatherObservation,
    ) -> _ForecastFeature:
        return cls(
            timestamp,
            profile_baseline_mw,
            load_state,
            _attribute_float(operational_source, "spinning_reserve_mw"),
            _attribute_float(operational_source, "available_capacity_mw"),
            _attribute_float(operational_source, "online_capacity_mw"),
            _attribute_float(operational_source, "generation_mw"),
            *values,
        )


def _feature_matrix(rows: Sequence[_ForecastFeature]) -> np.ndarray:
    features: list[list[float]] = []
    for row in rows:
        hour_angle = 2.0 * math.pi * row.timestamp.hour / 24.0
        year_angle = 2.0 * math.pi * row.timestamp.timetuple().tm_yday / 365.25
        state = row.load_state
        features.append(
            [
                math.sin(hour_angle),
                math.cos(hour_angle),
                math.sin(year_angle),
                math.cos(year_angle),
                float(row.timestamp.weekday()),
                1.0 if row.timestamp.weekday() >= 5 else 0.0,
                row.profile_baseline_mw,
                state.lag_1h_mw,
                state.lag_2h_mw,
                state.lag_3h_mw,
                state.lag_6h_mw,
                state.lag_24h_mw,
                state.lag_48h_mw,
                state.lag_168h_mw,
                state.rolling_3h_mw,
                state.rolling_6h_mw,
                state.rolling_12h_mw,
                state.rolling_24h_mw,
                state.rate_1h_mw,
                state.rate_3h_mw,
                state.rate_6h_mw,
                state.recent_profile_residual_mw,
                state.same_hour_7d_average_mw,
                row.spinning_reserve_mw,
                row.available_capacity_mw,
                row.online_capacity_mw,
                row.generation_tra_mw,
                row.temperature_c,
                row.humidity_percent,
                row.rainfall_mm_hr,
                row.cloud_cover_percent,
                row.wind_speed_kmh,
                row.pressure_hpa,
            ]
        )
    return np.asarray(features, dtype=float)


@dataclass(frozen=True)
class _RidgeModel:
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    feature_lower: np.ndarray
    feature_upper: np.ndarray
    coefficients: np.ndarray
    residual_lower: float
    residual_upper: float

    def predict(self, values: np.ndarray) -> np.ndarray:
        clipped = np.clip(values, self.feature_lower, self.feature_upper)
        normalized = (clipped - self.feature_mean) / self.feature_scale
        design = np.column_stack((np.ones(len(normalized)), normalized))
        predicted = design @ self.coefficients
        return np.clip(predicted, self.residual_lower, self.residual_upper)


def _fit_load_state_ridge(
    rows: Sequence[_ForecastFeature],
    targets: Sequence[float],
    alpha: float,
) -> _RidgeModel | None:
    if not rows or len(rows) != len(targets):
        return None
    features = _feature_matrix(rows)
    feature_lower = np.quantile(features, 0.005, axis=0)
    feature_upper = np.quantile(features, 0.995, axis=0)
    clipped_features = np.clip(features, feature_lower, feature_upper)
    feature_mean = clipped_features.mean(axis=0)
    feature_scale = clipped_features.std(axis=0)
    feature_scale[feature_scale < 1e-9] = 1.0
    normalized = (clipped_features - feature_mean) / feature_scale
    design = np.column_stack((np.ones(len(normalized)), normalized))
    target = np.asarray(targets, dtype=float)
    penalty = np.eye(design.shape[1]) * alpha
    penalty[0, 0] = 0.0
    try:
        coefficients = np.linalg.solve(
            design.T @ design + penalty,
            design.T @ target,
        )
    except np.linalg.LinAlgError:
        coefficients = np.linalg.lstsq(design, target, rcond=None)[0]
    residual_lower = float(np.quantile(target, 0.01))
    residual_upper = float(np.quantile(target, 0.99))
    if residual_upper <= residual_lower:
        residual_lower = float(target.min())
        residual_upper = float(target.max())
    return _RidgeModel(
        feature_mean,
        feature_scale,
        feature_lower,
        feature_upper,
        coefficients,
        residual_lower,
        residual_upper,
    )


def _chronological_three_way_split(
    rows: Sequence[DemandWeatherObservation],
) -> tuple[
    list[DemandWeatherObservation],
    list[DemandWeatherObservation],
    list[DemandWeatherObservation],
]:
    ordered = sorted(rows, key=lambda row: row.timestamp)
    row_count = len(ordered)
    minimum_fit_rows = 24
    tuning_size = max(12, int(row_count * 0.2))
    holdout_size = max(12, int(row_count * 0.2))
    available_after_fit = row_count - minimum_fit_rows
    if tuning_size + holdout_size > available_after_fit:
        tuning_size = max(1, available_after_fit // 2)
        holdout_size = max(1, available_after_fit - tuning_size)

    fit_end = row_count - tuning_size - holdout_size
    tuning_end = row_count - holdout_size
    return (
        ordered[:fit_end],
        ordered[fit_end:tuning_end],
        ordered[tuning_end:],
    )


def _supervised_features(
    rows: Sequence[DemandWeatherObservation],
    baseline: dict[int, float],
) -> tuple[list[_ForecastFeature], list[float]]:
    ordered = sorted(rows, key=lambda row: row.timestamp)
    demand_history: dict[datetime, float] = {}
    features: list[_ForecastFeature] = []
    targets: list[float] = []
    latest_weather: DemandWeatherObservation | None = None
    for row in ordered:
        if (
            len(demand_history) >= MIN_LOAD_HISTORY_ROWS
            and latest_weather is not None
        ):
            profile_baseline = _baseline_for(row.timestamp.hour, baseline, ordered)
            state = _load_state(
                row.timestamp,
                demand_history,
                baseline,
                ordered,
            )
            features.append(
                _ForecastFeature.from_sources(
                    row.timestamp,
                    latest_weather,
                    None,
                    state,
                    profile_baseline,
                )
            )
            targets.append(float(row.demand_mw))
        key = _hour_key(row.timestamp)
        if key is not None:
            demand_history[key] = float(row.demand_mw)
        latest_weather = row
    return features, targets


def _validation_features(
    train_rows: Sequence[DemandWeatherObservation],
    validation_rows: Sequence[DemandWeatherObservation],
    baseline: dict[int, float],
) -> list[_ForecastFeature]:
    demand_history = {
        _hour_key(row.timestamp): float(row.demand_mw)
        for row in train_rows
        if _hour_key(row.timestamp) is not None
    }
    fallback_rows = list(train_rows)
    latest_weather: DemandWeatherObservation = fallback_rows[-1]
    features: list[_ForecastFeature] = []
    for row in sorted(validation_rows, key=lambda item: item.timestamp):
        profile_baseline = _baseline_for(row.timestamp.hour, baseline, fallback_rows)
        state = _load_state(
            row.timestamp,
            demand_history,
            baseline,
            fallback_rows,
        )
        features.append(
            _ForecastFeature.from_sources(
                row.timestamp,
                latest_weather,
                None,
                state,
                profile_baseline,
            )
        )
        key = _hour_key(row.timestamp)
        if key is not None:
            # Walk-forward validation may use observations available before the
            # next issue hour, but never a later validation target.
            demand_history[key] = float(row.demand_mw)
        latest_weather = row
    return features


def _load_state(
    timestamp: datetime,
    demand_history: dict[datetime, float],
    baseline: dict[int, float],
    fallback_rows: Sequence[DemandWeatherObservation],
) -> _DemandState:
    target = _hour_key(timestamp) or timestamp.replace(
        minute=0,
        second=0,
        microsecond=0,
    )
    fallback_average = (
        mean(baseline.values())
        if baseline
        else mean(row.demand_mw for row in fallback_rows)
    )

    def lag(hours: int) -> float:
        lagged_at = target - timedelta(hours=hours)
        return float(
            demand_history.get(
                lagged_at,
                baseline.get(lagged_at.hour, fallback_average),
            )
        )

    def rolling(window: int) -> float:
        return mean(lag(offset) for offset in range(1, window + 1))

    lag_1h = lag(1)
    lag_2h = lag(2)
    lag_3h = lag(3)
    lag_6h = lag(6)
    lag_24h = lag(24)
    lag_48h = lag(48)
    lag_168h = lag(168)
    recent_profile_average = mean(
        baseline.get((target.hour - offset) % 24, fallback_average)
        for offset in range(1, 4)
    )
    recent_profile_residual = median(
        lag(offset)
        - baseline.get((target.hour - offset) % 24, fallback_average)
        for offset in range(1, 7)
    )
    return _DemandState(
        lag_1h_mw=lag_1h,
        lag_2h_mw=lag_2h,
        lag_3h_mw=lag_3h,
        lag_6h_mw=lag_6h,
        lag_24h_mw=lag_24h,
        lag_48h_mw=lag_48h,
        lag_168h_mw=lag_168h,
        rolling_3h_mw=rolling(3),
        rolling_6h_mw=rolling(6),
        rolling_12h_mw=rolling(12),
        rolling_24h_mw=rolling(24),
        rate_1h_mw=lag_1h - lag_2h,
        rate_3h_mw=(lag_1h - lag(4)) / 3.0,
        rate_6h_mw=(lag_1h - lag(7)) / 6.0,
        recent_profile_average_mw=recent_profile_average,
        recent_profile_residual_mw=recent_profile_residual,
        same_hour_7d_average_mw=mean(
            lag(24 * day_offset) for day_offset in range(1, 8)
        ),
    )


def _moving_average_profile_baseline(
    profile_baseline_mw: float,
    state: _DemandState,
) -> float:
    return max(0.0, profile_baseline_mw + state.recent_profile_residual_mw)


def _hourly_demand_lookup(
    rows: Sequence[DemandWeatherObservation],
) -> dict[int, float]:
    return {
        hour: mean(row.demand_mw for row in rows if row.timestamp.hour == hour)
        for hour in range(24)
        if any(row.timestamp.hour == hour for row in rows)
    }


def _hourly_weather_means(
    rows: Sequence[DemandWeatherObservation],
) -> dict[int, tuple[float, float, float, float, float, float]]:
    result: dict[int, tuple[float, float, float, float, float, float]] = {}
    for hour in range(24):
        hourly = [row for row in rows if row.timestamp.hour == hour]
        if not hourly:
            continue
        result[hour] = (
            mean(row.temperature_c for row in hourly),
            mean(row.humidity_percent for row in hourly),
            mean(row.rainfall_mm_hr for row in hourly),
            mean(row.cloud_cover_percent for row in hourly),
            mean(row.wind_speed_kmh for row in hourly),
            mean(row.pressure_hpa for row in hourly),
        )
    return result


def _baseline_for(
    hour: int,
    lookup: dict[int, float],
    rows: Sequence[DemandWeatherObservation],
) -> float:
    if hour in lookup:
        return lookup[hour]
    return mean(row.demand_mw for row in rows)


def _forecast_metrics(actual: list[float], predicted: list[float]) -> tuple[float, float]:
    errors = [observed - estimate for observed, estimate in zip(actual, predicted)]
    mae = mean(abs(error) for error in errors)
    rmse = math.sqrt(mean(error * error for error in errors))
    return mae, rmse


def _metric_sort_key(metrics: tuple[float, float]) -> tuple[float, float]:
    return metrics


def _hour_key(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed.replace(minute=0, second=0, microsecond=0)


def _safe_float(value: Any, fallback: float) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return converted if math.isfinite(converted) else float(fallback)


def _attribute_float(source: object, name: str) -> float:
    return _safe_float(getattr(source, name, 0.0), 0.0)
