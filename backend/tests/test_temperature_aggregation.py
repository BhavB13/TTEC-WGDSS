from __future__ import annotations

import pytest

from app.data.temperature_sampling import (
    TRINIDAD_TEMPERATURE_SAMPLING_POINTS,
    TemperatureObservation,
    build_temperature_aggregation,
    build_weather_aggregation,
)
from app.providers.weather_provider import WeatherProvider
from app.services.weather_service import WeatherService


def test_temperature_aggregation_applies_configured_demand_weights():
    observations = [
        TemperatureObservation(
            point_id=point.id,
            temperature_c=27.0 + index,
        )
        for index, point in enumerate(TRINIDAD_TEMPERATURE_SAMPLING_POINTS)
    ]

    aggregate = build_temperature_aggregation(
        observations,
        source_name="Test Provider",
        minimum_weight_coverage_percent=70.0,
        policy_status="PROTOTYPE_UNCONFIRMED",
    )

    assert aggregate is not None
    expected = sum(
        observation.temperature_c * point.demand_weight
        for observation, point in zip(
            observations,
            TRINIDAD_TEMPERATURE_SAMPLING_POINTS,
            strict=True,
        )
    ) / sum(point.demand_weight for point in TRINIDAD_TEMPERATURE_SAMPLING_POINTS)
    assert aggregate["weighted_average_c"] == pytest.approx(expected, abs=0.01)
    assert aggregate["sample_count"] == 11
    assert aggregate["weight_coverage_percent"] == 100.0
    assert aggregate["samples"][1]["name"] == "Port of Spain"
    assert (
        aggregate["samples"][1]["effective_weight_percent"]
        > aggregate["samples"][-1]["effective_weight_percent"]
    )


def test_temperature_aggregation_fails_closed_below_weight_coverage():
    point = TRINIDAD_TEMPERATURE_SAMPLING_POINTS[-1]

    aggregate = build_temperature_aggregation(
        [TemperatureObservation(point_id=point.id, temperature_c=31.0)],
        source_name="Test Provider",
        minimum_weight_coverage_percent=70.0,
        policy_status="PROTOTYPE_UNCONFIRMED",
    )

    assert aggregate is None


def test_weather_aggregation_uses_same_points_and_weights_for_all_fields():
    observations = [
        TemperatureObservation(
            point_id=point.id,
            temperature_c=27.0 + index,
            humidity_percent=60.0 + index,
            rainfall_mm_hr=float(index),
            cloud_cover_percent=20.0 + index * 5.0,
            wind_speed_kmh=10.0 + index,
            wind_direction_deg=350.0 if index % 2 == 0 else 10.0,
            pressure_hpa=1008.0 + index,
            precipitation_probability_percent=5.0 + index * 3.0,
        )
        for index, point in enumerate(TRINIDAD_TEMPERATURE_SAMPLING_POINTS)
    ]

    aggregate = build_weather_aggregation(
        observations,
        source_name="Test Provider",
        minimum_weight_coverage_percent=70.0,
        policy_status="PROTOTYPE_UNCONFIRMED",
    )

    assert aggregate is not None
    total_weight = sum(
        point.demand_weight for point in TRINIDAD_TEMPERATURE_SAMPLING_POINTS
    )
    expected_humidity = sum(
        observation.humidity_percent * point.demand_weight
        for observation, point in zip(
            observations,
            TRINIDAD_TEMPERATURE_SAMPLING_POINTS,
            strict=True,
        )
    ) / total_weight
    assert aggregate["weighted_humidity_percent"] == pytest.approx(
        expected_humidity,
        abs=0.1,
    )
    assert aggregate["weighted_rainfall_mm_hr"] is not None
    assert aggregate["weighted_cloud_cover_percent"] is not None
    assert aggregate["weighted_wind_speed_kmh"] is not None
    assert (
        aggregate["field_weight_coverage_percent"]["humidity_percent"]
        == 100.0
    )
    direction = aggregate["weighted_wind_direction_deg"]
    assert direction >= 340.0 or direction <= 20.0
    assert aggregate["samples"][0]["humidity_percent"] == 60.0


class _WeatherProvider(WeatherProvider):
    async def get_current_weather(self, latitude: float, longitude: float):
        return {
            "timestamp": "2026-07-23T09:00:00-04:00",
            "temperature_c": 27.0,
            "humidity_percent": 80.0,
            "rainfall_mm_hr": 0.0,
            "cloud_cover_percent": 40.0,
            "wind_speed_kmh": 12.0,
            "weather_condition": "Partly cloudy",
            "heat_index_c": 29.0,
            "provider_name": "Representative Site",
        }

    async def get_forecast(self, latitude: float, longitude: float, days: int = 7):
        return [
            {
                "forecast_timestamp": "2026-07-23T10:00:00-04:00",
                "temperature_c": 28.0,
                "humidity_percent": 78.0,
                "rainfall_mm_hr": 0.0,
                "cloud_cover_percent": 35.0,
                "wind_speed_kmh": 13.0,
                "weather_condition": "Partly cloudy",
                "heat_index_c": 30.0,
                "precipitation_probability_percent": 10.0,
                "provider_name": "Representative Site",
            }
        ]


class _TemperatureAggregationService:
    async def get_current_aggregate(self):
        return _aggregate_payload(30.5)

    async def get_forecast_aggregates(self, forecast_hours: int):
        from datetime import datetime, timezone

        return {
            datetime(2026, 7, 23, 14, tzinfo=timezone.utc): _aggregate_payload(
                31.2
            )
        }


def _aggregate_payload(temperature_c: float):
    return {
        "label": "Trinidad and Tobago weighted weather",
        "method": "demand_exposure_weighted_mean",
        "policy_version": "PROTOTYPE_DEMAND_EXPOSURE_V1",
        "policy_status": "PROTOTYPE_UNCONFIRMED",
        "status": "COMPLETE",
        "source_name": "Test Provider",
        "weighted_average_c": temperature_c,
        "weighted_humidity_percent": 72.0,
        "weighted_rainfall_mm_hr": 1.25,
        "weighted_cloud_cover_percent": 64.0,
        "weighted_wind_speed_kmh": 18.0,
        "weighted_wind_direction_deg": 82.0,
        "weighted_pressure_hpa": 1011.0,
        "weighted_precipitation_probability_percent": 55.0,
        "minimum_c": temperature_c - 1.0,
        "maximum_c": temperature_c + 1.0,
        "spread_c": 2.0,
        "sample_count": 11,
        "expected_sample_count": 11,
        "weight_coverage_percent": 100.0,
        "samples": [],
    }


@pytest.mark.asyncio
async def test_weather_service_uses_aggregate_for_current_and_forecast_temperature():
    service = WeatherService(
        provider=_WeatherProvider(),
        fallback_provider=_WeatherProvider(),
        consensus_providers=[],
        temperature_aggregation_service=_TemperatureAggregationService(),
    )

    current = await service.get_current_weather(10.5953, -61.3372)
    forecast = await service.get_forecast(10.5953, -61.3372, days=1)

    assert current["temperature_c"] == 30.5
    assert current["humidity_percent"] == 72.0
    assert current["rainfall_mm_hr"] == 1.25
    assert current["cloud_cover_percent"] == 64.0
    assert current["wind_speed_kmh"] == 18.0
    assert current["wind_direction_deg"] == 82.0
    assert current["temperature_aggregation"]["sample_count"] == 11
    assert current["weather_aggregation"]["sample_count"] == 11
    assert forecast[0]["temperature_c"] == 31.2
    assert forecast[0]["humidity_percent"] == 72.0
    assert forecast[0]["rainfall_mm_hr"] == 1.25
    assert forecast[0]["cloud_cover_percent"] == 64.0
    assert forecast[0]["wind_speed_kmh"] == 18.0
    assert forecast[0]["precipitation_probability_percent"] == 55.0
    assert forecast[0]["temperature_aggregation"]["weighted_average_c"] == 31.2
