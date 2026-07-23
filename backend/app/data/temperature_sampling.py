from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable


TEMPERATURE_AGGREGATION_METHOD = "demand_exposure_weighted_mean"
TEMPERATURE_AGGREGATION_LABEL = "Trinidad and Tobago weighted temperature"
TEMPERATURE_AGGREGATION_POLICY_VERSION = "PROTOTYPE_DEMAND_EXPOSURE_V1"


@dataclass(frozen=True)
class TemperatureSamplingPoint:
    id: str
    name: str
    latitude: float
    longitude: float
    location_type: str
    notes: str
    demand_weight: float


@dataclass(frozen=True)
class TemperatureObservation:
    point_id: str
    temperature_c: float
    humidity_percent: float | None = None
    rainfall_mm_hr: float | None = None
    cloud_cover_percent: float | None = None
    wind_speed_kmh: float | None = None
    wind_direction_deg: float | None = None
    pressure_hpa: float | None = None
    precipitation_probability_percent: float | None = None
    timestamp: datetime | str | None = None
    latitude: float | None = None
    longitude: float | None = None


# Weights are prototype demand-exposure weights, not official population or
# T&TEC load-allocation factors. Every operational weather field uses these
# same locations and weights.
TRINIDAD_TEMPERATURE_SAMPLING_POINTS: tuple[TemperatureSamplingPoint, ...] = (
    TemperatureSamplingPoint(
        id="piarco_corridor",
        name="Piarco / East-West Corridor",
        latitude=10.5953,
        longitude=-61.3372,
        location_type="mixed_residential_commercial",
        notes="Eastern urban corridor and airport-area reference point.",
        demand_weight=1.10,
    ),
    TemperatureSamplingPoint(
        id="port_of_spain",
        name="Port of Spain",
        latitude=10.6668,
        longitude=-61.5189,
        location_type="dense_commercial_residential",
        notes="Dense commercial core and surrounding residential demand.",
        demand_weight=1.60,
    ),
    TemperatureSamplingPoint(
        id="chaguanas",
        name="Chaguanas",
        latitude=10.5167,
        longitude=-61.4167,
        location_type="dense_residential_commercial",
        notes="High-growth residential and commercial load center.",
        demand_weight=1.50,
    ),
    TemperatureSamplingPoint(
        id="san_fernando",
        name="San Fernando",
        latitude=10.2903,
        longitude=-61.4531,
        location_type="dense_residential_commercial",
        notes="Southern commercial center and surrounding residential demand.",
        demand_weight=1.40,
    ),
    TemperatureSamplingPoint(
        id="arima",
        name="Arima",
        latitude=10.6330,
        longitude=-61.2830,
        location_type="residential_commercial",
        notes="Eastern residential and commercial load center.",
        demand_weight=1.25,
    ),
    TemperatureSamplingPoint(
        id="diego_martin",
        name="Diego Martin",
        latitude=10.7208,
        longitude=-61.5662,
        location_type="dense_residential",
        notes="North-west residential demand concentration.",
        demand_weight=1.20,
    ),
    TemperatureSamplingPoint(
        id="penal_debe",
        name="Penal / Debe",
        latitude=10.1667,
        longitude=-61.4667,
        location_type="residential_mixed",
        notes="South Trinidad residential and mixed-use reference point.",
        demand_weight=0.90,
    ),
    TemperatureSamplingPoint(
        id="sangre_grande",
        name="Sangre Grande",
        latitude=10.5862,
        longitude=-61.1322,
        location_type="residential_regional",
        notes="North-east regional residential reference point.",
        demand_weight=0.80,
    ),
    TemperatureSamplingPoint(
        id="mayaro",
        name="Mayaro",
        latitude=10.3050,
        longitude=-61.0000,
        location_type="lower_density_residential",
        notes="South-east coastal and lower-density residential reference.",
        demand_weight=0.30,
    ),
    TemperatureSamplingPoint(
        id="scarborough",
        name="Scarborough",
        latitude=11.1880,
        longitude=-60.7332,
        location_type="tobago_commercial_residential",
        notes="Primary Tobago commercial and residential load center.",
        demand_weight=0.50,
    ),
    TemperatureSamplingPoint(
        id="point_lisas",
        name="Point Lisas",
        latitude=10.3880,
        longitude=-61.5000,
        location_type="industrial_reference",
        notes="Industrial reference point; deliberately down-weighted.",
        demand_weight=0.50,
    ),
)


def build_temperature_aggregation(
    observations: Iterable[TemperatureObservation],
    *,
    source_name: str,
    minimum_weight_coverage_percent: float,
    policy_status: str,
) -> dict[str, Any] | None:
    points_by_id = {
        point.id: point for point in TRINIDAD_TEMPERATURE_SAMPLING_POINTS
    }
    valid_by_id: dict[str, TemperatureObservation] = {}
    for observation in observations:
        point = points_by_id.get(observation.point_id)
        if point is None or observation.point_id in valid_by_id:
            continue
        try:
            temperature = float(observation.temperature_c)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(temperature):
            continue
        valid_by_id[observation.point_id] = TemperatureObservation(
            point_id=observation.point_id,
            temperature_c=temperature,
            timestamp=observation.timestamp,
            latitude=observation.latitude,
            longitude=observation.longitude,
        )

    total_weight = sum(point.demand_weight for point in points_by_id.values())
    covered_weight = sum(
        points_by_id[point_id].demand_weight for point_id in valid_by_id
    )
    coverage_percent = (
        covered_weight / total_weight * 100.0 if total_weight > 0 else 0.0
    )
    if (
        not valid_by_id
        or coverage_percent < minimum_weight_coverage_percent
        or covered_weight <= 0
    ):
        return None

    weighted_average = sum(
        observation.temperature_c
        * points_by_id[point_id].demand_weight
        for point_id, observation in valid_by_id.items()
    ) / covered_weight
    temperatures = [
        observation.temperature_c for observation in valid_by_id.values()
    ]
    samples: list[dict[str, Any]] = []
    for point in TRINIDAD_TEMPERATURE_SAMPLING_POINTS:
        observation = valid_by_id.get(point.id)
        if observation is None:
            continue
        timestamp = observation.timestamp
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        samples.append(
            {
                "id": point.id,
                "name": point.name,
                "latitude": (
                    observation.latitude
                    if observation.latitude is not None
                    else point.latitude
                ),
                "longitude": (
                    observation.longitude
                    if observation.longitude is not None
                    else point.longitude
                ),
                "location_type": point.location_type,
                "notes": point.notes,
                "demand_weight": point.demand_weight,
                "effective_weight_percent": round(
                    point.demand_weight / covered_weight * 100.0,
                    2,
                ),
                "temperature_c": round(observation.temperature_c, 2),
                "timestamp": timestamp,
                "provider_name": source_name,
                "status": "AVAILABLE",
            }
        )

    return {
        "label": TEMPERATURE_AGGREGATION_LABEL,
        "method": TEMPERATURE_AGGREGATION_METHOD,
        "policy_version": TEMPERATURE_AGGREGATION_POLICY_VERSION,
        "policy_status": policy_status,
        "status": (
            "COMPLETE"
            if len(valid_by_id) == len(TRINIDAD_TEMPERATURE_SAMPLING_POINTS)
            else "DEGRADED"
        ),
        "source_name": source_name,
        "weighted_average_c": round(weighted_average, 2),
        "minimum_c": round(min(temperatures), 2),
        "maximum_c": round(max(temperatures), 2),
        "spread_c": round(max(temperatures) - min(temperatures), 2),
        "sample_count": len(valid_by_id),
        "expected_sample_count": len(TRINIDAD_TEMPERATURE_SAMPLING_POINTS),
        "weight_coverage_percent": round(coverage_percent, 2),
        "samples": samples,
    }


WEATHER_NUMERIC_FIELDS = (
    "temperature_c",
    "humidity_percent",
    "rainfall_mm_hr",
    "cloud_cover_percent",
    "wind_speed_kmh",
    "pressure_hpa",
    "precipitation_probability_percent",
)


def build_weather_aggregation(
    observations: Iterable[TemperatureObservation],
    *,
    source_name: str,
    minimum_weight_coverage_percent: float,
    policy_status: str,
) -> dict[str, Any] | None:
    observations = list(observations)
    temperature_aggregate = build_temperature_aggregation(
        observations,
        source_name=source_name,
        minimum_weight_coverage_percent=minimum_weight_coverage_percent,
        policy_status=policy_status,
    )
    if temperature_aggregate is None:
        return None

    points_by_id = {
        point.id: point for point in TRINIDAD_TEMPERATURE_SAMPLING_POINTS
    }
    observations_by_id = {
        observation.point_id: observation
        for observation in observations
        if observation.point_id in points_by_id
    }
    weighted_fields: dict[str, float] = {}
    field_coverage: dict[str, float] = {}
    total_weight = sum(point.demand_weight for point in points_by_id.values())

    for field_name in WEATHER_NUMERIC_FIELDS:
        weighted_total = 0.0
        covered_weight = 0.0
        for point_id, observation in observations_by_id.items():
            value = _finite_number(getattr(observation, field_name, None))
            if value is None:
                continue
            weight = points_by_id[point_id].demand_weight
            weighted_total += value * weight
            covered_weight += weight
        if covered_weight > 0:
            weighted_fields[field_name] = weighted_total / covered_weight
            field_coverage[field_name] = (
                covered_weight / total_weight * 100.0 if total_weight else 0.0
            )

    direction_sin = 0.0
    direction_cos = 0.0
    direction_weight = 0.0
    for point_id, observation in observations_by_id.items():
        direction = _finite_number(observation.wind_direction_deg)
        if direction is None:
            continue
        weight = points_by_id[point_id].demand_weight
        radians = math.radians(direction % 360.0)
        direction_sin += math.sin(radians) * weight
        direction_cos += math.cos(radians) * weight
        direction_weight += weight
    if direction_weight > 0:
        weighted_fields["wind_direction_deg"] = (
            math.degrees(math.atan2(direction_sin, direction_cos)) + 360.0
        ) % 360.0
        field_coverage["wind_direction_deg"] = (
            direction_weight / total_weight * 100.0 if total_weight else 0.0
        )

    sample_by_id = {
        str(sample["id"]): sample for sample in temperature_aggregate["samples"]
    }
    for point_id, observation in observations_by_id.items():
        sample = sample_by_id.get(point_id)
        if sample is None:
            continue
        for field_name in WEATHER_NUMERIC_FIELDS[1:] + ("wind_direction_deg",):
            value = _finite_number(getattr(observation, field_name, None))
            sample[field_name] = round(value, 2) if value is not None else None

    temperature_aggregate.update(
        {
            "label": "Trinidad and Tobago weighted weather",
            "weighted_average_c": round(
                weighted_fields["temperature_c"],
                2,
            ),
            "weighted_humidity_percent": _rounded(
                weighted_fields.get("humidity_percent"),
                1,
            ),
            "weighted_rainfall_mm_hr": _rounded(
                weighted_fields.get("rainfall_mm_hr"),
                2,
            ),
            "weighted_cloud_cover_percent": _rounded(
                weighted_fields.get("cloud_cover_percent"),
                1,
            ),
            "weighted_wind_speed_kmh": _rounded(
                weighted_fields.get("wind_speed_kmh"),
                1,
            ),
            "weighted_wind_direction_deg": _rounded(
                weighted_fields.get("wind_direction_deg"),
                1,
            ),
            "weighted_pressure_hpa": _rounded(
                weighted_fields.get("pressure_hpa"),
                1,
            ),
            "weighted_precipitation_probability_percent": _rounded(
                weighted_fields.get("precipitation_probability_percent"),
                1,
            ),
            "field_weight_coverage_percent": {
                field_name: round(coverage, 2)
                for field_name, coverage in field_coverage.items()
            },
        }
    )
    return temperature_aggregate


def _finite_number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _rounded(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None
