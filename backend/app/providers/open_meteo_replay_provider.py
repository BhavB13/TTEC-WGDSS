from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.data.temperature_sampling import (
    TRINIDAD_TEMPERATURE_SAMPLING_POINTS,
    TemperatureObservation,
    build_weather_aggregation,
)
from app.providers.open_meteo_provider import OpenMeteoProvider


TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")
GLOBAL_RUN_CYCLE_HOURS = 6
ARCHIVED_RUN_FORECAST_HOURS = 72


@dataclass(frozen=True)
class ArchivedForecastResult:
    source_payloads: list[list[dict[str, Any]]]
    run_initialized_at: datetime
    assumed_available_at: datetime
    expected_source_count: int


class OpenMeteoReplayProvider(OpenMeteoProvider):
    """Retrieve model runs that were available at a historical SCADA cursor."""

    MODEL_NAMES = {
        "ecmwf_ifs025": "Open-Meteo ECMWF IFS",
        "gfs_global": "Open-Meteo NOAA GFS",
        "icon_global": "Open-Meteo DWD ICON",
    }

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.OPEN_METEO_SINGLE_RUNS_URL,
            cache_ttl_seconds=settings.REPLAY_WEATHER_CACHE_TTL_SECONDS,
        )
        self.models = tuple(
            model.strip()
            for model in settings.REPLAY_WEATHER_MODELS.split(",")
            if model.strip()
        )
        if not self.models:
            raise ValueError("At least one replay weather model must be configured")

    def get_forecast_sources(
        self,
        latitude: float,
        longitude: float,
        source_cursor: datetime,
        hours: int = 24,
    ) -> ArchivedForecastResult:
        source_local = _as_trinidad_time(source_cursor)
        run_initialized_at, assumed_available_at = self._available_run(source_local)
        aggregate_temperature = settings.TEMPERATURE_AGGREGATION_ENABLED
        coordinates = (
            [
                (point.latitude, point.longitude)
                for point in TRINIDAD_TEMPERATURE_SAMPLING_POINTS
            ]
            if aggregate_temperature
            else [(latitude, longitude)]
        )
        payload = self._request_json(
            params={
                "latitude": ",".join(
                    str(point_latitude) for point_latitude, _ in coordinates
                ),
                "longitude": ",".join(
                    str(point_longitude) for _, point_longitude in coordinates
                ),
                "cell_selection": "land",
                "run": run_initialized_at.strftime("%Y-%m-%dT%H:%M"),
                "models": ",".join(self.models),
                "hourly": ",".join(
                    (
                        "temperature_2m",
                        "relative_humidity_2m",
                        "precipitation",
                        "cloud_cover",
                        "wind_speed_10m",
                        "wind_direction_10m",
                        "surface_pressure",
                        "weather_code",
                    )
                ),
                "forecast_hours": ARCHIVED_RUN_FORECAST_HOURS,
                "timezone": "America/Port_of_Spain",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
            }
        )
        source_payloads = self._source_payloads(
            payload,
            source_local=source_local,
            hours=max(1, hours),
            run_initialized_at=run_initialized_at,
            assumed_available_at=assumed_available_at,
        )
        if not source_payloads:
            raise RuntimeError("Open-Meteo archived run returned no usable model data")
        return ArchivedForecastResult(
            source_payloads=source_payloads,
            run_initialized_at=run_initialized_at,
            assumed_available_at=assumed_available_at,
            expected_source_count=len(self.models),
        )

    @staticmethod
    def _available_run(source_local: datetime) -> tuple[datetime, datetime]:
        cutoff_utc = source_local.astimezone(timezone.utc) - timedelta(
            hours=settings.REPLAY_WEATHER_RUN_AVAILABILITY_LAG_HOURS
        )
        run_hour = (
            cutoff_utc.hour // GLOBAL_RUN_CYCLE_HOURS
        ) * GLOBAL_RUN_CYCLE_HOURS
        run_initialized_at = cutoff_utc.replace(
            hour=run_hour,
            minute=0,
            second=0,
            microsecond=0,
        )
        assumed_available_at = run_initialized_at + timedelta(
            hours=settings.REPLAY_WEATHER_RUN_AVAILABILITY_LAG_HOURS
        )
        return run_initialized_at, assumed_available_at

    def _source_payloads(
        self,
        payload: dict[str, Any] | list[dict[str, Any]],
        source_local: datetime,
        hours: int,
        run_initialized_at: datetime,
        assumed_available_at: datetime,
    ) -> list[list[dict[str, Any]]]:
        location_payloads = (
            [item for item in payload if isinstance(item, dict)]
            if isinstance(payload, list)
            else [payload]
        )
        if not location_payloads:
            return []
        base_payload = location_payloads[0]
        hourly = base_payload.get("hourly") or {}
        timestamps = hourly.get("time") or []
        location_hourly = [
            location.get("hourly") or {} for location in location_payloads
        ]
        location_time_indices = [
            {
                str(timestamp): index
                for index, timestamp in enumerate(location.get("time") or [])
            }
            for location in location_hourly
        ]
        horizon_end = source_local + timedelta(hours=hours)
        sources: list[list[dict[str, Any]]] = []
        for model in self.models:
            provider_name = self.MODEL_NAMES.get(
                model,
                f"Open-Meteo {model}",
            )
            periods: list[dict[str, Any]] = []
            for index, timestamp_value in enumerate(timestamps):
                timestamp = _parse_local_timestamp(timestamp_value)
                if timestamp is None or not (source_local < timestamp <= horizon_end):
                    continue
                temperature = self._safe_list_value(
                    hourly.get(f"temperature_2m_{model}", []), index
                )
                humidity = self._safe_list_value(
                    hourly.get(f"relative_humidity_2m_{model}", []), index
                )
                if temperature is None or humidity is None:
                    continue
                weather_aggregation = None
                if len(location_payloads) > 1:
                    observations: list[TemperatureObservation] = []
                    for point, location, indices, location_payload in zip(
                        TRINIDAD_TEMPERATURE_SAMPLING_POINTS,
                        location_hourly,
                        location_time_indices,
                        location_payloads,
                        strict=False,
                    ):
                        location_index = indices.get(str(timestamp_value))
                        if location_index is None:
                            continue
                        location_temperature = self._safe_list_value(
                            location.get(f"temperature_2m_{model}", []),
                            location_index,
                        )
                        if location_temperature is None:
                            continue
                        observations.append(
                            TemperatureObservation(
                                point_id=point.id,
                                temperature_c=location_temperature,
                                humidity_percent=self._safe_list_value(
                                    location.get(
                                        f"relative_humidity_2m_{model}",
                                        [],
                                    ),
                                    location_index,
                                ),
                                rainfall_mm_hr=self._safe_list_value(
                                    location.get(
                                        f"precipitation_{model}",
                                        [],
                                    ),
                                    location_index,
                                ),
                                cloud_cover_percent=self._safe_list_value(
                                    location.get(
                                        f"cloud_cover_{model}",
                                        [],
                                    ),
                                    location_index,
                                ),
                                wind_speed_kmh=self._safe_list_value(
                                    location.get(
                                        f"wind_speed_10m_{model}",
                                        [],
                                    ),
                                    location_index,
                                ),
                                wind_direction_deg=self._safe_list_value(
                                    location.get(
                                        f"wind_direction_10m_{model}",
                                        [],
                                    ),
                                    location_index,
                                ),
                                pressure_hpa=self._safe_list_value(
                                    location.get(
                                        f"surface_pressure_{model}",
                                        [],
                                    ),
                                    location_index,
                                ),
                                timestamp=timestamp,
                                latitude=location_payload.get("latitude"),
                                longitude=location_payload.get("longitude"),
                            )
                        )
                    weather_aggregation = build_weather_aggregation(
                        observations,
                        source_name=provider_name,
                        minimum_weight_coverage_percent=(
                            settings.TEMPERATURE_AGGREGATION_MIN_WEIGHT_COVERAGE_PERCENT
                        ),
                        policy_status=settings.TEMPERATURE_AGGREGATION_POLICY_STATUS,
                    )
                    if weather_aggregation is not None:
                        temperature = weather_aggregation["weighted_average_c"]
                rainfall = _number(
                    self._safe_list_value(
                        hourly.get(f"precipitation_{model}", []), index, 0.0
                    ),
                    0.0,
                )
                cloud = _number(
                    self._safe_list_value(
                        hourly.get(f"cloud_cover_{model}", []), index, 0.0
                    ),
                    0.0,
                )
                wind_speed = self._safe_list_value(
                    hourly.get(f"wind_speed_10m_{model}", []), index, 0.0
                )
                wind_direction = self._safe_list_value(
                    hourly.get(f"wind_direction_10m_{model}", []), index
                )
                pressure = self._safe_list_value(
                    hourly.get(f"surface_pressure_{model}", []), index
                )
                if weather_aggregation is not None:
                    humidity = _value_or_fallback(
                        weather_aggregation.get("weighted_humidity_percent"),
                        humidity,
                    )
                    rainfall = _value_or_fallback(
                        weather_aggregation.get("weighted_rainfall_mm_hr"),
                        rainfall,
                    )
                    cloud = _value_or_fallback(
                        weather_aggregation.get(
                            "weighted_cloud_cover_percent"
                        ),
                        cloud,
                    )
                    wind_speed = _value_or_fallback(
                        weather_aggregation.get("weighted_wind_speed_kmh"),
                        wind_speed,
                    )
                    wind_direction = _value_or_fallback(
                        weather_aggregation.get(
                            "weighted_wind_direction_deg"
                        ),
                        wind_direction,
                    )
                    pressure = _value_or_fallback(
                        weather_aggregation.get("weighted_pressure_hpa"),
                        pressure,
                    )
                weather_code = self._safe_list_value(
                    hourly.get(f"weather_code_{model}", []), index
                )
                periods.append(
                    {
                        "forecast_timestamp": timestamp.isoformat(),
                        "temperature_c": temperature,
                        "humidity_percent": humidity,
                        "rainfall_mm_hr": rainfall,
                        "cloud_cover_percent": cloud,
                        "wind_speed_kmh": wind_speed,
                        "wind_direction_deg": wind_direction,
                        "pressure_hpa": pressure,
                        "weather_condition": self._describe_weather_code(weather_code),
                        "precipitation_probability_percent": min(
                            100.0,
                            round(10.0 + cloud * 0.65 + rainfall * 7.0, 1),
                        ),
                        "weather_code": weather_code,
                        "provider_name": provider_name,
                        "source_run_at": run_initialized_at.isoformat(),
                        "forecast_issued_at": assumed_available_at.isoformat(),
                        **(
                            {
                                "temperature_aggregation": weather_aggregation,
                                "weather_aggregation": weather_aggregation,
                            }
                            if weather_aggregation is not None
                            else {}
                        ),
                    }
                )
            if periods:
                sources.append(periods)
        return sources


def _as_trinidad_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=TRINIDAD_TZ)
    return value.astimezone(TRINIDAD_TZ)


def _value_or_fallback(value: Any, fallback: Any) -> Any:
    return fallback if value is None else value


def _parse_local_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TRINIDAD_TZ)
    return parsed.astimezone(TRINIDAD_TZ)


def _number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
