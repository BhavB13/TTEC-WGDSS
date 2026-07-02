from pydantic import BaseModel


class ProbabilityResponse(BaseModel):
    engine_version: str = "unknown"
    probability_score: float
    risk_level: str
    forecast_demand_30m: float
    forecast_demand_60m: float
    factors: list[str]
    reason: str
