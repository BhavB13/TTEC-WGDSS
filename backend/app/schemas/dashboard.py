from pydantic import BaseModel

from app.schemas.calibration import CalibrationSnapshotResponse
from app.schemas.data_quality import DataQualityResponse
from app.schemas.forecast import ForecastResponse
from app.schemas.grid import GridStatusResponse
from app.schemas.probability import ProbabilityResponse
from app.schemas.recommendation import RecommendationResponse
from app.schemas.weather import CurrentWeatherResponse


class ForecastBundleResponse(BaseModel):
    items: list[ForecastResponse]


class DashboardSnapshotResponse(BaseModel):
    weather: CurrentWeatherResponse
    grid: GridStatusResponse
    forecast: ForecastBundleResponse
    probability: ProbabilityResponse
    recommendation: RecommendationResponse
    calibration: CalibrationSnapshotResponse | None = None
    data_quality: DataQualityResponse
