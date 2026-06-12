from app.providers.weather_provider import WeatherProvider


class WeatherService:
    """
    Service layer for weather operations.
    """

    def __init__(self, provider: WeatherProvider):
        self.provider = provider

    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
    ):
        return await self.provider.get_current_weather(
            latitude,
            longitude,
        )

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ):
        return await self.provider.get_forecast(
            latitude,
            longitude,
            days,
        )
        