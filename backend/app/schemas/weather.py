from datetime import datetime

from pydantic import BaseModel, Field


class TemperatureSampleResponse(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    location_type: str
    notes: str
    demand_weight: float
    effective_weight_percent: float
    temperature_c: float
    humidity_percent: float | None = None
    rainfall_mm_hr: float | None = None
    cloud_cover_percent: float | None = None
    wind_speed_kmh: float | None = None
    wind_direction_deg: float | None = None
    pressure_hpa: float | None = None
    precipitation_probability_percent: float | None = None
    timestamp: datetime | None = None
    provider_name: str
    status: str


class TemperatureAggregationResponse(BaseModel):
    label: str
    method: str
    policy_version: str
    policy_status: str
    status: str
    source_name: str
    weighted_average_c: float
    weighted_humidity_percent: float | None = None
    weighted_rainfall_mm_hr: float | None = None
    weighted_cloud_cover_percent: float | None = None
    weighted_wind_speed_kmh: float | None = None
    weighted_wind_direction_deg: float | None = None
    weighted_pressure_hpa: float | None = None
    weighted_precipitation_probability_percent: float | None = None
    minimum_c: float
    maximum_c: float
    spread_c: float
    sample_count: int
    expected_sample_count: int
    weight_coverage_percent: float
    field_weight_coverage_percent: dict[str, float] = Field(
        default_factory=dict
    )
    samples: list[TemperatureSampleResponse] = Field(default_factory=list)


class CurrentWeatherResponse(BaseModel):
    timestamp: datetime | None = None
    temperature_c: float
    humidity_percent: float
    rainfall_mm_hr: float
    cloud_cover_percent: float
    wind_speed_kmh: float
    weather_condition: str
    heat_index_c: float
    rain_severity: str
    wind_direction_deg: float | None = None
    pressure_hpa: float | None = None
    provider_name: str
    temperature_aggregation: TemperatureAggregationResponse | None = None
    weather_aggregation: TemperatureAggregationResponse | None = None
