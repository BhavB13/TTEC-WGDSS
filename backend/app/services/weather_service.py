from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.providers.open_meteo_provider import OpenMeteoProvider
from app.providers.weather_provider import WeatherProvider

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class WeatherService:
    def __init__(
        self,
        provider: WeatherProvider | None = None,
        fallback_provider: WeatherProvider | None = None,
        cache_ttl_seconds: int | None = None,
    ) -> None:
        self.primary_provider = provider or OpenMeteoProvider()
        self.fallback_provider = fallback_provider or OpenMeteoProvider(
            base_url="https://api.open-meteo.com/v1/forecast"
        )
        self.cache_ttl_seconds = cache_ttl_seconds or settings.WEATHER_CACHE_TTL_SECONDS
        self._cache: dict[str, _CacheEntry] = {}
        self._cache_lock = asyncio.Lock()

    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        cache_key = self._cache_key("current", latitude, longitude)
        if not force_refresh:
            cached = await self._get_cache(cache_key)
            if cached is not None:
                return cached

        raw = await self._fetch_current_with_failover(latitude, longitude)
        normalized = self._normalize_current_weather(raw)
        await self._set_cache(cache_key, normalized)
        return copy.deepcopy(normalized)

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        cache_key = self._cache_key("forecast", latitude, longitude, days)
        if not force_refresh:
            cached = await self._get_cache(cache_key)
            if cached is not None:
                return cached

        raw = await self._fetch_forecast_with_failover(latitude, longitude, days)
        normalized = [self._normalize_forecast_item(item) for item in raw]
        normalized.sort(key=self._forecast_sort_key)
        await self._set_cache(cache_key, normalized)
        return copy.deepcopy(normalized)

    async def get_weather_bundle(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        current_task = self.get_current_weather(latitude, longitude, force_refresh=force_refresh)
        forecast_task = self.get_forecast(latitude, longitude, days, force_refresh=force_refresh)
        current_weather, forecast = await asyncio.gather(current_task, forecast_task)
        return {"current": current_weather, "forecast": forecast}

    async def _fetch_current_with_failover(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        providers = [self.primary_provider, self.fallback_provider]
        last_error: Exception | None = None

        for provider in providers:
            try:
                payload = await provider.get_current_weather(latitude, longitude)
                logger.info("Weather fetched from %s", provider.__class__.__name__)
                return payload
            except Exception as exc:  # pragma: no cover - defensive logging
                last_error = exc
                logger.warning(
                    "Weather provider %s failed: %s",
                    provider.__class__.__name__,
                    exc,
                )

        raise RuntimeError("All weather providers failed") from last_error

    async def _fetch_forecast_with_failover(
        self,
        latitude: float,
        longitude: float,
        days: int,
    ) -> list[dict[str, Any]]:
        providers = [self.primary_provider, self.fallback_provider]
        last_error: Exception | None = None

        for provider in providers:
            try:
                payload = await provider.get_forecast(latitude, longitude, days)
                logger.info("Forecast fetched from %s", provider.__class__.__name__)
                return payload
            except Exception as exc:  # pragma: no cover - defensive logging
                last_error = exc
                logger.warning(
                    "Forecast provider %s failed: %s",
                    provider.__class__.__name__,
                    exc,
                )

        raise RuntimeError("All weather providers failed") from last_error

    async def _get_cache(self, key: str) -> Any | None:
        async with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None or entry.expires_at < time.monotonic():
                self._cache.pop(key, None)
                return None
            return copy.deepcopy(entry.value)

    async def _set_cache(self, key: str, value: Any) -> None:
        async with self._cache_lock:
            self._cache[key] = _CacheEntry(
                value=copy.deepcopy(value),
                expires_at=time.monotonic() + self.cache_ttl_seconds,
            )

    def _normalize_current_weather(self, data: dict[str, Any]) -> dict[str, Any]:
        temperature_c = self._first_number(
            data,
            ["temperature_c", "temperature_2m", "temp_c"],
        )
        humidity_percent = self._first_number(
            data,
            ["humidity_percent", "relative_humidity_2m", "humidity"],
        )
        rainfall_mm_hr = self._first_number(
            data,
            ["rainfall_mm_hr", "precipitation", "precip_mm", "rain"],
            default=0.0,
        )
        cloud_cover_percent = self._first_number(
            data,
            ["cloud_cover_percent", "cloud_cover", "cloud"],
            default=0.0,
        )
        wind_speed_kmh = self._first_number(
            data,
            ["wind_speed_kmh", "wind_speed_10m", "wind_kph"],
            default=0.0,
        )
        wind_direction_deg = self._first_number(
            data,
            ["wind_direction_deg", "wind_direction_10m", "wind_degree"],
        )
        pressure_hpa = self._first_number(
            data,
            ["pressure_hpa", "pressure_mb", "surface_pressure"],
        )
        weather_condition = str(
            data.get("weather_condition")
            or (data.get("condition") or {}).get("text")
            or self._describe_weather_code(data.get("weather_code"))
            or "Unknown"
        )
        heat_index_c = self._first_number(
            data,
            ["heat_index_c", "heatindex_c", "apparent_temperature"],
            default=self._calculate_heat_index(temperature_c, humidity_percent),
        )
        timestamp = self._normalize_timestamp(data.get("timestamp") or data.get("last_updated"))

        return {
            "timestamp": timestamp,
            "temperature_c": temperature_c,
            "humidity_percent": humidity_percent,
            "rainfall_mm_hr": rainfall_mm_hr,
            "cloud_cover_percent": cloud_cover_percent,
            "wind_speed_kmh": wind_speed_kmh,
            "weather_condition": weather_condition,
            "heat_index_c": heat_index_c,
            "rain_severity": self._rain_severity(rainfall_mm_hr),
            "wind_direction_deg": wind_direction_deg,
            "pressure_hpa": pressure_hpa,
            "provider_name": data.get("provider_name", "Unknown"),
        }

    def _normalize_forecast_item(self, data: dict[str, Any]) -> dict[str, Any]:
        temperature_c = self._first_number(
            data,
            ["temperature_c", "temperature_2m", "temp_c"],
        )
        humidity_percent = self._first_number(
            data,
            ["humidity_percent", "relative_humidity_2m", "humidity"],
        )
        rainfall_mm_hr = self._first_number(
            data,
            ["rainfall_mm_hr", "precipitation", "precip_mm", "rain"],
            default=0.0,
        )
        cloud_cover_percent = self._first_number(
            data,
            ["cloud_cover_percent", "cloud_cover", "cloud"],
            default=0.0,
        )
        wind_speed_kmh = self._first_number(
            data,
            ["wind_speed_kmh", "wind_speed_10m", "wind_kph"],
            default=0.0,
        )
        weather_condition = str(
            data.get("weather_condition")
            or (data.get("condition") or {}).get("text")
            or self._describe_weather_code(data.get("weather_code"))
            or "Unknown"
        )
        heat_index_c = self._first_number(
            data,
            ["heat_index_c", "heatindex_c", "apparent_temperature"],
            default=self._calculate_heat_index(temperature_c, humidity_percent),
        )
        precipitation_probability = self._first_number(
            data,
            ["precipitation_probability_percent", "chance_of_rain", "precipitation_probability"],
            default=self._rain_probability(rainfall_mm_hr),
        )
        timestamp = self._normalize_timestamp(
            data.get("forecast_timestamp") or data.get("time") or data.get("time_epoch")
        )

        confidence_score = self._estimate_confidence(data.get("provider_name", "Unknown"))

        return {
            "forecast_timestamp": timestamp,
            "temperature_c": temperature_c,
            "humidity_percent": humidity_percent,
            "rainfall_mm_hr": rainfall_mm_hr,
            "cloud_cover_percent": cloud_cover_percent,
            "wind_speed_kmh": wind_speed_kmh,
            "weather_condition": weather_condition,
            "heat_index_c": heat_index_c,
            "precipitation_probability_percent": precipitation_probability,
            "confidence_score": confidence_score,
            "rain_severity": self._rain_severity(rainfall_mm_hr),
            "provider_name": data.get("provider_name", "Unknown"),
        }

    def _cache_key(self, *parts: Any) -> str:
        return ":".join(str(part) for part in parts)

    @staticmethod
    def _first_number(
        data: dict[str, Any],
        keys: list[str],
        default: float | None = 0.0,
    ) -> float:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return float(default if default is not None else 0.0)

    @staticmethod
    def _normalize_timestamp(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        parsed = WeatherService._parse_datetime(value)
        if parsed is not None:
            return parsed.isoformat()
        return str(value)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)

        text = str(value).strip()
        if not text:
            return None

        if text.isdigit():
            try:
                return datetime.fromtimestamp(float(text), tz=timezone.utc)
            except (OverflowError, ValueError):
                return None

        candidates = (
            text,
            text.replace("Z", "+00:00"),
            text.replace(" ", "T"),
        )
        for candidate in candidates:
            try:
                parsed = datetime.fromisoformat(candidate)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        for fmt in (
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None

    @staticmethod
    def _forecast_sort_key(item: dict[str, Any]) -> datetime:
        parsed = WeatherService._parse_datetime(item.get("forecast_timestamp"))
        return parsed or datetime.max.replace(tzinfo=timezone.utc)

    @staticmethod
    def _calculate_heat_index(temperature_c: float, humidity_percent: float) -> float:
        if temperature_c <= 0:
            return temperature_c
        # Approximation good enough for an operational decision aid.
        humidity_factor = max(0.0, humidity_percent)
        return round(
            temperature_c
            + 0.033 * humidity_factor
            - 0.70,
            2,
        )

    @staticmethod
    def _rain_severity(rainfall_mm_hr: float) -> str:
        if rainfall_mm_hr <= 0:
            return "DRY"
        if rainfall_mm_hr < 2:
            return "LIGHT"
        if rainfall_mm_hr < 7:
            return "MODERATE"
        if rainfall_mm_hr < 20:
            return "HEAVY"
        return "EXTREME"

    @staticmethod
    def _rain_probability(rainfall_mm_hr: float) -> float:
        return max(0.0, min(100.0, rainfall_mm_hr * 8.0))

    @staticmethod
    def _estimate_confidence(provider_name: str) -> float:
        provider = provider_name.lower()
        if "open-meteo" in provider:
            return 0.92
        if "weatherapi" in provider:
            return 0.88
        return 0.75

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
