from app.providers.met_norway_provider import MetNorwayProvider


def test_met_norway_provider_normalizes_compact_forecast(monkeypatch):
    provider = MetNorwayProvider(
        user_agent="WGDSS-Test/1.0",
        retry_attempts=1,
    )
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda params: {
            "properties": {
                "timeseries": [
                    {
                        "time": "2026-06-29T13:00:00Z",
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 29.4,
                                    "relative_humidity": 76.0,
                                    "cloud_area_fraction": 48.0,
                                    "wind_speed": 4.0,
                                    "wind_from_direction": 82.0,
                                    "air_pressure_at_sea_level": 1014.0,
                                }
                            },
                            "next_1_hours": {
                                "summary": {"symbol_code": "rainshowers_day"},
                                "details": {"precipitation_amount": 0.6},
                            },
                        },
                    }
                ]
            }
        },
    )

    forecast = provider._get_forecast_sync(10.5953, -61.3372, days=1)

    assert len(forecast) == 1
    assert forecast[0]["temperature_c"] == 29.4
    assert forecast[0]["humidity_percent"] == 76.0
    assert forecast[0]["rainfall_mm_hr"] == 0.6
    assert forecast[0]["wind_speed_kmh"] == 14.4
    assert forecast[0]["weather_condition"] == "Rain showers"
    assert forecast[0]["provider_name"] == "MET Norway"
