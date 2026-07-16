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


def test_risk_engine_uses_injected_configurable_operating_policy():
    policy = OperatingPolicy(
        status="TEST_UNCONFIRMED",
        reserve_fraction=0.10,
        medium_probability_threshold=0.20,
        high_probability_threshold=0.80,
        fast_start_unit_capacity_mw=10,
        fast_start_max_capacity_mw=20,
        fast_start_lead_time_minutes=15,
        heavy_start_min_capacity_mw=50,
        heavy_start_max_capacity_mw=100,
        heavy_start_lead_time_minutes=45,
    )
    result = RiskProbabilityEngine(policy=policy).evaluate(
        OperatingRiskInput(
            forecast_demand_mw=850,
            forecast_uncertainty_mw=25,
            current_demand_mw=830,
            online_capacity_mw=1100,
            available_capacity_mw=1250,
            spinning_reserve_mw=180,
        )
    )

    assert result.required_reserve_mw == 85
    assert result.policy_status == "TEST_UNCONFIRMED"
    assert any("test unconfirmed" in reason for reason in result.reasons)


def test_risk_engine_fails_closed_for_invalid_capacity_policy():
    policy = OperatingPolicy(
        status="TEST_INVALID",
        reserve_fraction=0.10,
        medium_probability_threshold=0.20,
        high_probability_threshold=0.80,
        fast_start_unit_capacity_mw=20,
        fast_start_max_capacity_mw=10,
        fast_start_lead_time_minutes=15,
        heavy_start_min_capacity_mw=100,
        heavy_start_max_capacity_mw=50,
        heavy_start_lead_time_minutes=45,
    )

    result = RiskProbabilityEngine(policy=policy).evaluate(
        OperatingRiskInput(
            forecast_demand_mw=850,
            forecast_uncertainty_mw=25,
            current_demand_mw=830,
            online_capacity_mw=1100,
            available_capacity_mw=1250,
            spinning_reserve_mw=180,
        )
    )

    assert result.risk_level == "UNAVAILABLE"
    assert result.recommendation == "DATA UNAVAILABLE"
    assert "fast-start maximum capacity" in result.reasons[0]
    assert "heavy-start maximum capacity" in result.reasons[0]


def test_risk_probability_low_when_forecast_is_below_safe_capacity():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=850,
            forecast_uncertainty_mw=25,
            current_demand_mw=830,
            online_capacity_mw=1100,
            available_capacity_mw=1250,
            spinning_reserve_mw=180,
        )
    )

    assert result.risk_level == "LOW"
    assert result.probability_score < 0.30
    assert result.recommendation == "NO ACTION REQUIRED"
    assert result.safe_online_capacity_mw == 882.5
    assert "Forecast demand remains within safe online capacity" in result.reasons
    assert any("TA could satisfy forecast demand" in reason for reason in result.reasons)


def test_risk_probability_preserves_a_small_nonzero_tail_probability():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=959,
            forecast_uncertainty_mw=20,
            current_demand_mw=950,
            online_capacity_mw=1200,
            available_capacity_mw=1200,
            spinning_reserve_mw=None,
        )
    )

    assert 0.0 < result.probability_score < 0.0001
    assert any("Safe online headroom" in reason for reason in result.reasons)
    assert any("Operating-risk probability is below 0.001%" in reason for reason in result.reasons)


def test_risk_probability_high_when_forecast_exceeds_safe_capacity():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=1040,
            forecast_uncertainty_mw=30,
            current_demand_mw=900,
            online_capacity_mw=1120,
            available_capacity_mw=1260,
            spinning_reserve_mw=80,
        )
    )

    assert result.risk_level == "HIGH"
    assert result.probability_score > 0.65
    assert result.recommendation == "START HEAVY GENERATOR SET"
    assert result.generator_set == "HEAVY 60-120 MW SET"
    assert result.startup_time_minutes == 60
    assert "Forecast demand exceeds safe online capacity" in result.reasons
    assert "Corrected spin is below the configured reserve requirement" in result.reasons
    assert any("TA could satisfy forecast demand" in reason for reason in result.reasons)


def test_risk_probability_medium_when_uncertainty_overlaps_reserve_boundary():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=955,
            forecast_uncertainty_mw=60,
            current_demand_mw=900,
            online_capacity_mw=1100,
            available_capacity_mw=1200,
            spinning_reserve_mw=250,
        )
    )

    assert result.risk_level == "MEDIUM"
    assert 0.30 <= result.probability_score <= 0.65
    assert result.recommendation == "MONITOR CONDITIONS"
    assert "Forecast uncertainty overlaps the operating reserve boundary" in result.reasons


def test_dispatch_selects_small_set_inside_twenty_minute_start_window():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=985,
            forecast_uncertainty_mw=5,
            current_demand_mw=950,
            online_capacity_mw=1120,
            available_capacity_mw=1200,
            spinning_reserve_mw=170,
            forecast_profile=(
                OperatingForecastPoint(
                    horizon_minutes=20,
                    forecast_demand_mw=985,
                    forecast_uncertainty_mw=5,
                    weather_effect_mw=12,
                    confidence=0.91,
                ),
            ),
        )
    )

    assert result.recommendation == "START BOTH 15 MW SMALL SETS"
    assert result.recommended_capacity_mw == 30
    assert result.startup_time_minutes == 20
    assert result.expected_rise_minutes == 20
    assert result.weather_effect_mw == 12


def test_dispatch_selects_one_fifteen_mw_set_for_small_shortfall():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=978,
            forecast_uncertainty_mw=5,
            current_demand_mw=950,
            online_capacity_mw=1120,
            available_capacity_mw=1200,
            spinning_reserve_mw=170,
            forecast_profile=(OperatingForecastPoint(20, 978, 5),),
        )
    )

    assert result.risk_level == "HIGH"
    assert result.recommendation == "START ONE 15 MW SMALL SET"
    assert result.generator_set == "1 x 15 MW FAST-START"
    assert result.recommended_capacity_mw == 15
    assert result.startup_time_minutes == 20


def test_dispatch_monitors_small_set_until_start_window():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=985,
            forecast_uncertainty_mw=5,
            current_demand_mw=950,
            online_capacity_mw=1120,
            available_capacity_mw=1200,
            spinning_reserve_mw=170,
            forecast_profile=(
                OperatingForecastPoint(45, 985, 5, confidence=0.88),
            ),
        )
    )

    assert result.recommendation == "MONITOR CONDITIONS"
    assert result.decision_action == "MONITOR SMALL-SET WINDOW"
    assert result.startup_time_minutes == 20


def test_dispatch_selects_heavy_set_for_large_one_hour_shortfall():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=1120,
            forecast_uncertainty_mw=20,
            current_demand_mw=950,
            online_capacity_mw=1150,
            available_capacity_mw=1250,
            spinning_reserve_mw=200,
            forecast_profile=(
                OperatingForecastPoint(
                    60,
                    1120,
                    20,
                    weather_effect_mw=35,
                    confidence=0.85,
                ),
            ),
        )
    )

    assert result.recommendation == "START HEAVY GENERATOR SET"
    assert 60 <= result.recommended_capacity_mw <= 120
    assert result.startup_time_minutes == 60
    assert result.projected_shortfall_mw > 30


def test_dispatch_does_not_claim_heavy_set_without_ta_headroom():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=1100,
            forecast_uncertainty_mw=15,
            current_demand_mw=950,
            online_capacity_mw=1100,
            available_capacity_mw=1120,
            spinning_reserve_mw=150,
            forecast_profile=(OperatingForecastPoint(60, 1100, 15),),
        )
    )

    assert result.risk_level == "HIGH"
    assert result.generator_set == "1 x 15 MW FAST-START"
    assert result.recommended_capacity_mw == 15
    assert result.residual_shortfall_mw > 0
    assert result.decision_action == "ESCALATE CAPACITY AVAILABILITY"


def test_risk_probability_fails_safely_when_inputs_are_missing():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=None,
            forecast_uncertainty_mw=30,
            current_demand_mw=900,
            online_capacity_mw=None,
            available_capacity_mw=1200,
            spinning_reserve_mw=150,
        )
    )

    assert result.risk_level == "UNAVAILABLE"
    assert result.probability_score == 0.0
    assert result.recommendation == "DATA UNAVAILABLE"
    assert "invalid or missing forecast_demand_mw, online_capacity_mw" in result.reasons[0]


def test_risk_probability_unavailable_without_online_capacity():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=940,
            forecast_uncertainty_mw=25,
            current_demand_mw=900,
            online_capacity_mw=None,
            available_capacity_mw=1200,
            spinning_reserve_mw=150,
        )
    )

    assert result.risk_level == "UNAVAILABLE"
    assert result.probability_score == 0.0
    assert result.recommendation == "DATA UNAVAILABLE"
    assert "invalid or missing online_capacity_mw" in result.reasons[0]


def test_risk_probability_rejects_invalid_numeric_inputs():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=-1,
            forecast_uncertainty_mw=float("nan"),
            current_demand_mw=0,
            online_capacity_mw=-10,
            available_capacity_mw=-5,
            spinning_reserve_mw=-1,
        )
    )

    assert result.risk_level == "UNAVAILABLE"
    assert result.recommendation == "DATA UNAVAILABLE"
    assert "nonnegative forecast_demand_mw" in result.reasons[0]
    assert "positive current_demand_mw" in result.reasons[0]
    assert "positive online_capacity_mw" in result.reasons[0]
    assert "nonnegative available_capacity_mw" in result.reasons[0]
    assert "nonnegative spinning_reserve_mw" in result.reasons[0]


def test_risk_probability_uses_valid_fallback_uncertainty():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=850,
            forecast_uncertainty_mw=float("nan"),
            fallback_uncertainty_mw=40,
            current_demand_mw=830,
            online_capacity_mw=1100,
            available_capacity_mw=1250,
            spinning_reserve_mw=180,
        )
    )

    assert result.risk_level != "UNAVAILABLE"
    assert result.forecast_uncertainty_mw == 40


def test_risk_probability_scales_reserve_to_higher_forecast_demand():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=1000,
            forecast_uncertainty_mw=25,
            current_demand_mw=800,
            online_capacity_mw=1200,
            available_capacity_mw=1300,
            spinning_reserve_mw=400,
        )
    )

    assert result.required_reserve_mw == 150
    assert result.safe_online_capacity_mw == 1050


def test_risk_probability_rejects_inconsistent_capacity_state():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=900,
            forecast_uncertainty_mw=25,
            current_demand_mw=950,
            online_capacity_mw=900,
            available_capacity_mw=850,
            spinning_reserve_mw=100,
        )
    )

    assert result.risk_level == "UNAVAILABLE"
    assert "current_demand_mw not above online_capacity_mw" in result.reasons[0]
    assert "available_capacity_mw not below online_capacity_mw" in result.reasons[0]


def test_risk_probability_increases_monotonically_with_forecast_demand():
    engine = RiskProbabilityEngine()
    scores = [
        engine.evaluate(
            OperatingRiskInput(
                forecast_demand_mw=forecast,
                forecast_uncertainty_mw=30,
                current_demand_mw=800,
                online_capacity_mw=1200,
                available_capacity_mw=1300,
                spinning_reserve_mw=400,
            )
        ).probability_score
        for forecast in (800, 900, 1000, 1100)
    ]

    assert scores == sorted(scores)
    assert scores[-1] > scores[0]


def test_risk_probability_decreases_with_more_spinning_headroom():
    engine = RiskProbabilityEngine()
    scores = [
        engine.evaluate(
            OperatingRiskInput(
                forecast_demand_mw=900,
                forecast_uncertainty_mw=30,
                current_demand_mw=800,
                online_capacity_mw=1200,
                available_capacity_mw=1300,
                spinning_reserve_mw=spinning_reserve,
            )
        ).probability_score
        for spinning_reserve in (150, 250, 400)
    ]

    assert scores == sorted(scores, reverse=True)


def test_risk_probability_is_half_at_the_operating_boundary():
    boundary_demand = 1200 / 1.15
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=boundary_demand,
            forecast_uncertainty_mw=30,
            current_demand_mw=800,
            online_capacity_mw=1200,
            available_capacity_mw=1300,
            spinning_reserve_mw=400,
        )
    )

    assert result.probability_score == 0.5


def test_risk_probability_returns_calibrated_intermediate_values():
    engine = RiskProbabilityEngine()
    uncertainty = 30.0

    def demand_for_probability(probability: float) -> float:
        z_score = NormalDist().inv_cdf(1.0 - probability)
        return (1200.0 - z_score * uncertainty) / 1.15

    results = [
        engine.evaluate(
            OperatingRiskInput(
                forecast_demand_mw=demand_for_probability(probability),
                forecast_uncertainty_mw=uncertainty,
                current_demand_mw=800,
                online_capacity_mw=1200,
                available_capacity_mw=1300,
                spinning_reserve_mw=400,
            )
        )
        for probability in (0.20, 0.50, 0.80)
    ]

    assert [result.probability_score for result in results] == pytest.approx(
        [0.20, 0.50, 0.80],
        abs=1e-12,
    )


def test_small_capacity_crossing_remains_near_fifty_percent_not_one_hundred():
    boundary_demand = 1200 / 1.15
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=boundary_demand + 1.0,
            forecast_uncertainty_mw=30,
            current_demand_mw=800,
            online_capacity_mw=1200,
            available_capacity_mw=1300,
            spinning_reserve_mw=400,
        )
    )

    assert 0.50 < result.probability_score < 0.53
    assert result.probability_score != 1.0


def test_horizon_profile_exposes_uncertainty_headroom_and_peak_deadline():
    reference = datetime(2026, 6, 15, 10)
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=980,
            forecast_uncertainty_mw=30,
            current_demand_mw=900,
            online_capacity_mw=1200,
            available_capacity_mw=1320,
            spinning_reserve_mw=300,
            forecast_profile=(
                OperatingForecastPoint(
                    60,
                    940,
                    30,
                    confidence=0.9,
                    forecast_timestamp=reference + timedelta(hours=1),
                ),
                OperatingForecastPoint(
                    120,
                    1000,
                    30,
                    confidence=0.85,
                    forecast_timestamp=reference + timedelta(hours=2),
                ),
                OperatingForecastPoint(
                    360,
                    1060,
                    35,
                    confidence=0.8,
                    forecast_timestamp=reference + timedelta(hours=6),
                ),
            ),
        )
    )

    assert [point.horizon_minutes for point in result.risk_profile] == [60, 120, 360]
    assert result.peak_risk_horizon_minutes == 360
    assert result.peak_risk_timestamp == reference + timedelta(hours=6)
    assert result.risk_profile[-1].forecast_lower_mw < 1060
    assert result.risk_profile[-1].forecast_upper_mw > 1060
    assert result.risk_profile[-1].online_headroom_mw == 140
    assert result.risk_profile[-1].reserve_adjusted_headroom_mw < 0
    assert result.risk_profile[-1].expected_shortfall_mw > 0
    assert result.risk_profile[-1].conservative_shortfall_mw > 0
    assert result.decision_deadline_at == reference + timedelta(hours=5)
    assert result.decision_deadline_minutes == 300


def test_risk_profile_is_monotonic_for_rising_forecast_at_fixed_uncertainty():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=900,
            forecast_uncertainty_mw=35,
            current_demand_mw=850,
            online_capacity_mw=1200,
            available_capacity_mw=1300,
            spinning_reserve_mw=350,
            forecast_profile=tuple(
                OperatingForecastPoint(horizon, demand, 35)
                for horizon, demand in ((60, 900), (120, 960), (360, 1020))
            ),
        )
    )

    probabilities = [point.probability for point in result.risk_profile]
    assert probabilities == sorted(probabilities)


def test_explicit_prediction_interval_can_supply_missing_standard_deviation():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=1000,
            forecast_uncertainty_mw=None,
            current_demand_mw=850,
            online_capacity_mw=1200,
            available_capacity_mw=1300,
            spinning_reserve_mw=350,
            forecast_profile=(
                OperatingForecastPoint(
                    60,
                    1000,
                    0,
                    confidence_lower_mw=950,
                    confidence_upper_mw=1050,
                    confidence_level=0.90,
                ),
            ),
        )
    )

    assert result.risk_level != "UNAVAILABLE"
    assert result.forecast_uncertainty_mw == pytest.approx(
        100 / (2 * NormalDist().inv_cdf(0.95))
    )


def test_invalid_prediction_interval_falls_back_to_residual_uncertainty():
    result = RiskProbabilityEngine().evaluate(
        OperatingRiskInput(
            forecast_demand_mw=1000,
            forecast_uncertainty_mw=30,
            current_demand_mw=850,
            online_capacity_mw=1200,
            available_capacity_mw=1300,
            spinning_reserve_mw=350,
            forecast_profile=(
                OperatingForecastPoint(
                    60,
                    1000,
                    30,
                    confidence_lower_mw=1020,
                    confidence_upper_mw=1030,
                    confidence_level=0.90,
                ),
            ),
        )
    )

    expected_delta = NormalDist().inv_cdf(0.95) * 30
    assert result.forecast_lower_mw == pytest.approx(1000 - expected_delta)
    assert result.forecast_upper_mw == pytest.approx(1000 + expected_delta)


def test_risk_backtest_is_chronological_and_reports_probability_calibration():
    base = datetime(2026, 6, 1, 0)
    samples = (
        RiskBacktestSample(base + timedelta(hours=2), base + timedelta(hours=3), 0.8, 1100, 1000),
        RiskBacktestSample(base, base + timedelta(hours=1), 0.2, 950, 1000),
        RiskBacktestSample(base + timedelta(hours=1), base + timedelta(hours=2), 0.5, 1000, 1000),
    )

    result = RiskProbabilityEngine.chronological_backtest(samples)

    assert result.sample_count == 3
    assert result.first_target_timestamp == base + timedelta(hours=1)
    assert result.last_target_timestamp == base + timedelta(hours=3)
    assert result.event_rate == pytest.approx(1 / 3)
    assert result.mean_probability == pytest.approx(0.5)
    assert result.brier_score == pytest.approx((0.2**2 + 0.5**2 + 0.2**2) / 3)
    assert result.mean_calibration_error == pytest.approx(1 / 6)


def test_risk_backtest_rejects_forecasts_issued_at_or_after_target_time():
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
