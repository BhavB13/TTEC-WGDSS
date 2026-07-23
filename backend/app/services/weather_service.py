from __future__ import annotations

import asyncio
import copy
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.providers.met_norway_provider import MetNorwayProvider
from app.providers.open_meteo_provider import OpenMeteoProvider
from app.providers.weather_provider import WeatherProvider
from app.providers.weatherapi_provider import WeatherAPIProvider
from app.services.provider_health import record_provider_failure, record_provider_success
from app.services.temperature_aggregation_service import TemperatureAggregationService

logger = logging.getLogger(__name__)
TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class WeatherService:
    def __init__(
        self,
        provider: WeatherProvider | None = None,
        fallback_provider: WeatherProvider | None = None,
        consensus_providers: list[WeatherProvider] | None = None,
        cache_ttl_seconds: int | None = None,
        temperature_aggregation_service: (
            TemperatureAggregationService | None
        ) = None,
        enable_temperature_aggregation: bool | None = None,
    ) -> None:
        use_default_ensemble = provider is None and fallback_provider is None
        self.primary_provider = provider or OpenMeteoProvider()
        self.fallback_provider = fallback_provider or self._default_fallback_provider()
        self.consensus_providers = (
            consensus_providers
            if consensus_providers is not None
            else (
                [MetNorwayProvider(), OpenMeteoProvider(model="gfs_global")]
                if use_default_ensemble
                else []
            )
        )
        self.cache_ttl_seconds = cache_ttl_seconds or settings.WEATHER_CACHE_TTL_SECONDS
        aggregation_enabled = (
            settings.TEMPERATURE_AGGREGATION_ENABLED
            if enable_temperature_aggregation is None
            else enable_temperature_aggregation
        )
        if temperature_aggregation_service is not None:
            self.temperature_aggregation_service = temperature_aggregation_service
        elif (
            aggregation_enabled
            and use_default_ensemble
            and isinstance(self.primary_provider, OpenMeteoProvider)
        ):
            self.temperature_aggregation_service = TemperatureAggregationService(
                provider=self.primary_provider
            )
        else:
            self.temperature_aggregation_service = None
        self._cache: dict[str, _CacheEntry] = {}
        self._cache_lock = asyncio.Lock()
        self.last_current_fallback_used = False
        self.last_forecast_fallback_used = False
        self.last_forecast_consensus_degraded = False
        self.last_forecast_source_count = 0
        self.last_forecast_provider_names: list[str] = []

    @staticmethod
    def _default_fallback_provider() -> WeatherProvider:
        if settings.ENABLE_WEATHERAPI_FALLBACK and settings.WEATHER_API_KEY:
            return WeatherAPIProvider()
        return OpenMeteoProvider(model="gfs_global")

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
        normalized = await self._apply_current_temperature_aggregate(normalized)
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

        if self.consensus_providers:
            source_payloads = await self._fetch_forecast_consensus(
                latitude,
                longitude,
                days,
            )
            normalized_sources = [
                [self._normalize_forecast_item(item) for item in payload]
                for payload in source_payloads
            ]
            normalized = self.reconcile_forecast_sources(
                normalized_sources,
                expected_source_count=1 + len(self.consensus_providers),
            )
            self.last_forecast_consensus_degraded = (
                self.last_forecast_consensus_degraded
                or not normalized
                or any(
                    item.get("source_sync_status") != "COMPLETE"
                    for item in normalized[:6]
                )
            )
        else:
            raw = await self._fetch_forecast_with_failover(latitude, longitude, days)
            normalized = [self._normalize_forecast_item(item) for item in raw]
            self.last_forecast_source_count = 1
            self.last_forecast_provider_names = sorted(
                {
                    str(item.get("provider_name", "Unknown"))
                    for item in normalized
                }
            )
            self.last_forecast_consensus_degraded = False
        normalized.sort(key=self._forecast_sort_key)
        normalized = await self._apply_forecast_temperature_aggregates(
            normalized,
            forecast_hours=max(1, min(days, 16)) * 24,
        )
        await self._set_cache(cache_key, normalized)
        return copy.deepcopy(normalized)

    async def _apply_current_temperature_aggregate(
        self,
        weather: dict[str, Any],
    ) -> dict[str, Any]:
        if self.temperature_aggregation_service is None:
            return weather
        try:
            aggregate = (
                await self.temperature_aggregation_service.get_current_aggregate()
            )
        except Exception as exc:  # pragma: no cover - provider resilience
            logger.warning(
                "Trinidad and Tobago weather aggregation unavailable; retaining "
                "representative-site weather: %s",
                exc,
            )
            return weather

        updated = self._apply_weighted_weather_fields(weather, aggregate)
        temperature = float(updated["temperature_c"])
        updated["heat_index_c"] = self._calculate_heat_index(
            temperature,
            float(updated["humidity_percent"]),
        )
        updated["temperature_aggregation"] = aggregate
        updated["weather_aggregation"] = aggregate
        return updated

    async def _apply_forecast_temperature_aggregates(
        self,
        forecast: list[dict[str, Any]],
        *,
        forecast_hours: int,
    ) -> list[dict[str, Any]]:
        if self.temperature_aggregation_service is None or not forecast:
            return forecast
        try:
            aggregates = (
                await self.temperature_aggregation_service.get_forecast_aggregates(
                    forecast_hours
                )
            )
        except Exception as exc:  # pragma: no cover - provider resilience
            logger.warning(
                "Trinidad and Tobago forecast weather aggregation unavailable; "
                "retaining provider-consensus weather: %s",
                exc,
            )
            return forecast

        updated_forecast: list[dict[str, Any]] = []
        for period in forecast:
            updated = copy.deepcopy(period)
            timestamp = self._parse_datetime(period.get("forecast_timestamp"))
            aggregate = None
            if timestamp is not None:
                aggregate = aggregates.get(
                    timestamp.astimezone(timezone.utc).replace(
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                )
            if aggregate is not None:
                updated = self._apply_weighted_weather_fields(
                    updated,
                    aggregate,
                )
                temperature = float(updated["temperature_c"])
                updated["heat_index_c"] = self._calculate_heat_index(
                    temperature,
                    float(updated["humidity_percent"]),
                )
                updated["temperature_aggregation"] = aggregate
                updated["weather_aggregation"] = aggregate
            updated_forecast.append(updated)
        return updated_forecast

    @classmethod
    def _apply_weighted_weather_fields(
        cls,
        weather: dict[str, Any],
        aggregate: dict[str, Any],
    ) -> dict[str, Any]:
        updated = copy.deepcopy(weather)
        field_map = {
            "temperature_c": "weighted_average_c",
            "humidity_percent": "weighted_humidity_percent",
            "rainfall_mm_hr": "weighted_rainfall_mm_hr",
            "cloud_cover_percent": "weighted_cloud_cover_percent",
            "wind_speed_kmh": "weighted_wind_speed_kmh",
            "wind_direction_deg": "weighted_wind_direction_deg",
            "pressure_hpa": "weighted_pressure_hpa",
            "precipitation_probability_percent": (
                "weighted_precipitation_probability_percent"
            ),
        }
        for weather_field, aggregate_field in field_map.items():
            value = aggregate.get(aggregate_field)
            if value is not None:
                updated[weather_field] = value

        rainfall = max(0.0, float(updated.get("rainfall_mm_hr", 0.0)))
        cloud_cover = cls._clamp(
            float(updated.get("cloud_cover_percent", 0.0)),
            0.0,
            100.0,
        )
        updated["rainfall_mm_hr"] = round(rainfall, 2)
        updated["cloud_cover_percent"] = round(cloud_cover, 1)
        updated["humidity_percent"] = round(
            cls._clamp(float(updated["humidity_percent"]), 0.0, 100.0),
            1,
        )
        updated["wind_speed_kmh"] = round(
            max(0.0, float(updated["wind_speed_kmh"])),
            1,
        )
        if updated.get("wind_direction_deg") is not None:
            updated["wind_direction_deg"] = round(
                float(updated["wind_direction_deg"]) % 360.0,
                1,
            )
        if updated.get("precipitation_probability_percent") is not None:
            updated["precipitation_probability_percent"] = round(
                cls._clamp(
                    float(updated["precipitation_probability_percent"]),
                    0.0,
                    100.0,
                ),
                1,
            )
        updated["weather_condition"] = cls._consensus_condition(
            [updated],
            rainfall,
            cloud_cover,
        )
        updated["rain_severity"] = cls._rain_severity(rainfall)
        return updated

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

        for index, provider in enumerate(providers):
            role = "weather_primary" if index == 0 else "weather_fallback"
            try:
                payload = await asyncio.wait_for(
                    provider.get_current_weather(latitude, longitude),
                    timeout=settings.WEATHER_CONSENSUS_TIMEOUT_SECONDS,
                )
                self.last_current_fallback_used = index > 0
                record_provider_success(role, provider.__class__.__name__)
                logger.info("Weather fetched from %s", provider.__class__.__name__)
                return payload
            except Exception as exc:  # pragma: no cover - defensive logging
                record_provider_failure(role, provider.__class__.__name__, exc)
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

        for index, provider in enumerate(providers):
            role = "weather_primary" if index == 0 else "weather_fallback"
            try:
                payload = await asyncio.wait_for(
                    provider.get_forecast(latitude, longitude, days),
                    timeout=settings.WEATHER_CONSENSUS_TIMEOUT_SECONDS,
                )
                self.last_forecast_fallback_used = index > 0
                record_provider_success(role, provider.__class__.__name__)
                logger.info("Forecast fetched from %s", provider.__class__.__name__)
                return payload
            except Exception as exc:  # pragma: no cover - defensive logging
                record_provider_failure(role, provider.__class__.__name__, exc)
                last_error = exc
                logger.warning(
                    "Forecast provider %s failed: %s",
                    provider.__class__.__name__,
                    exc,
                )

        raise RuntimeError("All weather providers failed") from last_error

    async def _fetch_forecast_consensus(
        self,
        latitude: float,
        longitude: float,
        days: int,
    ) -> list[list[dict[str, Any]]]:
        providers = [self.primary_provider, *self.consensus_providers]

        async def fetch(
            index: int,
            provider: WeatherProvider,
        ) -> tuple[int, WeatherProvider, list[dict[str, Any]] | Exception]:
            try:
                payload = await asyncio.wait_for(
                    provider.get_forecast(latitude, longitude, days),
                    timeout=settings.WEATHER_CONSENSUS_TIMEOUT_SECONDS,
                )
                if not payload:
                    raise RuntimeError("provider returned an empty forecast")
                return index, provider, payload
            except Exception as exc:  # pragma: no cover - defensive logging
                return index, provider, exc

        results = await asyncio.gather(
            *(fetch(index, provider) for index, provider in enumerate(providers))
        )

        successful: list[list[dict[str, Any]]] = []
        provider_names: list[str] = []
        primary_succeeded = False
        for index, provider, result in results:
            role = "weather_primary" if index == 0 else (
                "weather_consensus" if index == 1 else f"weather_consensus_{index}"
            )
            provider_name = self._provider_identity(provider)
            if isinstance(result, Exception):
                record_provider_failure(role, provider_name, result)
                logger.warning("Forecast provider %s failed: %s", provider_name, result)
                continue

            record_provider_success(role, provider_name)
            successful.append(result)
            provider_names.append(provider_name)
            primary_succeeded = primary_succeeded or index == 0

        if not successful:
            logger.warning("All consensus providers failed; attempting forecast fallback")
            fallback_payload = await asyncio.wait_for(
                self.fallback_provider.get_forecast(latitude, longitude, days),
                timeout=settings.WEATHER_CONSENSUS_TIMEOUT_SECONDS,
            )
            successful = [fallback_payload]
            provider_names = [self.fallback_provider.__class__.__name__]
            self.last_forecast_fallback_used = True
        else:
            self.last_forecast_fallback_used = not primary_succeeded

        self.last_forecast_source_count = len(successful)
        self.last_forecast_provider_names = provider_names
        self.last_forecast_consensus_degraded = len(successful) < len(providers)
        logger.info(
            "Forecast assembled from %s source(s): %s",
            len(successful),
            ", ".join(provider_names),
        )
        return successful

    @classmethod
    def reconcile_forecast_sources(
        cls,
        sources: list[list[dict[str, Any]]],
        expected_source_count: int | None = None,
    ) -> list[dict[str, Any]]:
        """Merge provider forecasts by UTC hour without inventing missing values."""
        expected_sources = expected_source_count or len(sources)
        periods: dict[datetime, dict[str, dict[str, Any]]] = {}
        for source_index, source in enumerate(sources):
            for item in source:
                timestamp = cls._parse_datetime(item.get("forecast_timestamp"))
                if timestamp is None:
                    continue
                utc_timestamp = timestamp.astimezone(timezone.utc)
                utc_hour = (utc_timestamp + timedelta(minutes=30)).replace(
                    minute=0, second=0, microsecond=0
                )
                if abs((utc_timestamp - utc_hour).total_seconds()) > 30 * 60:
                    continue
                provider_name = str(
                    item.get("provider_name") or f"source-{source_index + 1}"
                )
                existing = periods.setdefault(utc_hour, {}).get(provider_name)
                if existing is None or abs(
                    (utc_timestamp - utc_hour).total_seconds()
                ) < abs(
                    (
                        cls._parse_datetime(existing.get("forecast_timestamp"))
                        .astimezone(timezone.utc)
                        - utc_hour
                    ).total_seconds()
                ):
                    periods[utc_hour][provider_name] = item

        reconciled: list[dict[str, Any]] = []
        operational_fields = (
            "temperature_c",
            "humidity_percent",
            "rainfall_mm_hr",
            "cloud_cover_percent",
            "wind_speed_kmh",
        )
        for timestamp, provider_items in sorted(periods.items()):
            items = list(provider_items.values())
            provider_names = list(provider_items)
            field_values = {
                field: cls._values(items, field) for field in operational_fields
            }
            missing_fields = [
                field for field, values in field_values.items() if not values
            ]
            if missing_fields:
                logger.warning(
                    "Skipping forecast hour %s; no valid source supplied %s",
                    timestamp.isoformat(),
                    ", ".join(missing_fields),
                )
                continue

            temperature_values = field_values["temperature_c"]
            rainfall_values = field_values["rainfall_mm_hr"]
            cloud_values = field_values["cloud_cover_percent"]
            probability_values = cls._values(
                items,
                "precipitation_probability_percent",
            )

            temperature = cls._weighted_mean(items, "temperature_c")
            temperature_aggregation = cls._reconcile_temperature_aggregation(
                items
            )
            if temperature_aggregation is not None:
                temperature = float(
                    temperature_aggregation["weighted_average_c"]
                )
            humidity = cls._clamp(
                cls._weighted_mean(items, "humidity_percent"),
                0.0,
                100.0,
            )
            rainfall = max(0.0, cls._weighted_mean(items, "rainfall_mm_hr"))
            cloud_cover = cls._clamp(
                cls._weighted_mean(items, "cloud_cover_percent"),
                0.0,
                100.0,
            )
            wind_speed = max(0.0, cls._weighted_mean(items, "wind_speed_kmh"))
            pressure_values = cls._values(items, "pressure_hpa")
            pressure = (
                cls._weighted_mean(items, "pressure_hpa")
                if pressure_values
                else None
            )
            precipitation_probability = (
                max(probability_values)
                if probability_values
                else cls._rain_probability(rainfall)
            )
            condition = cls._consensus_condition(items, rainfall, cloud_cover)
            confidence = cls._consensus_confidence(
                len(items),
                cls._spread(temperature_values),
                cls._spread(cloud_values),
                cls._spread(rainfall_values),
            )
            field_source_counts = {
                field: len(values) for field, values in field_values.items()
            }

            reconciled_item = {
                "forecast_timestamp": timestamp.astimezone(
                    TRINIDAD_TZ
                ).isoformat(),
                "temperature_c": round(temperature, 1),
                "humidity_percent": round(humidity, 1),
                "rainfall_mm_hr": round(rainfall, 2),
                "cloud_cover_percent": round(cloud_cover, 1),
                "wind_speed_kmh": round(wind_speed, 1),
                "pressure_hpa": (
                    round(pressure, 1) if pressure is not None else None
                ),
                "weather_condition": condition,
                "heat_index_c": cls._calculate_heat_index(
                    temperature,
                    humidity,
                ),
                "precipitation_probability_percent": round(
                    cls._clamp(precipitation_probability, 0.0, 100.0),
                    1,
                ),
                "confidence_score": confidence,
                "rain_severity": cls._rain_severity(rainfall),
                "provider_name": (
                    f"Consensus ({' + '.join(provider_names)})"
                    if len(provider_names) > 1
                    else provider_names[0]
                ),
                "source_count": len(provider_names),
                "source_names": provider_names,
                "source_sync_status": (
                    "COMPLETE"
                    if len(provider_names) == expected_sources
                    else "DEGRADED"
                ),
                "field_source_counts": field_source_counts,
                "temperature_spread_c": round(
                    cls._spread(temperature_values),
                    2,
                ),
                "cloud_cover_spread_percent": round(
                    cls._spread(cloud_values),
                    1,
                ),
            }
            if temperature_aggregation is not None:
                reconciled_item["temperature_aggregation"] = (
                    temperature_aggregation
                )
            reconciled.append(reconciled_item)
        return reconciled

    # Backward-compatible alias retained for existing internal callers/tests.
    def _reconcile_forecasts(
        self,
        sources: list[list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        return self.reconcile_forecast_sources(sources)

    @staticmethod
    def _values(items: list[dict[str, Any]], key: str) -> list[float]:
        values: list[float] = []
        for item in items:
            try:
                value = item.get(key)
                if value is not None:
                    values.append(float(value))
            except (TypeError, ValueError):
                continue
        return values

    @classmethod
    def _weighted_mean(cls, items: list[dict[str, Any]], key: str) -> float:
        weighted_total = 0.0
        total_weight = 0.0
        for item in items:
            value = item.get(key)
            if value is None:
                continue
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                continue
            weight = cls._provider_weight(str(item.get("provider_name", "")))
            weighted_total += numeric_value * weight
            total_weight += weight
        return weighted_total / total_weight if total_weight else 0.0

    @classmethod
    def _reconcile_temperature_aggregation(
        cls,
        items: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        aggregate_items = [
            (item, item.get("temperature_aggregation"))
            for item in items
            if isinstance(item.get("temperature_aggregation"), dict)
        ]
        if not aggregate_items:
            return None

        templates: dict[str, dict[str, Any]] = {}
        point_values: dict[str, list[tuple[float, float]]] = {}
        for item, aggregate in aggregate_items:
            provider_weight = cls._provider_weight(
                str(item.get("provider_name", ""))
            )
            for sample in aggregate.get("samples", []):
                if not isinstance(sample, dict) or not sample.get("id"):
                    continue
                try:
                    temperature = float(sample["temperature_c"])
                except (KeyError, TypeError, ValueError):
                    continue
                point_id = str(sample["id"])
                templates.setdefault(point_id, sample)
                point_values.setdefault(point_id, []).append(
                    (temperature, provider_weight)
                )

        if not point_values:
            first = copy.deepcopy(aggregate_items[0][1])
            first["weighted_average_c"] = round(
                cls._weighted_mean(items, "temperature_c"),
                2,
            )
            return first

        samples: list[dict[str, Any]] = []
        covered_weight = 0.0
        weighted_total = 0.0
        for point_id, values in point_values.items():
            template = copy.deepcopy(templates[point_id])
            source_weight = sum(weight for _, weight in values)
            temperature = (
                sum(value * weight for value, weight in values) / source_weight
                if source_weight
                else sum(value for value, _ in values) / len(values)
            )
            demand_weight = float(template.get("demand_weight", 0.0) or 0.0)
            template["temperature_c"] = round(temperature, 2)
            template["provider_name"] = "Archived model consensus"
            samples.append(template)
            covered_weight += demand_weight
            weighted_total += temperature * demand_weight

        if not samples or covered_weight <= 0:
            return None
        for sample in samples:
            sample["effective_weight_percent"] = round(
                float(sample.get("demand_weight", 0.0)) / covered_weight * 100.0,
                2,
            )
        temperatures = [float(sample["temperature_c"]) for sample in samples]
        first_aggregate = aggregate_items[0][1]
        expected_count = max(
            int(aggregate.get("expected_sample_count", len(samples)) or len(samples))
            for _, aggregate in aggregate_items
        )
        provider_names = [
            str(item.get("provider_name", "Unknown"))
            for item, _ in aggregate_items
        ]
        return {
            "label": first_aggregate.get(
                "label",
                "Trinidad and Tobago weighted weather",
            ),
            "method": first_aggregate.get(
                "method",
                "demand_exposure_weighted_mean",
            ),
            "policy_version": first_aggregate.get(
                "policy_version",
                "PROTOTYPE_DEMAND_EXPOSURE_V1",
            ),
            "policy_status": first_aggregate.get(
                "policy_status",
                settings.TEMPERATURE_AGGREGATION_POLICY_STATUS,
            ),
            "status": (
                "COMPLETE"
                if len(samples) == expected_count
                else "DEGRADED"
            ),
            "source_name": f"Consensus ({' + '.join(provider_names)})",
            "weighted_average_c": round(weighted_total / covered_weight, 2),
            "minimum_c": round(min(temperatures), 2),
            "maximum_c": round(max(temperatures), 2),
            "spread_c": round(max(temperatures) - min(temperatures), 2),
            "sample_count": len(samples),
            "expected_sample_count": expected_count,
            "weight_coverage_percent": min(
                float(
                    aggregate.get("weight_coverage_percent", 100.0)
                    or 0.0
                )
                for _, aggregate in aggregate_items
            ),
            "samples": samples,
        }

    @staticmethod
    def _provider_weight(provider_name: str) -> float:
        normalized = provider_name.lower()
        if "best match" in normalized:
            return 0.5
        if "gfs" in normalized:
            return 0.2
        if "met norway" in normalized:
            return 0.3
        if "open-meteo" in normalized:
            return 0.5
        if "weatherapi" in normalized:
            return 0.5
        return 0.35

    @staticmethod
    def _provider_identity(provider: WeatherProvider) -> str:
        configured_name = getattr(provider, "provider_name", None)
        if isinstance(configured_name, str) and configured_name:
            return configured_name
        if isinstance(provider, MetNorwayProvider):
            return "MET Norway"
        return provider.__class__.__name__

    @staticmethod
    def _spread(values: list[float]) -> float:
        return max(values) - min(values) if len(values) > 1 else 0.0

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    @classmethod
    def _consensus_confidence(
        cls,
        source_count: int,
        temperature_spread: float,
        cloud_spread: float,
        rainfall_spread: float,
    ) -> float:
        if source_count < 2:
            return 0.68
        base_confidence = 0.97 if source_count >= 3 else 0.91
        disagreement_penalty = (
            min(temperature_spread / 8.0, 1.0) * 0.16
            + min(cloud_spread / 100.0, 1.0) * 0.12
            + min(rainfall_spread / 10.0, 1.0) * 0.10
        )
        return round(cls._clamp(base_confidence - disagreement_penalty, 0.58, 0.97), 2)

    @staticmethod
    def _consensus_condition(
        items: list[dict[str, Any]],
        rainfall: float,
        cloud_cover: float,
    ) -> str:
        conditions = [str(item.get("weather_condition", "")).lower() for item in items]
        if any("thunder" in condition for condition in conditions):
            return "Thunderstorm"
        if rainfall >= 7:
            return "Heavy rain"
        if rainfall >= 0.1 or any("rain" in condition for condition in conditions):
            return "Rain showers"
        if cloud_cover >= 85:
            return "Overcast"
        if cloud_cover >= 45:
            return "Partly cloudy"
        return "Mainly clear"

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

        normalized = {
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
        if isinstance(data.get("temperature_aggregation"), dict):
            normalized["temperature_aggregation"] = copy.deepcopy(
                data["temperature_aggregation"]
            )
        return normalized

    def _normalize_forecast_item(self, data: dict[str, Any]) -> dict[str, Any]:
        temperature_c = self._optional_number(
            data,
            ["temperature_c", "temperature_2m", "temp_c"],
        )
        humidity_percent = self._optional_number(
            data,
            ["humidity_percent", "relative_humidity_2m", "humidity"],
        )
        rainfall_mm_hr = self._optional_number(
            data,
            ["rainfall_mm_hr", "precipitation", "precip_mm", "rain"],
        )
        cloud_cover_percent = self._optional_number(
            data,
            ["cloud_cover_percent", "cloud_cover", "cloud"],
        )
        wind_speed_kmh = self._optional_number(
            data,
            ["wind_speed_kmh", "wind_speed_10m", "wind_kph"],
        )
        weather_condition = str(
            data.get("weather_condition")
            or (data.get("condition") or {}).get("text")
            or self._describe_weather_code(data.get("weather_code"))
            or "Unknown"
        )
        heat_index_c = self._optional_number(
            data,
            ["heat_index_c", "heatindex_c", "apparent_temperature"],
        )
        if heat_index_c is None and temperature_c is not None and humidity_percent is not None:
            heat_index_c = self._calculate_heat_index(temperature_c, humidity_percent)
        precipitation_probability = self._optional_number(
            data,
            ["precipitation_probability_percent", "chance_of_rain", "precipitation_probability"],
        )
        if precipitation_probability is None and rainfall_mm_hr is not None:
            precipitation_probability = self._rain_probability(rainfall_mm_hr)
        timestamp = self._normalize_timestamp(
            data.get("forecast_timestamp") or data.get("time") or data.get("time_epoch")
        )

        confidence_score = self._estimate_confidence(data.get("provider_name", "Unknown"))

        normalized = {
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
            "rain_severity": (
                self._rain_severity(rainfall_mm_hr)
                if rainfall_mm_hr is not None
                else "UNKNOWN"
            ),
            "provider_name": data.get("provider_name", "Unknown"),
        }
        if isinstance(data.get("temperature_aggregation"), dict):
            normalized["temperature_aggregation"] = copy.deepcopy(
                data["temperature_aggregation"]
            )
        return normalized

    @staticmethod
    def _optional_number(data: dict[str, Any], keys: list[str]) -> float | None:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            try:
                converted = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(converted):
                return converted
        return None

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
            return value if value.tzinfo else value.replace(tzinfo=TRINIDAD_TZ)
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
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=TRINIDAD_TZ)
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
