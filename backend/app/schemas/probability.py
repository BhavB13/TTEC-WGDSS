from datetime import datetime

from pydantic import BaseModel, Field


class RiskDriverResponse(BaseModel):
    label: str
    direction: str
    category: str


class RiskHorizonResponse(BaseModel):
    horizon_minutes: int
    forecast_timestamp: datetime | None = None
    probability: float = Field(ge=0.0, le=1.0)
    forecast_demand_mw: float
    forecast_uncertainty_mw: float
    forecast_lower_mw: float
    forecast_upper_mw: float
    confidence_level: float = Field(ge=0.0, le=1.0)
    immediate_online_capacity_mw: float
    safe_online_capacity_mw: float
    required_reserve_mw: float
    online_headroom_mw: float
    reserve_adjusted_headroom_mw: float
    expected_shortfall_mw: float
    conservative_shortfall_mw: float
    expected_load_rise_mw: float
    weather_effect_mw: float
    forecast_confidence: float = Field(ge=0.0, le=1.0)
    startup_lead_time_minutes: int
    decision_deadline_minutes: int | None = None
    decision_deadline_at: datetime | None = None
    urgency: str


class ProbabilityResponse(BaseModel):
    engine_version: str = "unknown"
    policy_status: str = "PROTOTYPE_UNCONFIRMED"
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
    risk_profile: list[RiskHorizonResponse] = Field(default_factory=list)
    peak_risk_horizon_minutes: int | None = None
    peak_risk_timestamp: datetime | None = None
    forecast_lower_mw: float = 0.0
    forecast_upper_mw: float = 0.0
    immediate_online_capacity_mw: float = 0.0
    safe_online_capacity_mw: float = 0.0
    required_reserve_mw: float = 0.0
    online_headroom_mw: float = 0.0
    reserve_adjusted_headroom_mw: float = 0.0
    severity_level: str = "NONE"
    urgency: str = "ROUTINE"
    decision_deadline_minutes: int | None = None
    decision_deadline_at: datetime | None = None
    drivers: list[RiskDriverResponse] = Field(default_factory=list)
    increasing_factors: list[str] = Field(default_factory=list)
    reducing_factors: list[str] = Field(default_factory=list)
    quality_warnings: list[str] = Field(default_factory=list)
    probability_method: str = "NORMAL_RESIDUAL_EXCEEDANCE"
    aggregation_method: str = "MAX_HORIZON_PROBABILITY"
    capacity_basis: str = "TRA_ONLY"
    formula_version: str = "wgdss-operating-risk-v3"
