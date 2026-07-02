from datetime import datetime

from pydantic import BaseModel, Field


class DataQualityResponse(BaseModel):
    overall_status: str
    weather_status: str
    grid_status: str
    calibration_status: str
    weather_source: str
    grid_source: str
    observed_at: datetime | None = None
    age_seconds: int | None = None
    is_stale: bool = False
    fallback_used: bool = False
    grid_observed_at: datetime | None = None
    grid_age_seconds: int | None = None
    grid_is_stale: bool = False
    grid_fallback_used: bool = False
    decision_status: str = "AVAILABLE"
    notes: list[str] = Field(default_factory=list)
