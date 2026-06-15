from typing import Any

from app.providers.weather_provider import WeatherProvider


class OpenMeteoProvider(WeatherProvider):

    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        return {
            "temperature_c": 30.5,
            "humidity_percent": 75,
            "wind_speed_kph": 22,
            "wind_direction_deg": 120,
            "pressure_hpa": 1012,
            "precipitation_mm": 0,
            "provider_name": "Open-Meteo",
        }

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        return [
            {
                "forecast_timestamp": "2026-06-15T12:00:00Z",
                "temperature_c": 31,
                "wind_speed_kph": 25,
                "precipitation_probability_percent": 45,
                "confidence_score": 0.88,
            }
        ]