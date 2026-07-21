from __future__ import annotations

from collections import defaultdict
from statistics import median

from app.models.demand_forecast import ForecastTrainingRow


MAX_TREND_STEP_MW_PER_HOUR = 75.0


def persistence_forecast(row: ForecastTrainingRow) -> float:
    return row.current_demand_mw


def trend_adjusted_persistence_forecast(row: ForecastTrainingRow) -> float | None:
    if row.lag_1h_demand_mw is None:
        return None
    hourly_delta = row.current_demand_mw - row.lag_1h_demand_mw
    bounded_delta = max(
        -MAX_TREND_STEP_MW_PER_HOUR,
        min(MAX_TREND_STEP_MW_PER_HOUR, hourly_delta),
    )
    return max(0.0, row.current_demand_mw + bounded_delta * row.horizon_hours)


def rolling_trend_forecast(row: ForecastTrainingRow) -> float | None:
    if row.lag_1h_demand_mw is None:
        return None
    hourly_deltas = [row.current_demand_mw - row.lag_1h_demand_mw]
    if row.lag_2h_demand_mw is not None:
        hourly_deltas.append(row.lag_1h_demand_mw - row.lag_2h_demand_mw)
    robust_delta = median(hourly_deltas)
    bounded_delta = max(
        -MAX_TREND_STEP_MW_PER_HOUR,
        min(MAX_TREND_STEP_MW_PER_HOUR, robust_delta),
    )
    return max(0.0, row.current_demand_mw + bounded_delta * row.horizon_hours)


def same_hour_yesterday_forecast(row: ForecastTrainingRow) -> float | None:
    return (
        row.target_lag_24h_demand_mw
        if row.target_lag_24h_demand_mw is not None
        else row.lag_24h_demand_mw
    )


def seasonal_naive_weekly_forecast(row: ForecastTrainingRow) -> float | None:
    """Use the same hour from the previous week without future information."""

    return (
        row.target_lag_168h_demand_mw
        if row.target_lag_168h_demand_mw is not None
        else row.lag_168h_demand_mw
    )


def target_same_hour_average_forecast(
    row: ForecastTrainingRow,
) -> float | None:
    return row.target_same_hour_7d_average_mw


def hourly_average_lookup(rows: list[ForecastTrainingRow]) -> dict[int, float]:
    values_by_hour: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        values_by_hour[row.target_timestamp.hour].append(row.target_demand_mw)
    return {
        hour: sum(values) / len(values)
        for hour, values in values_by_hour.items()
        if values
    }


def hourly_average_forecast(
    row: ForecastTrainingRow,
    hourly_lookup: dict[int, float],
) -> float | None:
    return hourly_lookup.get(row.target_timestamp.hour)
