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
    notes: list[str] = Field(default_factory=list)
