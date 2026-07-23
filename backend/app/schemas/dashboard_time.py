from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class DaySeriesPointResponse(BaseModel):
    timestamp: datetime
    demand_mw: float | None = None
    generation_tra_mw: float | None = None
    spinning_reserve_mw: float | None = None
    available_capacity_mw: float | None = None
    temperature_c: float | None = None
    quality_status: str
    completeness_percent: float
    data_phase: Literal["JUNE_OBSERVED"] = "JUNE_OBSERVED"


class DashboardTimeContextResponse(BaseModel):
    selected_date: date
    active_date: date
    is_active_day: bool
    displayed_at: datetime
    granularity: Literal["hourly"] = "hourly"
    source: str
    value_classification: str
    available_start: date
    available_end: date
    available_dates: list[date] = Field(default_factory=list)
    completeness_percent: float
    record_count: int
    is_complete: bool
    notice: str | None = None
    series: list[DaySeriesPointResponse] = Field(default_factory=list)
