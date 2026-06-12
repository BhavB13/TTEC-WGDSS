from typing import Any

from app.providers.weather_provider import WeatherProvider


class OpenMeteoProvider(WeatherProvider):
    """
    Open-Meteo weather provider implementation.

    This provider will eventually retrieve weather data
    from the Open-Meteo API.
    """

    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "OpenMeteoProvider.get_current_weather not implemented."
        )

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "OpenMeteoProvider.get_forecast not implemented."
        )