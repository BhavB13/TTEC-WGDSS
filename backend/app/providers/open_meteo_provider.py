from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import requests

from app.core.config import settings
from app.providers.weather_provider import WeatherProvider

logger = logging.getLogger(__name__)
TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")


class OpenMeteoDailyLimitError(RuntimeError):
    pass


@dataclass
class _CachedResponse:
    payload: dict[str, Any] | list[dict[str, Any]]
    expires_at: float


class OpenMeteoProvider(WeatherProvider):
    _usage_lock = Lock()
    _usage_date: date = datetime.now(timezone.utc).date()
    _daily_request_count = 0

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        retry_attempts: int | None = None,
        backoff_seconds: float | None = None,
        cache_ttl_seconds: int | None = None,
    ) -> None:
        self.base_url = base_url or settings.OPEN_METEO_BASE_URL
        self.model = model
        self.timeout_seconds = timeout_seconds or settings.WEATHER_TIMEOUT_SECONDS
        self.retry_attempts = retry_attempts or settings.WEATHER_RETRY_ATTEMPTS
        self.backoff_seconds = backoff_seconds or settings.WEATHER_RETRY_BACKOFF_SECONDS
        self.cache_ttl_seconds = cache_ttl_seconds or settings.WEATHER_CACHE_TTL_SECONDS
        self.session = requests.Session()
        self._response_cache: dict[tuple[tuple[str, str], ...], _CachedResponse] = {}
        self._cache_lock = Lock()
        self._request_lock = Lock()

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

    async def get_current_temperature_samples(
        self,
        coordinates: Sequence[tuple[float, float]],
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._get_current_temperature_samples_sync,
            coordinates,
        )

    async def get_temperature_forecast_samples(
        self,
        coordinates: Sequence[tuple[float, float]],
        forecast_hours: int,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._get_temperature_forecast_samples_sync,
            coordinates,
            forecast_hours,
        )

    def _get_current_temperature_samples_sync(
        self,
        coordinates: Sequence[tuple[float, float]],
    ) -> list[dict[str, Any]]:
        weather_fields = [
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "surface_pressure",
        ]
        payloads = self._request_location_payloads(
            coordinates,
            {
                "current": ",".join(weather_fields),
                "hourly": ",".join(weather_fields),
                "forecast_hours": 1,
                "timezone": "America/Port_of_Spain",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                **({"models": self.model} if self.model else {}),
            },
        )
        samples: list[dict[str, Any]] = []
        for payload in payloads:
            current = payload.get("current") or {}
            if current.get("temperature_2m") is None:
                hourly = payload.get("hourly") or {}
                index = self._nearest_hour_index(hourly.get("time", []))
                current = {
                    field: self._safe_list_value(hourly.get(field, []), index)
                    for field in weather_fields
                }
                current["time"] = self._safe_list_value(
                    hourly.get("time", []), index
                )
            samples.append(
                {
                    "timestamp": current.get("time"),
                    "temperature_c": current.get("temperature_2m"),
                    "humidity_percent": current.get("relative_humidity_2m"),
                    "rainfall_mm_hr": current.get("precipitation"),
                    "cloud_cover_percent": current.get("cloud_cover"),
                    "wind_speed_kmh": current.get("wind_speed_10m"),
                    "wind_direction_deg": current.get("wind_direction_10m"),
                    "pressure_hpa": current.get("surface_pressure"),
                    "latitude": payload.get("latitude"),
                    "longitude": payload.get("longitude"),
                }
            )
        return samples

    def _get_temperature_forecast_samples_sync(
        self,
        coordinates: Sequence[tuple[float, float]],
        forecast_hours: int,
    ) -> list[dict[str, Any]]:
        weather_fields = [
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "precipitation_probability",
            "cloud_cover",
            "wind_speed_10m",
            "wind_direction_10m",
            "surface_pressure",
        ]
        payloads = self._request_location_payloads(
            coordinates,
            {
                "hourly": ",".join(weather_fields),
                "forecast_hours": max(1, min(forecast_hours, 16 * 24)),
                "timezone": "America/Port_of_Spain",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                **({"models": self.model} if self.model else {}),
            },
        )
        locations: list[dict[str, Any]] = []
        for payload in payloads:
            hourly = payload.get("hourly") or {}
            periods = [
                {
                    "forecast_timestamp": timestamp,
                    "temperature_c": self._safe_list_value(
                        hourly.get("temperature_2m", []),
                        index,
                    ),
                    "humidity_percent": self._safe_list_value(
                        hourly.get("relative_humidity_2m", []), index
                    ),
                    "rainfall_mm_hr": self._safe_list_value(
                        hourly.get("precipitation", []), index
                    ),
                    "cloud_cover_percent": self._safe_list_value(
                        hourly.get("cloud_cover", []), index
                    ),
                    "wind_speed_kmh": self._safe_list_value(
                        hourly.get("wind_speed_10m", []), index
                    ),
                    "wind_direction_deg": self._safe_list_value(
                        hourly.get("wind_direction_10m", []), index
                    ),
                    "pressure_hpa": self._safe_list_value(
                        hourly.get("surface_pressure", []), index
                    ),
                    "precipitation_probability_percent": self._safe_list_value(
                        hourly.get("precipitation_probability", []), index
                    ),
                }
                for index, timestamp in enumerate(hourly.get("time", []))
            ]
            locations.append(
                {
                    "latitude": payload.get("latitude"),
                    "longitude": payload.get("longitude"),
                    "periods": periods,
                }
            )
        return locations

    def _request_location_payloads(
        self,
        coordinates: Sequence[tuple[float, float]],
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not coordinates:
            return []
        payload = self._request_json(
            params={
                "latitude": ",".join(str(latitude) for latitude, _ in coordinates),
                "longitude": ",".join(str(longitude) for _, longitude in coordinates),
                "cell_selection": "land",
                **params,
            }
        )
        if isinstance(payload, list):
            return [
                location for location in payload if isinstance(location, dict)
            ]
        if isinstance(payload, dict):
            return [payload]
        raise RuntimeError("Open-Meteo returned an invalid multi-location payload")

    def _get_current_weather_sync(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        current_fields = [
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
        payload = self._request_json(
            params={
                "latitude": latitude,
                "longitude": longitude,
                "cell_selection": "nearest",
                "elevation": settings.WEATHER_SITE_ALTITUDE_METERS,
                "current": ",".join(current_fields),
                "hourly": ",".join(current_fields),
                "forecast_days": 1,
                "timezone": "America/Port_of_Spain",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                **({"models": self.model} if self.model else {}),
            }
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Open-Meteo returned an invalid current payload")
        current = payload.get("current") or {}
        hourly = payload.get("hourly") or {}
        if not current:
            nearest_index = self._nearest_hour_index(hourly.get("time", []))
            current = {
                field: self._safe_list_value(hourly.get(field, []), nearest_index)
                for field in current_fields
            }
            current["time"] = self._safe_list_value(hourly.get("time", []), nearest_index)

        if current.get("temperature_2m") is None or current.get("relative_humidity_2m") is None:
            raise RuntimeError("Open-Meteo returned incomplete current weather data")
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
            "provider_name": self.provider_name,
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
                "elevation": settings.WEATHER_SITE_ALTITUDE_METERS,
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
                # `forecast_hours` means a true rolling horizon. `forecast_days`
                # would truncate a one-day request at midnight.
                "forecast_hours": max(1, min(days, 16)) * 24,
                "timezone": "America/Port_of_Spain",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                **({"models": self.model} if self.model else {}),
            }
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Open-Meteo returned an invalid forecast payload")
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
            temperature = self._safe_list_value(temperatures, index)
            humidity = self._safe_list_value(humidities, index)
            if temperature is None or humidity is None:
                continue
            forecast.append(
                {
                    "forecast_timestamp": timestamp,
                    "temperature_c": temperature,
                    "humidity_percent": humidity,
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
                        temperature,
                    ),
                    "precipitation_probability_percent": self._safe_list_value(
                        precipitation_probability,
                        index,
                        0.0,
                    ),
                    "weather_code": self._safe_list_value(weather_code, index),
                    "provider_name": self.provider_name,
                }
            )

        logger.debug("Open-Meteo forecast payload received: %s points", len(forecast))
        return forecast

    @property
    def provider_name(self) -> str:
        if self.model == "gfs_global":
            return "Open-Meteo NOAA GFS"
        if self.model:
            return f"Open-Meteo {self.model}"
        return "Open-Meteo Best Match"

    def _request_json(
        self,
        params: dict[str, Any],
    ) -> dict[str, Any] | list[dict[str, Any]]:
        url = self.base_url
        last_error: Exception | None = None
        cache_key = tuple(sorted((key, str(value)) for key, value in params.items()))

        with self._cache_lock:
            cached = self._response_cache.get(cache_key)
            if cached and cached.expires_at > time.monotonic():
                return copy.deepcopy(cached.payload)

        for attempt in range(1, self.retry_attempts + 1):
            try:
                self._reserve_request()
                with self._request_lock:
                    response = self.session.get(
                        url,
                        params=params,
                        timeout=self.timeout_seconds,
                    )
                response.raise_for_status()
                payload = response.json()
                with self._cache_lock:
                    self._response_cache[cache_key] = _CachedResponse(
                        payload=copy.deepcopy(payload),
                        expires_at=time.monotonic() + self.cache_ttl_seconds,
                    )
                return payload
            except OpenMeteoDailyLimitError:
                with self._cache_lock:
                    stale = self._response_cache.get(cache_key)
                    if stale:
                        logger.warning(
                            "Serving cached Open-Meteo response at daily safety limit"
                        )
                        return copy.deepcopy(stale.payload)
                raise
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

        with self._cache_lock:
            stale = self._response_cache.get(cache_key)
            if stale:
                logger.warning("Serving stale Open-Meteo response after provider failure")
                return copy.deepcopy(stale.payload)

        raise RuntimeError("Open-Meteo request failed") from last_error

    @classmethod
    def _reserve_request(cls) -> None:
        today = datetime.now(timezone.utc).date()
        with cls._usage_lock:
            if cls._usage_date != today:
                cls._usage_date = today
                cls._daily_request_count = 0
            if cls._daily_request_count >= settings.OPEN_METEO_DAILY_REQUEST_LIMIT:
                raise OpenMeteoDailyLimitError(
                    "Open-Meteo daily request safety limit reached"
                )
            cls._daily_request_count += 1

    @classmethod
    def usage_state(cls) -> dict[str, int | str]:
        today = datetime.now(timezone.utc).date()
        with cls._usage_lock:
            if cls._usage_date != today:
                cls._usage_date = today
                cls._daily_request_count = 0
            return {
                "date": cls._usage_date.isoformat(),
                "count": cls._daily_request_count,
                "limit": settings.OPEN_METEO_DAILY_REQUEST_LIMIT,
            }

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
    def _nearest_hour_index(times: list[Any]) -> int:
        if not times:
            return 0

        now = datetime.now(TRINIDAD_TZ)
        nearest_index = 0
        nearest_delta: float | None = None
        for index, value in enumerate(times):
            try:
                parsed = datetime.fromisoformat(str(value))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=TRINIDAD_TZ)
                delta = abs((parsed - now).total_seconds())
            except (TypeError, ValueError):
                continue
            if nearest_delta is None or delta < nearest_delta:
                nearest_index = index
                nearest_delta = delta
        return nearest_index

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
