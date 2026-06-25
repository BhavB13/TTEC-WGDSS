from abc import ABC, abstractmethod
from typing import Any


class WeatherProvider(ABC):
    """
    Abstract interface for weather data providers.

    All weather providers must implement this interface.
    """

    @abstractmethod
    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        """
        Retrieve current weather conditions.
        """
        pass

    @abstractmethod
    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Retrieve weather forecast data.
        """
        pass