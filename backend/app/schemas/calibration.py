from datetime import datetime

from pydantic import BaseModel, Field


class CalibrationPointResponse(BaseModel):
    hour: int
    demand_mw: float | None = None
    spin_mw: float | None = None
    temperature_c: float | None = None
    quality_status: str | None = None


class CalibrationScenarioResponse(BaseModel):
    scenario_key: str
    scenario_label: str
    operating_regime: str
    source_workbook: str
    source_sheet: str
    demand_curve: list[CalibrationPointResponse] = Field(default_factory=list)
    scada_temperature_trace: list[CalibrationPointResponse] = Field(default_factory=list)


class CalibrationSnapshotResponse(BaseModel):
    source_archive: str | None = None
    imported_at: datetime | None = None
    selected_scenario_key: str | None = None
    selected_scenario_label: str | None = None
    selected_hour: int | None = None
    selected_temperature_c: float | None = None
    selected_demand_mw: float | None = None
    selected_next_demand_mw: float | None = None
    selected_spin_mw: float | None = None
    selected_next_spin_mw: float | None = None
    selection_reason: str | None = None
    selection_confidence: float | None = None
    scenario_scores: dict[str, float] = Field(default_factory=dict)
    scenarios: list[CalibrationScenarioResponse] = Field(default_factory=list)
