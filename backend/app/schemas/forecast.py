from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ForecastResponse(BaseModel):
    forecast_timestamp: datetime
    temperature_c: float
    humidity_percent: float
    rainfall_mm_hr: float
    cloud_cover_percent: float
    wind_speed_kmh: float
    weather_condition: str
    heat_index_c: float
    precipitation_probability_percent: float
    confidence_score: float
    rain_severity: str
    provider_name: str
    source_count: int = 1
    source_names: list[str] = Field(default_factory=list)
    source_sync_status: Literal["COMPLETE", "DEGRADED"] = "DEGRADED"
    field_source_counts: dict[str, int] = Field(default_factory=dict)
    temperature_spread_c: float = 0.0
    cloud_cover_spread_percent: float = 0.0
