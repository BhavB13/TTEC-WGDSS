from typing import Any

from app.providers.weather_provider import WeatherProvider


class WeatherAPIProvider(WeatherProvider):
    """
    WeatherAPI.com weather provider implementation.

    This provider serves as a fallback weather source
    when Open-Meteo is unavailable.
    """

    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "WeatherAPIProvider.get_current_weather not implemented."
        )

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "WeatherAPIProvider.get_forecast not implemented."
        )