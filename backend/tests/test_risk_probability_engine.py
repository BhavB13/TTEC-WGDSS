import math
from datetime import datetime, timedelta
from statistics import NormalDist

import pytest

from app.services.risk_probability_engine import (
    OperatingForecastPoint,
    OperatingPolicy,
    OperatingRiskInput,
    RiskBacktestSample,
    RiskProbabilityEngine,
)


def _risk_input(
    *,
    forecast_demand_mw: float = 950.0,
    forecast_uncertainty_mw: float | None = 20.0,
    current_demand_mw: float = 930.0,
    forecast_tra_mw: float = 1000.0,
    available_capacity_mw: float = 1150.0,
    spinning_reserve_mw: float | None = 50.0,
    forecast_profile: tuple[OperatingForecastPoint, ...] = (),
    **overrides: object,
) -> OperatingRiskInput:
    payload = {
        "forecast_demand_mw": forecast_demand_mw,
        "forecast_uncertainty_mw": forecast_uncertainty_mw,
        "current_demand_mw": current_demand_mw,
        "online_capacity_mw": forecast_tra_mw,
        "available_capacity_mw": available_capacity_mw,
        "spinning_reserve_mw": spinning_reserve_mw,
        "forecast_profile": forecast_profile,
    }
    payload.update(overrides)
    return OperatingRiskInput(**payload)


def _policy(**overrides: object) -> OperatingPolicy:
    payload = {
        "status": "TEST_UNCONFIRMED",
        "required_reserve_mw": 30.0,
        "watch_probability_threshold": 0.20,
        "prepare_probability_threshold": 0.50,
        "add_generation_probability_threshold": 0.80,
        "fast_start_unit_capacity_mw": 15.0,
        "fast_start_max_capacity_mw": 30.0,
        "fast_start_lead_time_minutes": 20,
        "heavy_start_min_capacity_mw": 60.0,
        "heavy_start_max_capacity_mw": 120.0,
        "heavy_start_lead_time_minutes": 60,
    }
    payload.update(overrides)
    return OperatingPolicy(**payload)


def test_risk_engine_uses_injected_configurable_operating_policy():
    result = RiskProbabilityEngine(
        policy=_policy(required_reserve_mw=45.0)
    ).evaluate(_risk_input())

    assert result.required_reserve_mw == 45.0
    assert result.projected_reserve_mw == 50.0
    assert result.reserve_surplus_mw == 5.0
    assert result.policy_status == "TEST_UNCONFIRMED"
    assert any("test unconfirmed" in reason for reason in result.reasons)


def test_risk_engine_fails_closed_for_invalid_capacity_policy():
    result = RiskProbabilityEngine(
        policy=_policy(
            watch_probability_threshold=0.6,
            prepare_probability_threshold=0.5,
            fast_start_unit_capacity_mw=20,
            fast_start_max_capacity_mw=10,
            heavy_start_min_capacity_mw=100,
            heavy_start_max_capacity_mw=50,
        )
    ).evaluate(_risk_input())

    assert result.risk_level == "UNAVAILABLE"
    assert result.capacity_status == "Unavailable"
    assert "ordered capacity-status" in result.reasons[0]
    assert "fast-start maximum capacity" in result.reasons[0]
    assert "heavy-start maximum capacity" in result.reasons[0]


def test_projected_reserve_above_target_is_normal_with_continuous_probability():
    result = RiskProbabilityEngine().evaluate(_risk_input())

    expected_probability = NormalDist().cdf((30.0 - 50.0) / 20.0)
    assert result.probability_score == pytest.approx(expected_probability)
    assert result.capacity_risk_percent == pytest.approx(expected_probability * 100)
    assert result.capacity_status == "Normal"
    assert result.risk_level == "LOW"
    assert result.recommendation == "NO ACTION REQUIRED"
    assert result.forecast_demand_mw == 950.0
    assert result.forecast_tra_mw == 1000.0
    assert result.projected_reserve_mw == 50.0
    assert result.required_reserve_mw == 30.0
    assert result.reserve_surplus_mw == 20.0
    assert result.reserve_deficit_mw == 0.0


def test_projected_reserve_at_target_is_fifty_percent_and_prepare_generation():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(forecast_demand_mw=970.0)
    )

    assert result.probability_score == pytest.approx(0.5)
    assert result.capacity_risk_percent == pytest.approx(50.0)
    assert result.projected_reserve_mw == 30.0
    assert result.reserve_surplus_mw == 0.0
    assert result.reserve_deficit_mw == 0.0
    assert result.capacity_status == "Prepare Generation"
    assert result.recommendation == "PREPARE ADDITIONAL GENERATION"
    assert result.reserve_insufficient_horizon_minutes == 60


def test_projected_reserve_below_target_is_add_generation():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(forecast_demand_mw=990.0)
    )

    expected_probability = NormalDist().cdf((30.0 - 10.0) / 20.0)
    assert result.probability_score == pytest.approx(expected_probability)
    assert result.capacity_status == "Add Generation"
    assert result.risk_level == "HIGH"
    assert result.projected_reserve_mw == 10.0
    assert result.reserve_surplus_mw == -20.0
    assert result.reserve_deficit_mw == 20.0
    assert result.recommendation in {
        "START HEAVY GENERATOR SET",
        "PREPARE ADDITIONAL GENERATION",
    }


def test_probability_is_continuous_at_status_thresholds():
    engine = RiskProbabilityEngine()
    sigma = 20.0

    def demand_for_probability(probability: float) -> float:
        return 1000.0 - 30.0 + sigma * NormalDist().inv_cdf(probability)

    results = [
        engine.evaluate(
            _risk_input(
                forecast_demand_mw=demand_for_probability(probability),
                forecast_uncertainty_mw=sigma,
            )
        )
        for probability in (0.20, 0.50, 0.80)
    ]

    assert [result.probability_score for result in results] == pytest.approx(
        [0.20, 0.50, 0.80],
        abs=1e-12,
    )
    assert [result.capacity_status for result in results] == [
        "Watch",
        "Prepare Generation",
        "Add Generation",
    ]


def test_one_mw_boundary_crossing_does_not_jump_to_one_hundred_percent():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(forecast_demand_mw=971.0, forecast_uncertainty_mw=30.0)
    )

    assert 0.50 < result.probability_score < 0.52
    assert result.probability_score != 1.0


def test_probability_increases_with_demand_and_decreases_with_tra():
    engine = RiskProbabilityEngine()
    demand_scores = [
        engine.evaluate(_risk_input(forecast_demand_mw=demand)).probability_score
        for demand in (930.0, 950.0, 970.0, 990.0)
    ]
    tra_scores = [
        engine.evaluate(_risk_input(forecast_tra_mw=tra)).probability_score
        for tra in (980.0, 1000.0, 1020.0, 1040.0)
    ]

    assert demand_scores == sorted(demand_scores)
    assert tra_scores == sorted(tra_scores, reverse=True)


def test_corrected_system_spin_is_context_not_a_probability_term():
    engine = RiskProbabilityEngine()
    scores = [
        engine.evaluate(_risk_input(spinning_reserve_mw=spin)).probability_score
        for spin in (10.0, 50.0, 150.0)
    ]

    assert scores[0] == pytest.approx(scores[1])
    assert scores[1] == pytest.approx(scores[2])


def test_profile_selects_peak_and_headline_fields_from_same_horizon():
    reference = datetime(2026, 6, 15, 10)
    profile = (
        OperatingForecastPoint(
            60,
            950.0,
            20.0,
            forecast_timestamp=reference + timedelta(hours=1),
            forecast_tra_mw=1000.0,
            tra_projection_basis="SUPPLIED_TRA_SCHEDULE",
        ),
        OperatingForecastPoint(
            120,
            980.0,
            20.0,
            forecast_timestamp=reference + timedelta(hours=2),
            forecast_tra_mw=1010.0,
            tra_projection_basis="SUPPLIED_TRA_SCHEDULE",
        ),
        OperatingForecastPoint(
            180,
            990.0,
            20.0,
            forecast_timestamp=reference + timedelta(hours=3),
            forecast_tra_mw=1015.0,
            tra_projection_basis="SUPPLIED_TRA_SCHEDULE",
        ),
    )
    result = RiskProbabilityEngine().evaluate(
        _risk_input(forecast_profile=profile)
    )
    selected = max(result.risk_profile, key=lambda point: point.probability)

    assert result.peak_risk_horizon_minutes == selected.horizon_minutes == 180
    assert result.peak_risk_timestamp == selected.forecast_timestamp
    assert result.probability_score == selected.probability
    assert result.capacity_risk_percent == selected.capacity_risk_percent
    assert result.forecast_demand_mw == selected.forecast_demand_mw
    assert result.forecast_tra_mw == selected.forecast_tra_mw
    assert result.projected_reserve_mw == selected.projected_reserve_mw
    assert result.required_reserve_mw == selected.required_reserve_mw
    assert result.reserve_surplus_mw == selected.reserve_surplus_mw
    assert result.reserve_deficit_mw == selected.reserve_deficit_mw
    assert result.capacity_status == selected.capacity_status
    assert result.reserve_insufficient_horizon_minutes == 120
    assert result.reserve_insufficient_at == reference + timedelta(hours=2)


def test_current_tra_is_explicitly_held_when_future_schedule_is_unavailable():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(
            forecast_profile=(
                OperatingForecastPoint(60, 950.0, 20.0),
                OperatingForecastPoint(120, 960.0, 20.0),
            )
        )
    )

    assert all(point.forecast_tra_mw == 1000.0 for point in result.risk_profile)
    assert all(
        point.tra_projection_basis
        == "CURRENT_TRA_HELD_SCENARIO_NO_DISPATCH_PLAN"
        for point in result.risk_profile
    )
    assert any("No future TRA schedule" in warning for warning in result.quality_warnings)


def test_prediction_interval_can_supply_uncertainty():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(
            forecast_uncertainty_mw=None,
            forecast_profile=(
                OperatingForecastPoint(
                    60,
                    970.0,
                    None,
                    confidence_lower_mw=930.0,
                    confidence_upper_mw=1010.0,
                    confidence_level=0.90,
                ),
            ),
        )
    )

    expected_sigma = 80.0 / (2 * NormalDist().inv_cdf(0.95))
    assert result.risk_level != "UNAVAILABLE"
    assert result.forecast_uncertainty_mw == pytest.approx(expected_sigma)
    assert result.uncertainty_source == "PREDICTION_INTERVAL_NORMAL_EQUIVALENT"


def test_historical_rmse_is_used_as_documented_uncertainty_fallback():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(
            forecast_uncertainty_mw=None,
            historical_validation_rmse_mw=24.0,
        )
    )

    assert result.forecast_uncertainty_mw == 24.0
    assert result.uncertainty_source == "HISTORICAL_VALIDATION_RMSE_AS_SIGMA"


def test_historical_mae_is_converted_to_normal_equivalent_sigma():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(
            forecast_uncertainty_mw=None,
            historical_validation_mae_mw=20.0,
        )
    )

    assert result.forecast_uncertainty_mw == pytest.approx(
        20.0 * math.sqrt(math.pi / 2.0)
    )
    assert (
        result.uncertainty_source
        == "HISTORICAL_VALIDATION_MAE_NORMAL_EQUIVALENT"
    )


def test_probability_fails_safely_without_uncertainty_evidence():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(forecast_uncertainty_mw=None)
    )

    assert result.risk_level == "UNAVAILABLE"
    assert result.capacity_status == "Unavailable"
    assert result.recommendation == "DATA UNAVAILABLE"
    assert "forecast uncertainty" in result.reasons[0]


def test_missing_core_inputs_fail_safely():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=None,
            forecast_uncertainty_mw=20.0,
            current_demand_mw=900.0,
            online_capacity_mw=None,
            available_capacity_mw=1200.0,
            spinning_reserve_mw=50.0,
        )
    )

    assert result.risk_level == "UNAVAILABLE"
    assert result.probability_score == 0.0
    assert "forecast_demand_mw, online_capacity_mw" in result.reasons[0]


def test_demand_above_tra_is_a_high_risk_state_not_invalid_data():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(
            current_demand_mw=1005.0,
            forecast_demand_mw=1010.0,
            forecast_tra_mw=1000.0,
        )
    )

    assert result.risk_level == "HIGH"
    assert result.capacity_status == "Add Generation"
    assert result.projected_reserve_mw == -10.0
    assert result.reserve_deficit_mw == 40.0


def test_available_capacity_below_tra_is_rejected_as_inconsistent():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(forecast_tra_mw=1000.0, available_capacity_mw=990.0)
    )

    assert result.risk_level == "UNAVAILABLE"
    assert "available_capacity_mw not below online_capacity_mw" in result.reasons[0]


def test_add_generation_dispatch_uses_small_set_inside_start_window():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(
            forecast_demand_mw=990.0,
            forecast_uncertainty_mw=5.0,
            forecast_profile=(
                OperatingForecastPoint(20, 990.0, 5.0),
            ),
        )
    )

    assert result.capacity_status == "Add Generation"
    assert result.recommendation == "START BOTH 15 MW SMALL SETS"
    assert result.generator_set == "2 x 15 MW FAST-START"
    assert result.recommended_capacity_mw == 30.0
    assert result.startup_time_minutes == 20


def test_add_generation_does_not_claim_a_unit_without_verified_ta():
    result = RiskProbabilityEngine().evaluate(
        _risk_input(
            forecast_demand_mw=990.0,
            forecast_uncertainty_mw=5.0,
            available_capacity_is_verified=False,
            forecast_profile=(OperatingForecastPoint(20, 990.0, 5.0),),
        )
    )

    assert result.capacity_status == "Add Generation"
    assert result.recommendation == "PREPARE ADDITIONAL GENERATION"
    assert result.decision_action == "VERIFY STARTABLE CAPACITY"
    assert result.generator_set == "NONE"
    assert result.recommended_capacity_mw == 0.0


def test_risk_backtest_is_chronological_and_reports_calibration():
    base = datetime(2026, 6, 1, 0)
    samples = (
        RiskBacktestSample(
            base + timedelta(hours=2),
            base + timedelta(hours=3),
            0.8,
            1100,
            1000,
        ),
        RiskBacktestSample(base, base + timedelta(hours=1), 0.2, 950, 1000),
        RiskBacktestSample(
            base + timedelta(hours=1),
            base + timedelta(hours=2),
            0.5,
            1000,
            1000,
        ),
    )

    result = RiskProbabilityEngine.chronological_backtest(samples)

    assert result.sample_count == 3
    assert result.first_target_timestamp == base + timedelta(hours=1)
    assert result.last_target_timestamp == base + timedelta(hours=3)
    assert result.event_rate == pytest.approx(1 / 3)
    assert result.mean_probability == pytest.approx(0.5)
    assert result.brier_score == pytest.approx((0.2**2 + 0.5**2 + 0.2**2) / 3)
    assert result.mean_calibration_error == pytest.approx(1 / 6)


def test_risk_backtest_rejects_forecasts_at_or_after_target_time():
    timestamp = datetime(2026, 6, 1, 12)

    with pytest.raises(ValueError, match="issued before"):
        RiskProbabilityEngine.chronological_backtest(
            (
                RiskBacktestSample(
                    timestamp,
                    timestamp,
                    0.5,
                    1000,
                    1000,
                ),
            )
        )
