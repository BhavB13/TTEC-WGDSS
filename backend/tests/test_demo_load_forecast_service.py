from datetime import datetime

from app.services.demo_load_forecast_service import DemoLoadForecastService
from app.services.demo_replay_service import _generate_demo_year


def test_demo_forecast_uses_weather_and_never_reveals_future_actuals():
    rows = _generate_demo_year(2025)
    cursor = datetime(2025, 6, 15, 10)
    history = [row for row in rows if row.timestamp <= cursor]
    day_rows = [
        row
        for row in rows
        if datetime(2025, 6, 15) <= row.timestamp <= datetime(2025, 6, 15, 23)
    ]

    def forecasts(temperature: float):
        return [
            {
                "forecast_timestamp": row.timestamp,
                "temperature_c": temperature,
                "humidity_percent": row.humidity_percent,
                "rainfall_mm_hr": row.rainfall_mm_hr,
                "cloud_cover_percent": row.cloud_cover_percent,
                "wind_speed_kmh": row.wind_speed_kmh,
                "pressure_hpa": row.pressure_hpa,
                "confidence_score": 0.92,
                "source_count": 3,
            }
            for row in day_rows
            if row.timestamp > cursor
        ]

    service = DemoLoadForecastService()
    cool = service.forecast_day(history, day_rows, forecasts(26), cursor)
    hot = service.forecast_day(history, day_rows, forecasts(34), cursor)

    assert hot.points[14].forecast_demand_mw > cool.points[14].forecast_demand_mw
    assert hot.points[14].weather_impact_mw > cool.points[14].weather_impact_mw
    assert all(point.actual_demand_mw is None for point in hot.points[11:])
    assert hot.mae_mw <= hot.baseline_mae_mw
    assert hot.training_rows == len(history)
    assert hot.points[14].weather_source_count == 3

