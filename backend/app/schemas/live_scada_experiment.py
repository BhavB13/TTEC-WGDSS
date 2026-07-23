from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SnapshotFieldEvidence(BaseModel):
    field: str
    source_tag: str | None = None
    source_member: str | None = None
    timestamp: datetime | None = None
    raw_value: str | None = None
    cleaned_value: float | None = None
    engineering_unit: str | None = None
    raw_quality: str | None = None
    normalized_quality: str | None = None
    status: str
    warnings: list[str] = Field(default_factory=list)


class SnapshotHourlyPoint(BaseModel):
    timestamp: datetime
    available_at: datetime
    demand_mw: float | None = None
    generation_tra_mw: float | None = None
    spinning_reserve_mw: float | None = None
    available_capacity_ta_mw: float | None = None
    temperature_c: float | None = None
    coverage_percent: dict[str, float] = Field(default_factory=dict)
    quality_status: str
    warnings: list[str] = Field(default_factory=list)


class SnapshotImportSummary(BaseModel):
    source_filename: str
    source_path: str
    source_file_hash: str
    source_format: str
    source_timezone: str = "America/Port_of_Spain"
    imported_at: datetime
    available_start: datetime | None = None
    available_end: datetime | None = None
    latest_valid_timestamp: datetime | None = None
    model_issue_hour: datetime | None = None
    raw_record_count: int = 0
    cleaned_record_count: int = 0
    malformed_record_count: int = 0
    duplicate_record_count: int = 0
    future_record_count: int = 0
    missing_required_variables: list[str] = Field(default_factory=list)
    field_evidence: list[SnapshotFieldEvidence] = Field(default_factory=list)
    hourly_series: list[SnapshotHourlyPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FrozenModelMetadata(BaseModel):
    status: str
    model_name: str | None = None
    model_version: str | None = None
    feature_profile: str | None = None
    artifact_hash: str | None = None
    artifact_path: str | None = None
    training_start_at: datetime | None = None
    training_end_at: datetime | None = None
    training_policy: str = "October-May only; June and snapshot excluded"
    snapshot_used_for_training: bool = False
    preprocessing_refit: bool = False
    warnings: list[str] = Field(default_factory=list)


class ExperimentWeatherSnapshot(BaseModel):
    fetched_at: datetime
    boundary_timestamp: datetime
    current: dict[str, object] | None = None
    forecast: list[dict[str, object]] = Field(default_factory=list)
    observed_temperature_source: str = "SCADA snapshot"
    post_boundary_weather_source: str | None = None
    response_hash: str
    warnings: list[str] = Field(default_factory=list)


class ExperimentalForecastPoint(BaseModel):
    horizon_hours: int
    forecast_timestamp: datetime
    forecast_demand_mw: float
    uncertainty_mw: float
    lower_bound_mw: float
    upper_bound_mw: float
    model_name: str
    model_version: str
    status: Literal["MODEL_INFERENCE", "REFERENCE_ONLY"]
    input_quality: str
    reasons: list[str] = Field(default_factory=list)


class ExperimentalRiskPoint(BaseModel):
    horizon_hours: int
    forecast_timestamp: datetime
    generation_tra_mw: float | None = None
    forecast_demand_mw: float | None = None
    projected_tra_minus_demand_mw: float | None = None
    required_reserve_mw: float
    generation_need_probability: float | None = None
    risk_level: str
    status: str
    reasons: list[str] = Field(default_factory=list)


class ExperimentalSessionArtifacts(BaseModel):
    manifest_path: str
    raw_audit_path: str
    cleaned_audit_path: str
    weather_snapshot_path: str
    test_report_path: str


class LiveScadaTestSession(BaseModel):
    schema_version: str = "wgdss-live-scada-test-v1"
    session_id: str
    experiment_label: str = "EXPERIMENTAL - STATIC SCADA SNAPSHOT"
    advisory_notice: str = (
        "READ-ONLY TEST ONLY - NO SCADA CONTROL OR AUTOMATIC DISPATCH"
    )
    created_at: datetime
    source: SnapshotImportSummary
    model: FrozenModelMetadata
    weather: ExperimentWeatherSnapshot
    model_inputs: list[dict[str, object]] = Field(default_factory=list)
    forecasts: list[ExperimentalForecastPoint] = Field(default_factory=list)
    reference_forecasts: list[ExperimentalForecastPoint] = Field(
        default_factory=list
    )
    risk: list[ExperimentalRiskPoint] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    processing_metadata: dict[str, object] = Field(default_factory=dict)
    artifacts: ExperimentalSessionArtifacts | None = None


class LiveScadaExperimentStatus(BaseModel):
    branch: str = "experiment/live-scada-snapshot"
    enabled: bool
    configured_source: bool
    source_path: str | None = None
    latest_session_id: str | None = None
    latest_available_timestamp: datetime | None = None
    message: str
