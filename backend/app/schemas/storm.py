from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class StormAdvisoryLinkResponse(BaseModel):
    advisory_number: str | None = None
    issuance: datetime | None = None
    url: str | None = None


class StormSystemResponse(BaseModel):
    id: str
    bin_number: str | None = None
    name: str | None = None
    basin: str | None = None
    classification: str | None = None
    classification_label: str | None = None
    intensity_knots: float | None = None
    pressure_mb: float | None = None
    latitude: str | None = None
    longitude: str | None = None
    latitude_numeric: float | None = None
    longitude_numeric: float | None = None
    movement_direction_deg: float | None = None
    movement_speed_mph: float | None = None
    last_update: datetime | None = None
    public_advisory: StormAdvisoryLinkResponse | None = None
    forecast_advisory: StormAdvisoryLinkResponse | None = None
    forecast_discussion: StormAdvisoryLinkResponse | None = None
    forecast_graphics: StormAdvisoryLinkResponse | None = None
    forecast_track_kmz_url: str | None = None
    wind_speed_probabilities_url: str | None = None


class StormTrackingResponse(BaseModel):
    source_url: str
    status: Literal["available", "unavailable"]
    fetched_at: datetime | None = None
    message: str | None = None
    active_storms: list[StormSystemResponse] = Field(default_factory=list)
