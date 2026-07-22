from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.capacity_plan import evaluate_capacity_plan
from app.main import app
from app.schemas.capacity_plan import (
    CapacityPlanEvaluateRequest,
    CapacityStartActionRequest,
)
from app.schemas.grid import GridStatusResponse
from app.schemas.probability import ProbabilityResponse
from app.services.capacity_planning_service import capacity_planning_service
from app.services.risk_probability_engine import (
    OperatingForecastPoint,
    OperatingRiskInput,
    RiskProbabilityEngine,
    risk_result_details,
)


ISSUE_TIME = datetime(2026, 6, 20, 2, tzinfo=timezone.utc)


def _grid() -> GridStatusResponse:
    return GridStatusResponse.model_validate(
        {
            "timestamp": ISSUE_TIME,
            "current_demand_mw": 950,
            "current_generation_mw": 1000,
            "total_available_capacity_mw": 1200,
            "reserve_margin_percent": 26.3,
            "grid_status": "WATCH",
            "demand_period": "NIGHT",
            "source_provider": "HistoricalScadaReplay",
            "quality_status": "GOOD",
        }
    )


def _probability() -> ProbabilityResponse:
    point = OperatingForecastPoint(
        horizon_minutes=60,
        forecast_timestamp=ISSUE_TIME + timedelta(hours=1),
        forecast_demand_mw=975,
        forecast_uncertainty_mw=10,
    )
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=point.forecast_demand_mw,
            forecast_uncertainty_mw=point.forecast_uncertainty_mw,
            current_demand_mw=950,
            online_capacity_mw=1000,
            available_capacity_mw=1200,
            spinning_reserve_mw=80,
            forecast_profile=(point,),
            available_capacity_is_verified=True,
        )
    )
    return ProbabilityResponse(
        engine_version=result.engine_version,
        policy_status=result.policy_status,
        probability_score=result.probability_score,
        risk_level=result.risk_level,
        forecast_demand_30m=result.forecast_demand_mw,
        forecast_demand_60m=result.forecast_demand_mw,
        factors=result.reasons,
        reason="; ".join(result.reasons),
        **risk_result_details(result),
    )


def test_capacity_plan_endpoint_is_registered():
    operation = app.openapi()["paths"]["/api/v1/capacity-plan/evaluate"]

    assert "post" in operation


@pytest.mark.asyncio
async def test_capacity_plan_endpoint_evaluates_registered_snapshot():
    snapshot_id = f"api-{uuid4()}"
    capacity_planning_service.build_snapshot_plan(
        snapshot_id,
        _grid(),
        _probability(),
    )

    response = await evaluate_capacity_plan(
        CapacityPlanEvaluateRequest(
            snapshot_id=snapshot_id,
            actions=[
                CapacityStartActionRequest(
                    block_id="small-fast-start",
                    count=1,
                )
            ],
        )
    )

    assert response.snapshot_id == snapshot_id
    assert response.action_source == "OPERATOR_WHAT_IF"
    assert response.evaluated_actions[0].count == 1
    assert response.profile[0].baseline_tra_mw == 1000
    assert response.profile[0].planned_tra_mw == 1015


@pytest.mark.asyncio
async def test_capacity_plan_endpoint_rejects_unknown_snapshot():
    with pytest.raises(HTTPException) as caught:
        await evaluate_capacity_plan(
            CapacityPlanEvaluateRequest(snapshot_id=f"missing-{uuid4()}")
        )

    assert caught.value.status_code == 404
    assert "refresh the dashboard" in str(caught.value.detail)
