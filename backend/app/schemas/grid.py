from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class TelemetryQuality(StrEnum):
    GOOD = "GOOD"
    UNCERTAIN = "UNCERTAIN"
    BAD = "BAD"
    STALE = "STALE"


class GenerationUnitResponse(BaseModel):
    station_name: str
    unit_name: str
    fuel_type: str
    available_capacity_mw: float
    current_output_mw: float
    status: str
    is_dispatchable: bool
    observed_at: datetime | None = None
    quality_status: TelemetryQuality = TelemetryQuality.GOOD
    source_tag: str | None = None


class GridStatusResponse(BaseModel):
    timestamp: datetime | None = None
    current_demand_mw: float
    current_generation_mw: float
    total_available_capacity_mw: float
    reserve_margin_percent: float
    spinning_reserve_mw: float | None = None
    spinning_reserve_source: str | None = None
    grid_status: str
    demand_period: str
    source_provider: str
    generation_units: list[GenerationUnitResponse] = Field(default_factory=list)
    received_at: datetime | None = None
    quality_status: TelemetryQuality = TelemetryQuality.GOOD
    missing_fields: list[str] = Field(default_factory=list)
