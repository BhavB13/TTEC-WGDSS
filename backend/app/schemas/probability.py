from pydantic import BaseModel


class ProbabilityResponse(BaseModel):
    engine_version: str = "unknown"
    probability_score: float
    risk_level: str
    forecast_demand_30m: float
    forecast_demand_60m: float
    factors: list[str]
    reason: str
    decision_action: str = "NO ACTION"
    generator_set: str = "NONE"
    recommended_capacity_mw: float = 0.0
    projected_shortfall_mw: float = 0.0
    expected_shortfall_mw: float = 0.0
    expected_load_rise_mw: float = 0.0
    expected_rise_minutes: int = 0
    startup_time_minutes: int = 0
    decision_confidence: float = 0.0
    weather_effect_mw: float = 0.0
    available_start_capacity_mw: float | None = None
    residual_shortfall_mw: float = 0.0
