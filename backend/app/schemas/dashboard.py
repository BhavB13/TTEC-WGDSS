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


class ForecastBundleResponse(BaseModel):
    items: list[ForecastResponse]


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
