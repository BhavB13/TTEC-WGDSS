from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CapacityPlanStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    STALE_SNAPSHOT = "STALE_SNAPSHOT"


class CapacityActionSource(StrEnum):
    NONE = "NONE"
    SYSTEM_RECOMMENDED = "SYSTEM_RECOMMENDED"
    OPERATOR_WHAT_IF = "OPERATOR_WHAT_IF"


class CapacityActionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"


class GenerationBlockDefinitionResponse(BaseModel):
    block_id: str
    label: str
    block_class: str
    unit_capacity_mw: float | None = Field(default=None, gt=0)
    startable_count: int = Field(default=0, ge=0)
    startup_lead_time_minutes: int = Field(ge=0)
    enabled: bool
    provenance: str
    verification_status: str


class CapacityStartActionRequest(BaseModel):
    block_id: str = Field(min_length=1, max_length=100)
    count: int = Field(ge=1, le=100)
    start_at: datetime | None = None


class CapacityStartActionResponse(BaseModel):
    block_id: str
    block_label: str
    block_class: str
    count: int = Field(ge=1)
    unit_capacity_mw: float = Field(gt=0)
    total_capacity_mw: float = Field(gt=0)
    startup_lead_time_minutes: int = Field(ge=0)
    start_at: datetime
    start_by: datetime | None = None
    expected_online_at: datetime
    verification_status: str
    action_status: CapacityActionStatus
    applied_to_projection: bool


class CapacityPlanHorizonResponse(BaseModel):
    horizon_minutes: int = Field(gt=0)
    forecast_timestamp: datetime | None = None
    forecast_demand_mw: float
    forecast_uncertainty_mw: float = Field(gt=0)
    baseline_tra_mw: float
    baseline_reserve_mw: float
    baseline_capacity_risk_percent: float = Field(ge=0, le=100)
    baseline_capacity_status: str
    planned_tra_mw: float
    applied_start_capacity_mw: float = Field(ge=0)
    planned_reserve_mw: float
    planned_reserve_surplus_mw: float
    planned_reserve_deficit_mw: float = Field(ge=0)
    planned_capacity_risk_percent: float = Field(ge=0, le=100)
    planned_capacity_status: str
    required_reserve_mw: float


class CapacityPlanResponse(BaseModel):
    snapshot_id: str
    status: CapacityPlanStatus
    action_source: CapacityActionSource = CapacityActionSource.NONE
    advisory_only: bool = True
    advisory_notice: str = (
        "ADVISORY ONLY - MANUAL OPERATOR ACTION REQUIRED"
    )
    system_suggestion: str
    system_suggestion_basis: list[str] = Field(default_factory=list)
    issue_time: datetime | None = None
    current_tra_mw: float | None = None
    current_tra_observed_at: datetime | None = None
    current_tra_age_seconds: float | None = Field(default=None, ge=0)
    current_tra_source: str
    current_tra_quality_status: str
    current_tra_projection_basis: str = "CURRENT_TRA_HELD_NO_ACTION"
    required_reserve_mw: float
    target_risk_probability: float = Field(ge=0, le=1)
    baseline_peak_risk_percent: float = Field(ge=0, le=100)
    post_plan_peak_risk_percent: float = Field(ge=0, le=100)
    risk_reduction_percentage_points: float
    first_unprotected_horizon_minutes: int | None = None
    first_unprotected_at: datetime | None = None
    interim_unmitigated_risk: bool = False
    unresolved_capacity_mw: float = Field(default=0, ge=0)
    block_definitions: list[GenerationBlockDefinitionResponse] = Field(
        default_factory=list
    )
    recommended_actions: list[CapacityStartActionResponse] = Field(
        default_factory=list
    )
    evaluated_actions: list[CapacityStartActionResponse] = Field(
        default_factory=list
    )
    profile: list[CapacityPlanHorizonResponse] = Field(default_factory=list)
    configuration_status: str = "PROTOTYPE_UNCONFIRMED"
    warnings: list[str] = Field(default_factory=list)


class CapacityPlanEvaluateRequest(BaseModel):
    snapshot_id: str = Field(min_length=1, max_length=64)
    actions: list[CapacityStartActionRequest] = Field(default_factory=list)
