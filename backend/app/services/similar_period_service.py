from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import math

from app.models.demand_forecast import ForecastTrainingRow
from app.services.forecast_calendar_service import calendar_context


DEFAULT_SIMILAR_PERIOD_LIMIT = 8
TEMPERATURE_TOLERANCE_C = 4.0


@dataclass(frozen=True)
class SimilarPeriodExample:
    feature_timestamp: datetime
    target_timestamp: datetime
    target_demand_mw: float
    temperature_c: float | None
    forecast_temperature_c: float | None
    day_type: str
    distance: float

    def as_json_object(self) -> dict[str, object]:
        payload = asdict(self)
        payload["feature_timestamp"] = self.feature_timestamp.isoformat()
        payload["target_timestamp"] = self.target_timestamp.isoformat()
        return payload


@dataclass(frozen=True)
class SimilarPeriodForecast:
    forecast_mw: float | None
    spread_mw: float | None
    examples: tuple[SimilarPeriodExample, ...]


def similar_period_forecast(
    history: list[ForecastTrainingRow],
    query: ForecastTrainingRow,
    limit: int = DEFAULT_SIMILAR_PERIOD_LIMIT,
    extra_holiday_dates: str = "",
) -> SimilarPeriodForecast:
    candidates = [
        row
        for row in history
        if row.horizon_hours == query.horizon_hours
        and row.feature_timestamp < query.feature_timestamp
        and row.target_timestamp <= query.feature_timestamp
    ]
    if not candidates:
        return SimilarPeriodForecast(None, None, ())

    query_context = calendar_context(query.target_timestamp, extra_holiday_dates)
    same_hour = [
        row
        for row in candidates
        if _circular_hour_distance(
            row.target_timestamp.hour,
            query.target_timestamp.hour,
        )
        == 0
    ]
    same_hour_temperature = [
        row
        for row in same_hour
        if _temperature_difference(row, query) <= TEMPERATURE_TOLERANCE_C
    ]
    preferred = [
        row
        for row in same_hour_temperature
        if calendar_context(
            row.target_timestamp,
            extra_holiday_dates,
        ).day_type
        == query_context.day_type
    ]
    candidate_pool = (
        preferred
        if len(preferred) >= 3
        else same_hour_temperature
        if len(same_hour_temperature) >= 3
        else same_hour
        if len(same_hour) >= 3
        else candidates
    )
    selected = sorted(
        (
            (
                _distance(row, query, query_context.day_type, extra_holiday_dates),
                row,
            )
            for row in candidate_pool
        ),
        key=lambda item: (item[0], item[1].target_timestamp),
    )[: max(1, limit)]
    weights = [math.exp(-min(20.0, distance)) for distance, _ in selected]
    if sum(weights) <= 0:
        weights = [1.0 for _ in selected]
    total_weight = sum(weights)
    forecast = sum(
        weight * row.target_demand_mw
        for weight, (_, row) in zip(weights, selected)
    ) / total_weight
    variance = sum(
        weight * (row.target_demand_mw - forecast) ** 2
        for weight, (_, row) in zip(weights, selected)
    ) / total_weight
    examples = tuple(
        SimilarPeriodExample(
            feature_timestamp=row.feature_timestamp,
            target_timestamp=row.target_timestamp,
            target_demand_mw=round(row.target_demand_mw, 4),
            temperature_c=row.temperature_c,
            forecast_temperature_c=row.forecast_temperature_c,
            day_type=calendar_context(
                row.target_timestamp,
                extra_holiday_dates,
            ).day_type,
            distance=round(distance, 4),
        )
        for distance, row in selected
    )
    return SimilarPeriodForecast(
        forecast_mw=round(forecast, 4),
        spread_mw=round(variance**0.5, 4),
        examples=examples,
    )


def _distance(
    candidate: ForecastTrainingRow,
    query: ForecastTrainingRow,
    query_day_type: str,
    extra_holiday_dates: str,
) -> float:
    candidate_context = calendar_context(
        candidate.target_timestamp,
        extra_holiday_dates,
    )
    hour_distance = _circular_hour_distance(
        candidate.target_timestamp.hour,
        query.target_timestamp.hour,
    )
    month_distance = _circular_month_distance(
        candidate.target_timestamp.month,
        query.target_timestamp.month,
    )
    day_type_penalty = (
        0.0
        if candidate_context.day_type == query_day_type
        else 3.5
        if "HOLIDAY" in {candidate_context.day_type, query_day_type}
        else 1.75
    )
    return (
        hour_distance * 2.5
        + _temperature_difference(candidate, query) / 2.5
        + day_type_penalty
        + month_distance / 4.0
        + _normalized_difference(
            candidate.humidity_percent,
            query.humidity_percent,
            15.0,
        )
        * 0.6
        + _normalized_difference(
            _log_rain(candidate.forecast_rainfall_mm_hr),
            _log_rain(query.forecast_rainfall_mm_hr),
            1.0,
        )
        * 0.5
        + _normalized_difference(
            candidate.forecast_cloud_cover_percent,
            query.forecast_cloud_cover_percent,
            30.0,
        )
        * 0.4
        + _normalized_difference(
            candidate.current_demand_mw,
            query.current_demand_mw,
            100.0,
        )
        * 1.5
        + _normalized_difference(
            candidate.demand_rate_1h_mw,
            query.demand_rate_1h_mw,
            50.0,
        )
        * 0.8
    )


def _temperature_difference(
    left: ForecastTrainingRow,
    right: ForecastTrainingRow,
) -> float:
    left_value = left.forecast_temperature_c or left.temperature_c
    right_value = right.forecast_temperature_c or right.temperature_c
    if left_value is None or right_value is None:
        return TEMPERATURE_TOLERANCE_C
    return abs(float(left_value) - float(right_value))


def _normalized_difference(
    left: float | None,
    right: float | None,
    scale: float,
) -> float:
    if left is None or right is None:
        return 1.0
    return abs(float(left) - float(right)) / scale


def _log_rain(value: float | None) -> float | None:
    return math.log1p(max(0.0, float(value))) if value is not None else None


def _circular_hour_distance(left: int, right: int) -> int:
    distance = abs(left - right)
    return min(distance, 24 - distance)


def _circular_month_distance(left: int, right: int) -> int:
    distance = abs(left - right)
    return min(distance, 12 - distance)
