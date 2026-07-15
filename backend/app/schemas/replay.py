from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReplayStatusResponse(BaseModel):
    mode: str = "SIMULATED_LIVE"
    dataset_label: str
    dataset_start: datetime
    dataset_end: datetime
    replay_start: datetime
    replay_end: datetime
    cursor_at: datetime
    is_playing: bool
    step_minutes: int
    speed_multiplier: float
    progress_percent: float
    revealed_records: int
    total_replay_records: int
    source: str


class OperationalTrendPointResponse(BaseModel):
    timestamp: datetime
    demand_mw: float
    generation_mw: float
    available_capacity_mw: float
    reserve_margin_percent: float
    temperature_c: float
    rainfall_mm_hr: float
    data_phase: Literal["HISTORICAL", "SIMULATED_LIVE"]


class LoadForecastPointResponse(BaseModel):
    timestamp: datetime
    forecast_demand_mw: float
    historical_average_mw: float
    actual_demand_mw: float | None = None
    uncertainty_mw: float


class ReplaySummaryResponse(BaseModel):
    historical_months: int
    historical_record_count: int
    historical_average_demand_mw: float
    historical_peak_demand_mw: float
    replay_month_label: str
    current_day_peak_forecast_mw: float


class MonthlyHistoryPointResponse(BaseModel):
    month: str
    average_demand_mw: float
    peak_demand_mw: float
    average_temperature_c: float
    rainfall_total_mm: float
    data_phase: Literal["HISTORICAL", "REPLAY_SOURCE"]


class ReplayDashboardResponse(BaseModel):
    status: ReplayStatusResponse
    operational_history: list[OperationalTrendPointResponse] = Field(default_factory=list)
    full_day_load_forecast: list[LoadForecastPointResponse] = Field(default_factory=list)
    monthly_history: list[MonthlyHistoryPointResponse] = Field(default_factory=list)
    summary: ReplaySummaryResponse


class ReplayControlRequest(BaseModel):
    action: Literal["play", "pause", "reset", "step", "configure"]
    step_minutes: int | None = Field(default=None, ge=15, le=1440)
    speed_multiplier: float | None = Field(default=None, ge=1, le=86400)
