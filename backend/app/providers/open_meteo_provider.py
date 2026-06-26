from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import requests

from app.core.config import settings
from app.providers.weather_provider import WeatherProvider

logger = logging.getLogger(__name__)


class OpenMeteoProvider(WeatherProvider):
    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        retry_attempts: int | None = None,
        backoff_seconds: float | None = None,
    ) -> None:
        self.base_url = base_url or settings.OPEN_METEO_BASE_URL
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
            params={
                "latitude": latitude,
                "longitude": longitude,
                "cell_selection": "nearest",
                "elevation": "nan",
                "current": ",".join(
                    [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "apparent_temperature",
                        "precipitation",
                        "rain",
                        "showers",
                        "cloud_cover",
                        "wind_speed_10m",
                        "wind_direction_10m",
                        "surface_pressure",
                        "weather_code",
                    ]
                ),
                "timezone": "America/Port_of_Spain",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
            }
        )
        current = payload.get("current") or {}
        hourly = payload.get("hourly") or {}
        if not current:
            current = {
                "time": self._safe_list_value(hourly.get("time", []), 0),
                "temperature_2m": self._safe_list_value(hourly.get("temperature_2m", []), 0),
                "relative_humidity_2m": self._safe_list_value(hourly.get("relative_humidity_2m", []), 0),
                "precipitation": self._safe_list_value(hourly.get("precipitation", []), 0),
                "rain": self._safe_list_value(hourly.get("rain", []), 0, 0.0),
                "cloud_cover": self._safe_list_value(hourly.get("cloud_cover", []), 0, 0.0),
                "wind_speed_10m": self._safe_list_value(hourly.get("wind_speed_10m", []), 0, 0.0),
                "wind_direction_10m": self._safe_list_value(hourly.get("wind_direction_10m", []), 0),
                "surface_pressure": self._safe_list_value(hourly.get("surface_pressure", []), 0),
                "weather_code": self._safe_list_value(hourly.get("weather_code", []), 0),
                "apparent_temperature": self._safe_list_value(hourly.get("apparent_temperature", []), 0),
            }
        logger.debug("Open-Meteo current payload received")

        return {
            "timestamp": current.get("time"),
            "temperature_c": current.get("temperature_2m"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "rainfall_mm_hr": current.get("precipitation")
            if current.get("precipitation") is not None
            else current.get("rain", 0.0),
            "cloud_cover_percent": current.get("cloud_cover", 0.0),
            "wind_speed_kmh": current.get("wind_speed_10m", 0.0),
            "wind_direction_deg": current.get("wind_direction_10m"),
            "pressure_hpa": current.get("surface_pressure"),
            "weather_condition": self._describe_weather_code(
                current.get("weather_code")
            ),
            "heat_index_c": current.get(
                "apparent_temperature",
                current.get("temperature_2m"),
            ),
            "weather_code": current.get("weather_code"),
            "pressure_hpa": current.get("surface_pressure"),
            "provider_name": "Open-Meteo",
        }

    def _get_forecast_sync(
        self,
        latitude: float,
        longitude: float,
        days: int,
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            params={
                "latitude": latitude,
                "longitude": longitude,
                "cell_selection": "nearest",
                "elevation": "nan",
                "hourly": ",".join(
                    [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "precipitation",
                        "rain",
                        "showers",
                        "cloud_cover",
                        "wind_speed_10m",
                        "weather_code",
                        "apparent_temperature",
                        "precipitation_probability",
                    ]
                ),
                "forecast_days": days,
                "timezone": "America/Port_of_Spain",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
            }
        )

        hourly = payload.get("hourly") or {}
        times = hourly.get("time", [])
        temperatures = hourly.get("temperature_2m", [])
        humidities = hourly.get("relative_humidity_2m", [])
        precipitation = hourly.get("precipitation", [])
        rain = hourly.get("rain", [])
        showers = hourly.get("showers", [])
        cloud_cover = hourly.get("cloud_cover", [])
        wind_speed = hourly.get("wind_speed_10m", [])
        weather_code = hourly.get("weather_code", [])
        apparent_temperature = hourly.get("apparent_temperature", [])
        precipitation_probability = hourly.get("precipitation_probability", [])

        forecast: list[dict[str, Any]] = []
        for index, timestamp in enumerate(times):
            forecast.append(
                {
                    "forecast_timestamp": timestamp,
                    "temperature_c": self._safe_list_value(temperatures, index),
                    "humidity_percent": self._safe_list_value(humidities, index),
                    "rainfall_mm_hr": self._safe_list_value(precipitation, index)
                    if self._safe_list_value(precipitation, index) is not None
                    else self._safe_list_value(rain, index, 0.0),
                    "cloud_cover_percent": self._safe_list_value(cloud_cover, index, 0.0),
                    "wind_speed_kmh": self._safe_list_value(wind_speed, index, 0.0),
                    "weather_condition": self._describe_weather_code(
                        self._safe_list_value(weather_code, index)
                    ),
                    "heat_index_c": self._safe_list_value(
                        apparent_temperature,
                        index,
                        self._safe_list_value(temperatures, index),
                    ),
                    "precipitation_probability_percent": self._safe_list_value(
                        precipitation_probability,
                        index,
                        0.0,
                    ),
                    "weather_code": self._safe_list_value(weather_code, index),
                    "provider_name": "Open-Meteo",
                }
            )

        logger.debug("Open-Meteo forecast payload received: %s points", len(forecast))
        return forecast

    def _request_json(self, params: dict[str, Any]) -> dict[str, Any]:
        url = self.base_url
        last_error: Exception | None = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout_seconds)
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # pragma: no cover - defensive logging
                last_error = exc
                logger.warning(
                    "Open-Meteo request failed on attempt %s/%s: %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )
                if attempt < self.retry_attempts:
                    time.sleep(self.backoff_seconds)

        raise RuntimeError("Open-Meteo request failed") from last_error

    @staticmethod
    def _safe_list_value(
        values: list[Any],
        index: int,
        default: Any = None,
    ) -> Any:
        try:
            return values[index]
        except Exception:
            return default

    @staticmethod
    def _describe_weather_code(code: Any) -> str:
        mapping = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            80: "Rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            95: "Thunderstorm",
            96: "Thunderstorm with hail",
            99: "Thunderstorm with heavy hail",
        }
        try:
            return mapping.get(int(code), "Unknown")
        except Exception:
            return "Unknown"
