from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import requests

from app.core.config import settings
from app.providers.weather_provider import WeatherProvider

logger = logging.getLogger(__name__)


class WeatherAPIProvider(WeatherProvider):
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        retry_attempts: int | None = None,
        backoff_seconds: float | None = None,
    ) -> None:
        self.base_url = base_url or settings.WEATHER_API_BASE_URL
        self.api_key = api_key if api_key is not None else settings.WEATHER_API_KEY
        self.timeout_seconds = timeout_seconds or settings.WEATHER_TIMEOUT_SECONDS
        self.retry_attempts = retry_attempts or settings.WEATHER_RETRY_ATTEMPTS
        self.backoff_seconds = backoff_seconds or settings.WEATHER_RETRY_BACKOFF_SECONDS
        self.session = requests.Session()

    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._get_current_weather_sync,
            latitude,
            longitude,
        )

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._get_forecast_sync,
            latitude,
            longitude,
            days,
        )

    def _get_current_weather_sync(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        payload = self._request_json(
            path="current.json",
            params={
                "q": f"{latitude},{longitude}",
                "aqi": "no",
            },
        )
        current = payload.get("current") or {}
        location = payload.get("location") or {}
        condition = current.get("condition") or {}

        logger.debug("WeatherAPI current payload received")
        return {
            "timestamp": current.get("last_updated"),
            "temperature_c": current.get("temp_c"),
            "humidity_percent": current.get("humidity"),
            "rainfall_mm_hr": current.get("precip_mm", 0.0),
            "cloud_cover_percent": current.get("cloud", 0.0),
            "wind_speed_kmh": current.get("wind_kph", 0.0),
            "wind_direction_deg": current.get("wind_degree"),
            "pressure_hpa": current.get("pressure_mb"),
            "weather_condition": condition.get("text", "Unknown"),
            "heat_index_c": current.get("heatindex_c", current.get("temp_c")),
            "weather_code": condition.get("code"),
            "provider_name": "WeatherAPI",
            "location_name": location.get("name"),
        }

    def _get_forecast_sync(
        self,
        latitude: float,
        longitude: float,
        days: int,
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            path="forecast.json",
            params={
                "q": f"{latitude},{longitude}",
                "days": min(max(days, 1), 14),
                "aqi": "no",
                "alerts": "no",
            },
        )

        forecast: list[dict[str, Any]] = []
        for day in payload.get("forecast", {}).get("forecastday", []):
            for hour in day.get("hour", []):
                condition = hour.get("condition") or {}
                forecast.append(
                    {
                        "forecast_timestamp": hour.get("time"),
                        "temperature_c": hour.get("temp_c"),
                        "humidity_percent": hour.get("humidity"),
                        "rainfall_mm_hr": hour.get("precip_mm", 0.0),
                        "cloud_cover_percent": hour.get("cloud", 0.0),
                        "wind_speed_kmh": hour.get("wind_kph", 0.0),
                        "weather_condition": condition.get("text", "Unknown"),
                        "heat_index_c": hour.get("heatindex_c", hour.get("temp_c")),
                        "precipitation_probability_percent": hour.get(
                            "chance_of_rain",
                            0.0,
                        ),
                        "weather_code": condition.get("code"),
                        "provider_name": "WeatherAPI",
                    }
                )

        logger.debug("WeatherAPI forecast payload received: %s points", len(forecast))
        return forecast

    def _request_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("WeatherAPI API key is not configured")

        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        query = {"key": self.api_key, **params}
        last_error: Exception | None = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = self.session.get(url, params=query, timeout=self.timeout_seconds)
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # pragma: no cover - defensive logging
                last_error = exc
                logger.warning(
                    "WeatherAPI request failed on attempt %s/%s: %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )
                if attempt < self.retry_attempts:
                    time.sleep(self.backoff_seconds)

        raise RuntimeError("WeatherAPI request failed") from last_error
