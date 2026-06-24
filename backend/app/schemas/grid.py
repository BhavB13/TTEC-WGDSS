from datetime import datetime

from pydantic import BaseModel, Field


class GenerationUnitResponse(BaseModel):
    station_name: str
    unit_name: str
    fuel_type: str
    available_capacity_mw: float
    current_output_mw: float
    status: str
    is_dispatchable: bool


class GridStatusResponse(BaseModel):
    timestamp: datetime | None = None
    current_demand_mw: float
    current_generation_mw: float
    total_available_capacity_mw: float
    reserve_margin_percent: float
    grid_status: str
    demand_period: str
    source_provider: str
    generation_units: list[GenerationUnitResponse] = Field(default_factory=list)
