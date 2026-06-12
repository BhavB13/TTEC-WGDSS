from typing import Any

from app.providers.weather_provider import WeatherProvider


class OpenMeteoProvider(WeatherProvider):

    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        return {
            "temperature_c": 30,
            "humidity_percent": 75,
        }

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        return [
            {
                "wind_speed_kph": 25,
            }
        ]