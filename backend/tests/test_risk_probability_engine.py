from app.services.risk_probability_engine import OperatingRiskInput, RiskProbabilityEngine


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
    assert (
        "Available capacity can satisfy forecast demand and reserve requirement"
        in result.reasons
    )


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
            available_capacity_mw=1160,
            spinning_reserve_mw=80,
        )
    )

    assert result.risk_level == "HIGH"
    assert result.probability_score > 0.65
    assert (
        result.recommendation
        == "PREPARE ADDITIONAL GENERATION / START ADDITIONAL TURBINE"
    )
    assert "Forecast demand exceeds safe online capacity" in result.reasons
    assert "Spinning reserve is below the planning threshold" in result.reasons
    assert (
        "Forecast demand exceeds available capacity after reserve requirement"
        in result.reasons
    )


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
