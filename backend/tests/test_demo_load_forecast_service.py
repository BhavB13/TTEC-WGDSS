import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from app.services.demo_load_forecast_service import (
    DemoLoadForecastService,
    _chronological_three_way_split,
)
from app.services.demo_replay_service import _generate_demo_year


def test_demo_forecast_tracks_load_state_and_never_reveals_future_actuals():
    rows = _generate_demo_year(2025)
    cursor = datetime(2025, 6, 15, 10)
    history = [row for row in rows if row.timestamp <= cursor]
    day_rows = [
        row
        for row in rows
        if datetime(2025, 6, 15) <= row.timestamp <= datetime(2025, 6, 15, 23)
    ]

    service = DemoLoadForecastService()
    result = service.forecast_day(history, day_rows, [], cursor)

    assert all(point.actual_demand_mw is None for point in result.points[11:])
    assert all(
        point.actual_temperature_c is None for point in result.points[11:]
    )
    assert all(
        point.forecast_temperature_c is not None
        for point in result.points[11:]
    )
    assert result.mae_mw <= result.baseline_mae_mw
    assert result.mae_mw < 10.0
    assert result.training_rows == len(history)
    assert "rolling_3h_demand_mw" in result.weather_features
    assert "demand_rate_1h_mw" in result.weather_features


@dataclass(frozen=True)
class _Observation:
    timestamp: datetime
    demand_mw: float
    temperature_c: float
    humidity_percent: float = 70.0
    rainfall_mm_hr: float = 0.0
    cloud_cover_percent: float = 50.0
    wind_speed_kmh: float = 15.0
    pressure_hpa: float = 1012.0


def _weather_driven_rows() -> list[_Observation]:
    rows: list[_Observation] = []
    start = datetime(2025, 1, 1)
    previous_temperature = 28.0
    for index in range(30 * 24):
        timestamp = start + timedelta(hours=index)
        temperature = (
            28.0
            + 4.0 * math.sin(index * 1.731)
            + 2.0 * math.sin(index * 0.137)
        )
        daily_profile = 1000.0 + 120.0 * math.sin(
            2.0 * math.pi * (timestamp.hour - 8) / 24.0
        )
        rows.append(
            _Observation(
                timestamp=timestamp,
                demand_mw=daily_profile + 20.0 * (previous_temperature - 28.0),
                temperature_c=temperature,
            )
        )
        previous_temperature = temperature
    return rows


def test_replay_model_uses_ordered_fit_tuning_and_holdout_partitions():
    rows = _weather_driven_rows()[:100]

    fit_rows, tuning_rows, holdout_rows = _chronological_three_way_split(rows)

    assert [len(fit_rows), len(tuning_rows), len(holdout_rows)] == [60, 20, 20]
    assert fit_rows[-1].timestamp < tuning_rows[0].timestamp
    assert tuning_rows[-1].timestamp < holdout_rows[0].timestamp


def test_recent_moving_average_shifts_the_future_hourly_profile():
    start = datetime(2025, 1, 1)
    rows: list[_Observation] = []
    for index in range(20 * 24):
        timestamp = start + timedelta(hours=index)
        hourly_profile = 1000.0 + 100.0 * math.sin(
            2.0 * math.pi * (timestamp.hour - 8) / 24.0
        )
        recent_level_shift = 100.0 if index >= 17 * 24 else 0.0
        rows.append(
            _Observation(
                timestamp=timestamp,
                demand_mw=hourly_profile + recent_level_shift,
                temperature_c=28.0,
            )
        )

    cursor = start + timedelta(days=19, hours=10)
    history = [row for row in rows if row.timestamp <= cursor]
    day_rows = [row for row in rows if row.timestamp.date() == cursor.date()]
    result = DemoLoadForecastService().forecast_day(history, day_rows, [], cursor)
    next_hour = next(point for point in result.points if point.timestamp > cursor)

    assert result.mae_mw < result.baseline_mae_mw
    assert next_hour.forecast_demand_mw >= next_hour.historical_average_mw + 75.0


def test_validated_weather_model_responds_to_forecast_temperature():
    rows = _weather_driven_rows()
    cursor = rows[25 * 24 + 10].timestamp
    history = [row for row in rows if row.timestamp <= cursor]
    day_rows = [row for row in rows if row.timestamp.date() == cursor.date()]

    def forecasts(temperature: float) -> list[dict[str, object]]:
        return [
            {
                "forecast_timestamp": row.timestamp,
                "temperature_c": temperature,
                "confidence_score": 0.92,
                "source_count": 3,
            }
            for row in day_rows
            if row.timestamp > cursor
        ]

    service = DemoLoadForecastService()
    cool = service.forecast_day(history, day_rows, forecasts(24.0), cursor)
    hot = service.forecast_day(history, day_rows, forecasts(34.0), cursor)

    assert hot.model_mode == "ML_ACTIVE"
    assert hot.points[-2].forecast_demand_mw > cool.points[-2].forecast_demand_mw
    assert hot.points[-2].weather_impact_mw > cool.points[-2].weather_impact_mw
    assert hot.points[-2].weather_source_count == 3
    assert hot.points[-2].forecast_temperature_c == 34.0
    assert cool.points[-2].forecast_temperature_c == 24.0


def test_future_source_demand_cannot_leak_into_forecast():
    rows = _weather_driven_rows()
    cursor = rows[25 * 24 + 10].timestamp
    history = [row for row in rows if row.timestamp <= cursor]
    day_rows = [row for row in rows if row.timestamp.date() == cursor.date()]
    altered_day_rows = [
        replace(row, demand_mw=row.demand_mw + 5000.0)
        if row.timestamp > cursor
        else row
        for row in day_rows
    ]

    service = DemoLoadForecastService()
    reveal_at = cursor + timedelta(hours=2)
    normal = service.forecast_day(
        history,
        day_rows,
        [],
        cursor,
        actual_reveal_at=reveal_at,
    )
    altered = service.forecast_day(
        history,
        altered_day_rows,
        [],
        cursor,
        actual_reveal_at=reveal_at,
    )

    assert [point.forecast_demand_mw for point in normal.points] == [
        point.forecast_demand_mw for point in altered.points
    ]
    assert all(
        point.actual_demand_mw is not None
        for point in normal.points
        if cursor < point.timestamp <= reveal_at
    )


def test_forecast_tracks_sustained_load_shift_without_following_one_bad_reading():
    start = datetime(2025, 1, 1)
    rows: list[_Observation] = []
    for index in range(30 * 24):
        timestamp = start + timedelta(hours=index)
        profile = 1000.0 + 120.0 * math.sin(
            2.0 * math.pi * (timestamp.hour - 8) / 24.0
        )
        rows.append(
            _Observation(
                timestamp=timestamp,
                demand_mw=profile,
                temperature_c=28.0,
            )
        )

    cursor = start + timedelta(days=29, hours=10)
    day_start = cursor.replace(hour=0)
    isolated_bad_reading = [
        replace(row, demand_mw=100.0) if row.timestamp == cursor else row
        for row in rows
    ]
    sustained_shift = [
        replace(row, demand_mw=row.demand_mw - 280.0)
        if day_start <= row.timestamp
        else row
        for row in rows
    ]

    def next_hour(source: list[_Observation]):
        history = [row for row in source if row.timestamp <= cursor]
        day_rows = [row for row in source if row.timestamp.date() == cursor.date()]
        result = DemoLoadForecastService().forecast_day(
            history,
            day_rows,
            [],
            cursor,
        )
        point = next(item for item in result.points if item.timestamp > cursor)
        return result, point

    _, isolated_next = next_hour(isolated_bad_reading)
    shifted_result, shifted_next = next_hour(sustained_shift)

    assert isolated_next.forecast_demand_mw >= 1000.0
    assert shifted_next.forecast_demand_mw <= 850.0
    assert shifted_result.model_name == "MovingAverageProfile"
