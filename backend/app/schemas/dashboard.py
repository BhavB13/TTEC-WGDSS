from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.calibration import CalibrationSnapshotResponse
from app.schemas.capacity_plan import CapacityPlanResponse
from app.schemas.data_quality import DataQualityResponse
from app.schemas.forecast import ForecastResponse
from app.schemas.grid import GridStatusResponse
from app.schemas.model_status import (
    DemandForecastBundleResponse,
    ModelStatusResponse,
    ScadaStatusResponse,
)
from app.schemas.probability import ProbabilityResponse
from app.schemas.recommendation import RecommendationResponse
from app.schemas.replay import ReplayDashboardResponse
from app.schemas.weather import CurrentWeatherResponse
from app.schemas.dashboard_time import DashboardTimeContextResponse
from datetime import datetime


class ForecastBundleResponse(BaseModel):
    items: list[ForecastResponse]


class InferenceProvenanceResponse(BaseModel):
    data_mode: str
    source_provider: str
    source_observation_time: datetime | None = None
    source_available_at: datetime | None = None
    forecast_issue_time: datetime | None = None
    model_version: str | None = None
    artifact_hash: str | None = None
    training_cutoff: datetime | None = None
    status: str
    advisory_only: bool = True


class DashboardSnapshotResponse(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: str(uuid4()))
    weather: CurrentWeatherResponse
    grid: GridStatusResponse
    forecast: ForecastBundleResponse
    probability: ProbabilityResponse
    recommendation: RecommendationResponse
    calibration: CalibrationSnapshotResponse | None = None
    data_quality: DataQualityResponse
    demand_forecast: DemandForecastBundleResponse | None = None
    model_status: ModelStatusResponse | None = None
    scada_status: ScadaStatusResponse | None = None
    replay: ReplayDashboardResponse | None = None
    capacity_plan: CapacityPlanResponse | None = None
    # Optional for persisted legacy snapshots and internal constructors.
    # DashboardService always supplies it on the public snapshot endpoint.
    time_context: DashboardTimeContextResponse | None = None
    inference_provenance: InferenceProvenanceResponse | None = None
