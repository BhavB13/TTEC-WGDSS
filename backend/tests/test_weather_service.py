import pytest

from app.providers.weather_provider import WeatherProvider
from app.services.weather_service import WeatherService


class FailingProvider(WeatherProvider):
    async def get_current_weather(self, latitude: float, longitude: float):
        raise RuntimeError("provider unavailable")

    async def get_forecast(self, latitude: float, longitude: float, days: int = 7):
        raise RuntimeError("provider unavailable")


class WorkingProvider(WeatherProvider):
    async def get_current_weather(self, latitude: float, longitude: float):
        return {
            "timestamp": "2026-06-27T12:00",
            "temperature_c": 30,
            "humidity_percent": 75,
            "rainfall_mm_hr": 0.2,
            "cloud_cover_percent": 40,
            "wind_speed_kmh": 15,
            "weather_condition": "Partly cloudy",
            "heat_index_c": 34,
            "provider_name": "Fallback Test",
        }

    async def get_forecast(self, latitude: float, longitude: float, days: int = 7):
        return [
            {
                "forecast_timestamp": "2026-06-27T13:00",
                "temperature_c": 31,
                "humidity_percent": 72,
                "rainfall_mm_hr": 0,
                "cloud_cover_percent": 35,
                "wind_speed_kmh": 16,
                "weather_condition": "Partly cloudy",
                "heat_index_c": 35,
                "precipitation_probability_percent": 10,
                "provider_name": "Fallback Test",
            }
        ]


class OpenMeteoForecastProvider(WorkingProvider):
    async def get_forecast(self, latitude: float, longitude: float, days: int = 7):
        return [
            {
                "forecast_timestamp": "2026-06-27T13:00:00-04:00",
                "temperature_c": 30,
                "humidity_percent": 70,
                "rainfall_mm_hr": 0,
                "cloud_cover_percent": 40,
                "wind_speed_kmh": 14,
                "weather_condition": "Partly cloudy",
                "precipitation_probability_percent": 30,
                "provider_name": "Open-Meteo",
            }
        ]


class MetNorwayForecastProvider(WorkingProvider):
    async def get_forecast(self, latitude: float, longitude: float, days: int = 7):
        return [
            {
                "forecast_timestamp": "2026-06-27T17:00:00Z",
                "temperature_c": 32,
                "humidity_percent": 74,
                "rainfall_mm_hr": 0.2,
                "cloud_cover_percent": 60,
                "wind_speed_kmh": 18,
                "weather_condition": "Rain showers",
                "precipitation_probability_percent": 70,
                "provider_name": "MET Norway",
            }
        ]


class GfsForecastProvider(WorkingProvider):
    async def get_forecast(self, latitude: float, longitude: float, days: int = 7):
        return [
            {
                "forecast_timestamp": "2026-06-27T13:04:00-04:00",
                "temperature_c": 31,
                "humidity_percent": 73,
                "rainfall_mm_hr": None,
                "cloud_cover_percent": 50,
                "wind_speed_kmh": 15,
                "weather_condition": "Partly cloudy",
                "precipitation_probability_percent": 45,
                "provider_name": "Open-Meteo NOAA GFS",
            }
        ]


@pytest.mark.asyncio
async def test_weather_service_uses_fallback_and_marks_it():
    service = WeatherService(
        provider=FailingProvider(),
        fallback_provider=WorkingProvider(),
        cache_ttl_seconds=60,
    )

    current = await service.get_current_weather(10.69, -61.22)
    forecast = await service.get_forecast(10.69, -61.22, days=1)

    assert current["temperature_c"] == 30
    assert current["timestamp"].endswith("-04:00")
    assert forecast[0]["temperature_c"] == 31
    assert service.last_current_fallback_used is True
    assert service.last_forecast_fallback_used is True


@pytest.mark.asyncio
async def test_weather_service_reconciles_hourly_forecast_sources():
    service = WeatherService(
        provider=OpenMeteoForecastProvider(),
        fallback_provider=WorkingProvider(),
        consensus_providers=[MetNorwayForecastProvider()],
        cache_ttl_seconds=60,
    )

    forecast = await service.get_forecast(10.5953, -61.3372, days=1)

    assert len(forecast) == 1
    assert forecast[0]["temperature_c"] == 30.8
    assert forecast[0]["humidity_percent"] == 71.5
    assert forecast[0]["precipitation_probability_percent"] == 70
    assert forecast[0]["source_count"] == 2
    assert forecast[0]["source_names"] == ["Open-Meteo", "MET Norway"]
    assert forecast[0]["provider_name"] == "Consensus (Open-Meteo + MET Norway)"
    assert forecast[0]["confidence_score"] > 0.8
    assert service.last_forecast_consensus_degraded is False


@pytest.mark.asyncio
async def test_weather_service_synchronizes_three_sources_and_ignores_missing_field():
    service = WeatherService(
        provider=OpenMeteoForecastProvider(),
        fallback_provider=WorkingProvider(),
        consensus_providers=[MetNorwayForecastProvider(), GfsForecastProvider()],
        cache_ttl_seconds=60,
    )

    forecast = await service.get_forecast(10.5953, -61.3372, days=1)

    assert len(forecast) == 1
    assert forecast[0]["forecast_timestamp"] == "2026-06-27T13:00:00-04:00"
    assert forecast[0]["source_count"] == 3
    assert forecast[0]["source_sync_status"] == "COMPLETE"
    assert forecast[0]["field_source_counts"]["rainfall_mm_hr"] == 2
    assert forecast[0]["rainfall_mm_hr"] > 0
    assert service.last_forecast_consensus_degraded is False


@pytest.mark.asyncio
async def test_weather_service_marks_consensus_degraded_when_one_of_three_fails():
    service = WeatherService(
        provider=OpenMeteoForecastProvider(),
        fallback_provider=WorkingProvider(),
        consensus_providers=[MetNorwayForecastProvider(), FailingProvider()],
        cache_ttl_seconds=60,
    )

    forecast = await service.get_forecast(10.5953, -61.3372, days=1)

    assert forecast[0]["source_count"] == 2
    assert forecast[0]["source_sync_status"] == "DEGRADED"
    assert service.last_forecast_consensus_degraded is True
