from datetime import datetime, timedelta

from app.models.demand_forecast import ForecastTrainingRow
from app.services.similar_period_service import similar_period_forecast


def _row(
    feature_timestamp: datetime,
    target_demand_mw: float,
    temperature_c: float,
) -> ForecastTrainingRow:
    return ForecastTrainingRow(
        feature_timestamp=feature_timestamp,
        horizon_hours=1,
        target_timestamp=feature_timestamp + timedelta(hours=1),
        target_demand_mw=target_demand_mw,
        current_demand_mw=target_demand_mw - 20,
        lag_1h_demand_mw=target_demand_mw - 30,
        demand_rate_1h_mw=10,
        hour_of_day=feature_timestamp.hour,
        day_of_week=feature_timestamp.weekday(),
        temperature_c=temperature_c - 1,
        forecast_temperature_c=temperature_c,
        humidity_percent=72,
        forecast_rainfall_mm_hr=0.2,
        forecast_cloud_cover_percent=45,
        source_quality_status="GOOD",
    )


def test_similar_periods_prioritize_same_hour_and_nearby_temperature():
    query = _row(datetime(2026, 7, 15, 15), 0, 25)
    history = [
        _row(datetime(2026, 7, day, 15), 1000 + day, 24.5 + day / 20)
        for day in range(1, 10)
    ]
    history.append(_row(datetime(2026, 7, 10, 10), 1600, 25))

    result = similar_period_forecast(history, query, limit=5)

    assert result.forecast_mw is not None
    assert 1000 < result.forecast_mw < 1100
    assert len(result.examples) == 5
    assert all(example.target_timestamp.hour == 16 for example in result.examples)
    assert all(
        abs((example.forecast_temperature_c or 0) - 25) <= 4
        for example in result.examples
    )


def test_similar_periods_never_use_future_or_not_yet_observed_targets():
    query = _row(datetime(2026, 7, 15, 15), 0, 29)
    known = _row(datetime(2026, 7, 14, 15), 1050, 29)
    target_not_known = _row(datetime(2026, 7, 15, 15), 5000, 29)
    future = _row(datetime(2026, 7, 16, 15), 6000, 29)

    result = similar_period_forecast(
        [known, target_not_known, future],
        query,
    )

    assert result.forecast_mw == 1050
    assert [example.target_demand_mw for example in result.examples] == [1050]
