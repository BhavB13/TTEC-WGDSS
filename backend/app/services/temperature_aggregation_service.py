from __future__ import annotations

from datetime import datetime, timezone
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


class TemperatureAggregationService:
    """Build demand-exposure weighted Trinidad and Tobago weather observations."""

    def __init__(self, provider: OpenMeteoProvider | None = None) -> None:
        self.provider = provider or OpenMeteoProvider()

    async def get_current_aggregate(self) -> dict[str, Any]:
        raw_samples = await self.provider.get_current_temperature_samples(
            [
                (point.latitude, point.longitude)
                for point in TRINIDAD_TEMPERATURE_SAMPLING_POINTS
            ]
        )
        observations = [
            TemperatureObservation(
                point_id=point.id,
                temperature_c=sample["temperature_c"],
                humidity_percent=sample.get("humidity_percent"),
                rainfall_mm_hr=sample.get("rainfall_mm_hr"),
                cloud_cover_percent=sample.get("cloud_cover_percent"),
                wind_speed_kmh=sample.get("wind_speed_kmh"),
                wind_direction_deg=sample.get("wind_direction_deg"),
                pressure_hpa=sample.get("pressure_hpa"),
                timestamp=sample.get("timestamp"),
                latitude=sample.get("latitude"),
                longitude=sample.get("longitude"),
            )
            for point, sample in zip(
                TRINIDAD_TEMPERATURE_SAMPLING_POINTS,
                raw_samples,
                strict=False,
            )
            if sample.get("temperature_c") is not None
        ]
        aggregate = self._build(
            observations,
            source_name=self.provider.provider_name,
        )
        if aggregate is None:
            raise RuntimeError(
                "Open-Meteo returned insufficient Trinidad and Tobago weather coverage"
            )
        return aggregate

    async def get_forecast_aggregates(
        self,
        forecast_hours: int,
    ) -> dict[datetime, dict[str, Any]]:
        location_forecasts = (
            await self.provider.get_temperature_forecast_samples(
                [
                    (point.latitude, point.longitude)
                    for point in TRINIDAD_TEMPERATURE_SAMPLING_POINTS
                ],
                forecast_hours=max(1, forecast_hours),
            )
        )
        observations_by_hour: dict[datetime, list[TemperatureObservation]] = {}
        for point, location in zip(
            TRINIDAD_TEMPERATURE_SAMPLING_POINTS,
            location_forecasts,
            strict=False,
        ):
            for period in location.get("periods", []):
                timestamp = _parse_hour(period.get("forecast_timestamp"))
                temperature = period.get("temperature_c")
                if timestamp is None or temperature is None:
                    continue
                observations_by_hour.setdefault(timestamp, []).append(
                    TemperatureObservation(
                        point_id=point.id,
                        temperature_c=temperature,
                        humidity_percent=period.get("humidity_percent"),
                        rainfall_mm_hr=period.get("rainfall_mm_hr"),
                        cloud_cover_percent=period.get(
                            "cloud_cover_percent"
                        ),
                        wind_speed_kmh=period.get("wind_speed_kmh"),
                        wind_direction_deg=period.get(
                            "wind_direction_deg"
                        ),
                        pressure_hpa=period.get("pressure_hpa"),
                        precipitation_probability_percent=period.get(
                            "precipitation_probability_percent"
                        ),
                        timestamp=period.get("forecast_timestamp"),
                        latitude=location.get("latitude"),
                        longitude=location.get("longitude"),
                    )
                )

        aggregates: dict[datetime, dict[str, Any]] = {}
        for timestamp, observations in observations_by_hour.items():
            aggregate = self._build(
                observations,
                source_name=self.provider.provider_name,
            )
            if aggregate is not None:
                aggregates[timestamp] = aggregate
        if not aggregates:
            raise RuntimeError(
                "Open-Meteo returned no usable Trinidad and Tobago weather forecast"
            )
        return aggregates

    @staticmethod
    def _build(
        observations: list[TemperatureObservation],
        *,
        source_name: str,
    ) -> dict[str, Any] | None:
        return build_weather_aggregation(
            observations,
            source_name=source_name,
            minimum_weight_coverage_percent=(
                settings.TEMPERATURE_AGGREGATION_MIN_WEIGHT_COVERAGE_PERCENT
            ),
            policy_status=settings.TEMPERATURE_AGGREGATION_POLICY_STATUS,
        )


def _parse_hour(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TRINIDAD_TZ)
    return parsed.astimezone(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )
