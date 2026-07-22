from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.capacity_plan import (
    CapacityActionStatus,
    CapacityPlanEvaluateRequest,
    CapacityStartActionRequest,
)
from app.schemas.grid import GridStatusResponse, TelemetryQuality
from app.schemas.probability import ProbabilityResponse
from app.services.capacity_planning_service import (
    CapacityPlanningService,
    InvalidCapacityPlan,
)
from app.services.risk_probability_engine import (
    OperatingForecastPoint,
    OperatingRiskInput,
    RiskProbabilityEngine,
    risk_result_details,
)


ISSUE_TIME = datetime(2026, 6, 20, 2, tzinfo=timezone.utc)


def _probability(
    current_tra_mw: float = 1000.0,
    points: tuple[OperatingForecastPoint, ...] | None = None,
) -> ProbabilityResponse:
    profile = points or (
        OperatingForecastPoint(
            horizon_minutes=60,
            forecast_timestamp=ISSUE_TIME + timedelta(hours=1),
            forecast_demand_mw=975.0,
            forecast_uncertainty_mw=10.0,
        ),
    )
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=profile[0].forecast_demand_mw,
            forecast_uncertainty_mw=profile[0].forecast_uncertainty_mw,
            current_demand_mw=950.0,
            online_capacity_mw=current_tra_mw,
            available_capacity_mw=1200.0,
            spinning_reserve_mw=80.0,
            forecast_profile=profile,
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


def _grid(current_tra_mw: float = 1000.0) -> GridStatusResponse:
    return GridStatusResponse.model_validate(
        {
            "timestamp": ISSUE_TIME,
            "current_demand_mw": 950.0,
            "current_generation_mw": current_tra_mw,
            "total_available_capacity_mw": 1200.0,
            "reserve_margin_percent": 26.3,
            "spinning_reserve_mw": 80.0,
            "spinning_reserve_source": "GSYS SYSTEM_CORRECTED_SPIN_TOTAL",
            "grid_status": "WATCH",
            "demand_period": "NIGHT",
            "source_provider": "HistoricalScadaReplay",
            "generation_units": [],
            "quality_status": "GOOD",
        }
    )


def _service_and_snapshot(
    probability: ProbabilityResponse | None = None,
    current_tra_mw: float = 1000.0,
) -> tuple[CapacityPlanningService, str]:
    service = CapacityPlanningService(context_ttl_seconds=60)
    snapshot_id = "snapshot-1"
    service.build_snapshot_plan(
        snapshot_id,
        _grid(current_tra_mw),
        probability or _probability(current_tra_mw),
    )
    return service, snapshot_id


def test_snapshot_plan_is_anchored_to_current_tra_and_recommends_smallest_block():
    service, snapshot_id = _service_and_snapshot()

    plan = service.evaluate_what_if(
        CapacityPlanEvaluateRequest(snapshot_id=snapshot_id)
    )
    recommended = service.build_snapshot_plan(
        "snapshot-2", _grid(), _probability()
    )

    assert all(point.baseline_tra_mw == 1000.0 for point in plan.profile)
    assert all(point.planned_tra_mw == 1000.0 for point in plan.profile)
    assert len(recommended.recommended_actions) == 1
    assert recommended.recommended_actions[0].count == 1
    assert recommended.recommended_actions[0].total_capacity_mw == 15.0
    assert recommended.baseline_peak_risk_percent > recommended.post_plan_peak_risk_percent
    assert "REVIEW START OF 1 X SMALL FAST-START SET" in recommended.system_suggestion
    assert any("No-action peak risk" in item for item in recommended.system_suggestion_basis)


def test_small_block_applies_at_20_minutes_but_not_at_19_minutes():
    points = (
        OperatingForecastPoint(
            horizon_minutes=19,
            forecast_timestamp=ISSUE_TIME + timedelta(minutes=19),
            forecast_demand_mw=975.0,
            forecast_uncertainty_mw=10.0,
        ),
        OperatingForecastPoint(
            horizon_minutes=20,
            forecast_timestamp=ISSUE_TIME + timedelta(minutes=20),
            forecast_demand_mw=975.0,
            forecast_uncertainty_mw=10.0,
        ),
    )
    service, snapshot_id = _service_and_snapshot(_probability(points=points))

    plan = service.evaluate_what_if(
        CapacityPlanEvaluateRequest(
            snapshot_id=snapshot_id,
            actions=[
                CapacityStartActionRequest(
                    block_id="small-fast-start",
                    count=1,
                    start_at=ISSUE_TIME,
                )
            ],
        )
    )

    assert plan.profile[0].horizon_minutes == 19
    assert plan.profile[0].applied_start_capacity_mw == 0
    assert plan.profile[0].planned_tra_mw == 1000
    assert plan.profile[1].horizon_minutes == 20
    assert plan.profile[1].applied_start_capacity_mw == 15
    assert plan.profile[1].planned_tra_mw == 1015


def test_three_small_set_limit_is_enforced():
    service, snapshot_id = _service_and_snapshot()

    with pytest.raises(InvalidCapacityPlan, match="at most 3"):
        service.evaluate_what_if(
            CapacityPlanEvaluateRequest(
                snapshot_id=snapshot_id,
                actions=[
                    CapacityStartActionRequest(
                        block_id="small-fast-start",
                        count=4,
                    )
                ],
            )
        )


def test_unconfigured_heavy_capacity_cannot_be_evaluated():
    service, snapshot_id = _service_and_snapshot()

    with pytest.raises(InvalidCapacityPlan, match="not configured"):
        service.evaluate_what_if(
            CapacityPlanEvaluateRequest(
                snapshot_id=snapshot_id,
                actions=[
                    CapacityStartActionRequest(
                        block_id="heavy-start-unconfigured",
                        count=1,
                    )
                ],
            )
        )


def test_expired_action_is_excluded_until_current_tra_confirms_it():
    service, snapshot_id = _service_and_snapshot()

    plan = service.evaluate_what_if(
        CapacityPlanEvaluateRequest(
            snapshot_id=snapshot_id,
            actions=[
                CapacityStartActionRequest(
                    block_id="small-fast-start",
                    count=1,
                    start_at=ISSUE_TIME - timedelta(minutes=21),
                )
            ],
        )
    )

    action = plan.evaluated_actions[0]
    assert action.action_status == CapacityActionStatus.VERIFICATION_REQUIRED
    assert action.applied_to_projection is False
    assert all(point.planned_tra_mw == 1000 for point in plan.profile)
    assert any("excluded until TRA confirms" in warning for warning in plan.warnings)


def test_future_observed_tra_in_baseline_input_is_not_used_by_planner():
    probability = _probability(
        points=(
            OperatingForecastPoint(
                horizon_minutes=60,
                forecast_timestamp=ISSUE_TIME + timedelta(hours=1),
                forecast_demand_mw=1100.0,
                forecast_uncertainty_mw=20.0,
                forecast_tra_mw=1500.0,
                tra_projection_basis="FUTURE_OBSERVED_TRA_FOR_TEST",
            ),
        )
    )
    service, snapshot_id = _service_and_snapshot(
        probability=probability,
        current_tra_mw=1000.0,
    )

    plan = service.evaluate_what_if(
        CapacityPlanEvaluateRequest(snapshot_id=snapshot_id)
    )

    assert plan.profile[0].baseline_tra_mw == 1000.0
    assert plan.profile[0].planned_tra_mw == 1000.0
    assert plan.profile[0].baseline_capacity_risk_percent > 99


def test_current_tra_change_moves_baseline_risk_monotonically():
    low_tra = CapacityPlanningService().build_snapshot_plan(
        "low", _grid(980.0), _probability(980.0)
    )
    high_tra = CapacityPlanningService().build_snapshot_plan(
        "high", _grid(1020.0), _probability(1020.0)
    )

    assert low_tra.baseline_peak_risk_percent > high_tra.baseline_peak_risk_percent


def test_low_risk_system_suggestion_holds_current_tra():
    probability = _probability(
        points=(
            OperatingForecastPoint(
                horizon_minutes=60,
                forecast_timestamp=ISSUE_TIME + timedelta(hours=1),
                forecast_demand_mw=900.0,
                forecast_uncertainty_mw=10.0,
            ),
        )
    )

    plan = CapacityPlanningService().build_snapshot_plan(
        "low-risk",
        _grid(),
        probability,
    )

    assert plan.recommended_actions == []
    assert plan.system_suggestion == (
        "MAINTAIN CURRENT TRA AND MONITOR FORECAST CONDITIONS"
    )


def test_what_if_keeps_machine_suggestion_separate_from_operator_selection():
    service, snapshot_id = _service_and_snapshot()
    automatic = service.build_snapshot_plan(
        "automatic",
        _grid(),
        _probability(),
    )

    what_if = service.evaluate_what_if(
        CapacityPlanEvaluateRequest(snapshot_id=snapshot_id)
    )

    assert automatic.recommended_actions
    assert what_if.evaluated_actions == []
    assert what_if.system_suggestion == automatic.system_suggestion


@pytest.mark.parametrize("quality", [TelemetryQuality.BAD, TelemetryQuality.STALE])
def test_bad_or_stale_current_tra_fails_safely(quality: TelemetryQuality):
    grid = _grid().model_copy(update={"quality_status": quality})

    plan = CapacityPlanningService().build_snapshot_plan(
        "bad-quality",
        grid,
        _probability(),
    )

    assert plan.status == "UNAVAILABLE"
    assert plan.profile == []
    assert plan.recommended_actions == []
    assert plan.system_suggestion.startswith("VERIFY CURRENT TRA")


def test_missing_current_tra_evidence_fails_safely():
    grid = _grid().model_copy(
        update={"missing_fields": ["current_generation_mw"]}
    )

    plan = CapacityPlanningService().build_snapshot_plan(
        "missing-tra",
        grid,
        _probability(),
    )

    assert plan.status == "UNAVAILABLE"
    assert any("marked missing" in warning for warning in plan.warnings)


def test_live_current_tra_timestamp_must_be_fresh():
    observed_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    grid = _grid().model_copy(
        update={
            "timestamp": observed_at,
            "source_provider": "MockGridProvider",
        }
    )

    plan = CapacityPlanningService().build_snapshot_plan(
        "stale-live-tra",
        grid,
        _probability(),
    )

    assert plan.status == "UNAVAILABLE"
    assert plan.current_tra_age_seconds is not None
    assert plan.current_tra_age_seconds >= 119
