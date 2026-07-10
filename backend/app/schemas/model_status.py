from datetime import datetime

from pydantic import BaseModel, Field


class DemandForecastHorizonResponse(BaseModel):
    horizon_hours: int
    forecast_timestamp: datetime
    forecast_demand_mw: float
    forecast_uncertainty_mw: float
    model_name: str
    model_version: str
    baseline_name: str
    baseline_forecast_mw: float
    quality_status: str


class DemandForecastBundleResponse(BaseModel):
    horizons: list[DemandForecastHorizonResponse] = Field(default_factory=list)


class ModelMetricsResponse(BaseModel):
    mae: float | None = None
    rmse: float | None = None
    mape: float | None = None
    residual_std: float | None = None


class BaselineComparisonResponse(BaseModel):
    best_baseline: str | None = None
    ml_beats_baseline: bool | None = None


class ModelStatusResponse(BaseModel):
    active_model: str | None = None
    model_version: str | None = None
    mode: str = "UNAVAILABLE"
    trained_through: datetime | None = None
    metrics: ModelMetricsResponse = Field(default_factory=ModelMetricsResponse)
    baseline_comparison: BaselineComparisonResponse = Field(
        default_factory=BaselineComparisonResponse
    )


class ScadaStatusResponse(BaseModel):
    source: str = "unavailable"
    latest_snapshot: datetime | None = None
    quality_status: str = "UNAVAILABLE"
    missing_fields: str = ""
