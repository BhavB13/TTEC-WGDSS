from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, pstdev
from typing import Any, Protocol, Sequence

import numpy as np


# June replay is a prototype with less than one full month available at many
# cursor positions. Seven completed days are enough to evaluate Ridge, but the
# model is still activated only when it beats the chronological baseline.
MIN_TRAIN_ROWS = 24 * 7
MIN_MODEL_IMPROVEMENT = 0.02
MIN_UNCERTAINTY_MW = 12.0


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
    """Chronological weather-sensitive forecasting for the demonstration archive."""

    WEATHER_FEATURES = (
        "temperature_c",
        "humidity_percent",
        "rainfall_mm_hr",
        "cloud_cover_percent",
        "wind_speed_kmh",
        "pressure_hpa",
    )

    def forecast_day(
        self,
        history: Sequence[DemandWeatherObservation],
        day_rows: Sequence[DemandWeatherObservation],
        weather_forecast: Sequence[dict[str, Any]],
        cursor_at: datetime,
    ) -> DemoForecastResult:
        training = sorted(
            (row for row in history if row.timestamp <= cursor_at),
            key=lambda row: row.timestamp,
        )
        if len(training) < 48:
            raise ValueError("At least 48 chronological observations are required")

        split_index = max(24, int(len(training) * 0.8))
        split_index = min(split_index, len(training) - 24)
        train_rows = training[:split_index]
        validation_rows = training[split_index:]
        hourly_means = _hourly_weather_means(train_rows)
        raw_baseline = _hourly_demand_lookup(train_rows)

        actual = [row.demand_mw for row in validation_rows]
        raw_predictions = [
            _baseline_for(row.timestamp.hour, raw_baseline, train_rows)
            for row in validation_rows
        ]
        candidate_predictions: dict[str, list[float]] = {
            "HourlyHistoricalAverage": raw_predictions,
            "WeatherAdjustedBaseline": [
                _weather_adjusted_baseline(
                    base,
                    row,
                    hourly_means[row.timestamp.hour],
                )
                for base, row in zip(raw_predictions, validation_rows)
            ],
        }
        model = None
        if len(train_rows) >= MIN_TRAIN_ROWS:
            model = _fit_weather_ridge(train_rows)
            if model is not None:
                candidate_predictions["WeatherFeatureRidge"] = list(
                    model.predict(_feature_matrix(validation_rows))
                )

        metrics = {
            name: _forecast_metrics(actual, predictions)
            for name, predictions in candidate_predictions.items()
        }
        baseline_metrics = metrics["HourlyHistoricalAverage"]
        eligible = {
            name: values
            for name, values in metrics.items()
            if name == "HourlyHistoricalAverage"
            or (
                values[0] <= baseline_metrics[0] * (1.0 - MIN_MODEL_IMPROVEMENT)
                and values[1] <= baseline_metrics[1] * (1.0 - MIN_MODEL_IMPROVEMENT)
            )
        }
        selected_name = min(eligible, key=lambda name: (eligible[name][0], eligible[name][1]))

        # Refit the selected ML model on all data available at the replay cursor.
        if selected_name == "WeatherFeatureRidge":
            model = _fit_weather_ridge(training)
            if model is None:
                selected_name = "WeatherAdjustedBaseline"

        selected_validation = candidate_predictions.get(
            selected_name,
            candidate_predictions["WeatherAdjustedBaseline"],
        )
        selected_metrics = _forecast_metrics(actual, selected_validation)
        residuals = [
            observed - predicted
            for observed, predicted in zip(actual, selected_validation)
        ]
        residual_std = max(MIN_UNCERTAINTY_MW, pstdev(residuals) if len(residuals) > 1 else 0.0)

        all_hourly_means = _hourly_weather_means(training)
        all_baseline = _hourly_demand_lookup(training)
        forecast_by_hour = {
            _hour_key(item.get("forecast_timestamp")): item
            for item in weather_forecast
            if _hour_key(item.get("forecast_timestamp")) is not None
        }
        points: list[DemoForecastPoint] = []
        for row in sorted(day_rows, key=lambda item: item.timestamp):
            base = _baseline_for(row.timestamp.hour, all_baseline, training)
            weather_payload = forecast_by_hour.get(row.timestamp)
            target = _ForecastFeature.from_sources(row, weather_payload)
            neutral = _ForecastFeature.from_hourly_mean(
                row.timestamp,
                all_hourly_means[row.timestamp.hour],
            )
            if selected_name == "WeatherFeatureRidge" and model is not None:
                forecast_value = float(model.predict(_feature_matrix([target]))[0])
                neutral_value = float(model.predict(_feature_matrix([neutral]))[0])
            elif selected_name == "WeatherAdjustedBaseline":
                forecast_value = _weather_adjusted_baseline(
                    base,
                    target,
                    all_hourly_means[row.timestamp.hour],
                )
                neutral_value = base
            else:
                forecast_value = base
                neutral_value = base

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
            uncertainty = max(
                MIN_UNCERTAINTY_MW,
                residual_std * (1.0 + (1.0 - confidence) * 0.75),
            )
            points.append(
                DemoForecastPoint(
                    timestamp=row.timestamp,
                    forecast_demand_mw=round(max(0.0, forecast_value), 2),
                    historical_average_mw=round(base, 2),
                    actual_demand_mw=(row.demand_mw if row.timestamp <= cursor_at else None),
                    uncertainty_mw=round(uncertainty, 2),
                    weather_impact_mw=round(forecast_value - neutral_value, 2),
                    weather_confidence=round(max(0.0, min(1.0, confidence)), 2),
                    weather_source_count=source_count,
                )
            )

        mode = "ML_ACTIVE" if selected_name == "WeatherFeatureRidge" else "STATISTICAL_ACTIVE"
        return DemoForecastResult(
            points=points,
            model_name=selected_name,
            model_mode=mode,
            mae_mw=round(selected_metrics[0], 2),
            baseline_mae_mw=round(baseline_metrics[0], 2),
            residual_std_mw=round(residual_std, 2),
            trained_through=cursor_at,
            training_rows=len(training),
            weather_features=self.WEATHER_FEATURES,
        )


@dataclass(frozen=True)
class _ForecastFeature:
    timestamp: datetime
    demand_mw: float
    temperature_c: float
    humidity_percent: float
    rainfall_mm_hr: float
    cloud_cover_percent: float
    wind_speed_kmh: float
    pressure_hpa: float

    @classmethod
    def from_sources(
        cls,
        row: DemandWeatherObservation,
        forecast: dict[str, Any] | None,
    ) -> _ForecastFeature:
        payload = forecast or {}
        return cls(
            timestamp=row.timestamp,
            demand_mw=row.demand_mw,
            temperature_c=_safe_float(payload.get("temperature_c"), row.temperature_c),
            humidity_percent=_safe_float(payload.get("humidity_percent"), row.humidity_percent),
            rainfall_mm_hr=_safe_float(payload.get("rainfall_mm_hr"), row.rainfall_mm_hr),
            cloud_cover_percent=_safe_float(payload.get("cloud_cover_percent"), row.cloud_cover_percent),
            wind_speed_kmh=_safe_float(payload.get("wind_speed_kmh"), row.wind_speed_kmh),
            pressure_hpa=_safe_float(payload.get("pressure_hpa"), row.pressure_hpa),
        )

    @classmethod
    def from_hourly_mean(
        cls,
        timestamp: datetime,
        values: tuple[float, float, float, float, float, float],
    ) -> _ForecastFeature:
        return cls(timestamp, 0.0, *values)


def _feature_matrix(rows: Sequence[DemandWeatherObservation]) -> np.ndarray:
    features: list[list[float]] = []
    for row in rows:
        hour_angle = 2.0 * math.pi * row.timestamp.hour / 24.0
        year_angle = 2.0 * math.pi * row.timestamp.timetuple().tm_yday / 365.25
        features.append(
            [
                math.sin(hour_angle),
                math.cos(hour_angle),
                math.sin(year_angle),
                math.cos(year_angle),
                float(row.timestamp.weekday()),
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
    coefficients: np.ndarray

    def predict(self, values: np.ndarray) -> np.ndarray:
        normalized = (values - self.feature_mean) / self.feature_scale
        design = np.column_stack((np.ones(len(normalized)), normalized))
        return design @ self.coefficients


def _fit_weather_ridge(
    rows: Sequence[DemandWeatherObservation],
) -> _RidgeModel | None:
    if not rows:
        return None
    features = _feature_matrix(rows)
    feature_mean = features.mean(axis=0)
    feature_scale = features.std(axis=0)
    feature_scale[feature_scale < 1e-9] = 1.0
    normalized = (features - feature_mean) / feature_scale
    design = np.column_stack((np.ones(len(normalized)), normalized))
    target = np.asarray([row.demand_mw for row in rows], dtype=float)
    penalty = np.eye(design.shape[1]) * 8.0
    penalty[0, 0] = 0.0
    try:
        coefficients = np.linalg.solve(
            design.T @ design + penalty,
            design.T @ target,
        )
    except np.linalg.LinAlgError:
        coefficients = np.linalg.lstsq(design, target, rcond=None)[0]
    return _RidgeModel(feature_mean, feature_scale, coefficients)


def _weather_adjusted_baseline(
    baseline_mw: float,
    row: DemandWeatherObservation,
    hourly_mean: tuple[float, float, float, float, float, float],
) -> float:
    temp, humidity, rainfall, cloud, wind, _pressure = hourly_mean
    adjustment = (row.temperature_c - temp) * 11.5
    adjustment += (row.humidity_percent - humidity) * 0.9
    adjustment -= (row.rainfall_mm_hr - rainfall) * 3.5
    adjustment -= (row.cloud_cover_percent - cloud) * 0.08
    adjustment += (row.wind_speed_kmh - wind) * 0.05
    return max(0.0, baseline_mw + adjustment)


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
    return lookup.get(hour, mean(row.demand_mw for row in rows))


def _forecast_metrics(actual: list[float], predicted: list[float]) -> tuple[float, float]:
    errors = [observed - estimate for observed, estimate in zip(actual, predicted)]
    mae = mean(abs(error) for error in errors)
    rmse = math.sqrt(mean(error * error for error in errors))
    return mae, rmse


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
