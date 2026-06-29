from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from typing import Any

import requests

from app.core.config import settings
from app.providers.weather_provider import WeatherProvider

logger = logging.getLogger(__name__)


@dataclass
class _CachedResponse:
    payload: dict[str, Any]
    expires_at: datetime
    last_modified: str | None = None
    etag: str | None = None


class MetNorwayProvider(WeatherProvider):
    """Independent global forecast source used to cross-check Open-Meteo."""

    def __init__(
        self,
        base_url: str | None = None,
        user_agent: str | None = None,
        timeout_seconds: float | None = None,
        retry_attempts: int | None = None,
        backoff_seconds: float | None = None,
    ) -> None:
        self.base_url = base_url or settings.MET_NORWAY_BASE_URL
        self.user_agent = user_agent or settings.MET_NORWAY_USER_AGENT
        self.timeout_seconds = timeout_seconds or settings.WEATHER_TIMEOUT_SECONDS
        self.retry_attempts = retry_attempts or settings.WEATHER_RETRY_ATTEMPTS
        self.backoff_seconds = backoff_seconds or settings.WEATHER_RETRY_BACKOFF_SECONDS
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            }
        )
        self._response_cache: dict[tuple[tuple[str, str], ...], _CachedResponse] = {}
        self._cache_lock = Lock()
        self._request_lock = Lock()

    async def get_current_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_current_weather_sync, latitude, longitude)

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_forecast_sync, latitude, longitude, days)

    def _get_current_weather_sync(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        forecast = self._get_forecast_sync(latitude, longitude, days=1)
        if not forecast:
            raise RuntimeError("MET Norway returned no current forecast period")

        first = forecast[0]
        return {
            "timestamp": first["forecast_timestamp"],
            "temperature_c": first["temperature_c"],
            "humidity_percent": first["humidity_percent"],
            "rainfall_mm_hr": first["rainfall_mm_hr"],
            "cloud_cover_percent": first["cloud_cover_percent"],
            "wind_speed_kmh": first["wind_speed_kmh"],
            "wind_direction_deg": first.get("wind_direction_deg"),
            "pressure_hpa": first.get("pressure_hpa"),
            "weather_condition": first["weather_condition"],
            "provider_name": "MET Norway",
        }

    def _get_forecast_sync(
        self,
        latitude: float,
        longitude: float,
        days: int,
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            params={
                "lat": round(latitude, 4),
                "lon": round(longitude, 4),
                # Piarco and the main Trinidad load corridor are near sea level.
                "altitude": settings.WEATHER_SITE_ALTITUDE_METERS,
            }
        )
        timeseries = payload.get("properties", {}).get("timeseries", [])
        maximum_periods = max(1, min(days, 9)) * 24

        forecast: list[dict[str, Any]] = []
        for period in timeseries[:maximum_periods]:
            data = period.get("data") or {}
            instant = (data.get("instant") or {}).get("details") or {}
            next_hour = data.get("next_1_hours") or {}
            next_hour_details = next_hour.get("details") or {}
            next_hour_summary = next_hour.get("summary") or {}
            symbol_code = str(next_hour_summary.get("symbol_code") or "unknown")

            temperature = instant.get("air_temperature")
            humidity = instant.get("relative_humidity")
            if temperature is None or humidity is None:
                continue

            forecast.append(
                {
                    "forecast_timestamp": period.get("time"),
                    "temperature_c": temperature,
                    "humidity_percent": humidity,
                    "rainfall_mm_hr": next_hour_details.get("precipitation_amount", 0.0),
                    "cloud_cover_percent": instant.get("cloud_area_fraction", 0.0),
                    "wind_speed_kmh": self._meters_per_second_to_kmh(
                        instant.get("wind_speed", 0.0)
                    ),
                    "wind_direction_deg": instant.get("wind_from_direction"),
                    "pressure_hpa": instant.get("air_pressure_at_sea_level"),
                    "weather_condition": self._describe_symbol(symbol_code),
                    "provider_name": "MET Norway",
                }
            )

        if not forecast:
            raise RuntimeError("MET Norway returned incomplete forecast data")

        logger.debug("MET Norway forecast payload received: %s points", len(forecast))
        return forecast

    def _request_json(self, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        cache_key = tuple(sorted((key, str(value)) for key, value in params.items()))
        now = datetime.now(timezone.utc)

        with self._cache_lock:
            cached = self._response_cache.get(cache_key)
            if cached and cached.expires_at > now:
                return copy.deepcopy(cached.payload)

        for attempt in range(1, self.retry_attempts + 1):
            try:
                headers: dict[str, str] = {}
                if cached:
                    if cached.last_modified:
                        headers["If-Modified-Since"] = cached.last_modified
                    if cached.etag:
                        headers["If-None-Match"] = cached.etag
                with self._request_lock:
                    response = self.session.get(
                        self.base_url,
                        params=params,
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
                if response.status_code == 304 and cached:
                    cached.expires_at = self._response_expiry(response.headers)
                    return copy.deepcopy(cached.payload)
                response.raise_for_status()
                if response.status_code == 203:
                    logger.warning("MET Norway forecast API version is deprecated")
                payload = response.json()
                entry = _CachedResponse(
                    payload=copy.deepcopy(payload),
                    expires_at=self._response_expiry(response.headers),
                    last_modified=response.headers.get("Last-Modified"),
                    etag=response.headers.get("ETag"),
                )
                with self._cache_lock:
                    self._response_cache[cache_key] = entry
                return payload
            except Exception as exc:  # pragma: no cover - defensive logging
                last_error = exc
                logger.warning(
                    "MET Norway request failed on attempt %s/%s: %s",
                    attempt,
                    self.retry_attempts,
                    exc,
                )
                if attempt < self.retry_attempts:
                    time.sleep(self.backoff_seconds)

        if cached:
            logger.warning("Serving stale MET Norway response after provider failure")
            return copy.deepcopy(cached.payload)

        raise RuntimeError("MET Norway request failed") from last_error

    @staticmethod
    def _response_expiry(headers: Any) -> datetime:
        now = datetime.now(timezone.utc)
        cache_control = str(headers.get("Cache-Control", ""))
        for directive in cache_control.split(","):
            directive = directive.strip().lower()
            if directive.startswith("max-age="):
                try:
                    return now + timedelta(seconds=max(60, int(directive.split("=", 1)[1])))
                except ValueError:
                    break

        expires = headers.get("Expires")
        if expires:
            try:
                parsed = parsedate_to_datetime(expires)
                normalized = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                return max(normalized, now + timedelta(seconds=60))
            except (TypeError, ValueError):
                pass

        return now + timedelta(seconds=settings.WEATHER_CACHE_TTL_SECONDS)

    @staticmethod
    def _meters_per_second_to_kmh(value: Any) -> float:
        try:
            return round(float(value) * 3.6, 2)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _describe_symbol(symbol_code: str) -> str:
        normalized = symbol_code.lower()
        if "thunder" in normalized:
            return "Thunderstorm"
        if "heavyrain" in normalized:
            return "Heavy rain"
        if "rain" in normalized or "sleet" in normalized:
            return "Rain showers" if "showers" in normalized else "Rain"
        if "fog" in normalized:
            return "Fog"
        if "partlycloudy" in normalized:
            return "Partly cloudy"
        if "cloudy" in normalized:
            return "Cloudy"
        if "fair" in normalized:
            return "Mainly clear"
        if "clearsky" in normalized:
            return "Clear sky"
        return "Unknown"
