from app.services.recommendation_engine import RecommendationEngine


def test_probability_thresholds_produce_low_medium_and_high_actions():
    engine = RecommendationEngine()
    grid = {
        "current_demand_mw": 900,
        "current_generation_mw": 950,
        "total_available_capacity_mw": 1200,
        "reserve_margin_percent": 35,
    }

    low = engine.evaluate(
        {
            "temperature_c": 27,
            "humidity_percent": 55,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 20,
        },
        grid,
    )
    medium = engine.evaluate(
        {
            "temperature_c": 31,
            "humidity_percent": 72,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 20,
        },
        {**grid, "reserve_margin_percent": 24},
    )
    high = engine.evaluate(
        {
            "temperature_c": 34,
            "humidity_percent": 85,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 10,
        },
        {**grid, "reserve_margin_percent": 10},
    )

    assert low["risk_level"] == "LOW"
    assert low["recommendation"] == "NO ACTION REQUIRED"
    assert medium["risk_level"] == "MEDIUM"
    assert medium["recommendation"] == "MONITOR CONDITIONS"
    assert high["risk_level"] == "HIGH"
    assert high["recommendation"] == "START ADDITIONAL TURBINE"


def test_low_spin_profile_only_adds_pressure_below_planning_threshold():
    engine = RecommendationEngine()
    weather = {
        "temperature_c": 28,
        "humidity_percent": 60,
        "rainfall_mm_hr": 0,
        "cloud_cover_percent": 30,
    }
    grid = {
        "current_demand_mw": 900,
        "current_generation_mw": 950,
        "total_available_capacity_mw": 1200,
        "reserve_margin_percent": 30,
    }

    adequate = engine.evaluate(
        weather,
        grid,
        calibration={"selected_demand_mw": 900, "selected_spin_mw": 180},
    )
    low = engine.evaluate(
        weather,
        grid,
        calibration={"selected_demand_mw": 900, "selected_spin_mw": 50},
    )

    assert low["probability_score"] > adequate["probability_score"]
    assert any("spinning reserve" in factor for factor in low["factors"])


def test_spin_threshold_is_inclusive_and_has_no_pressure_at_fifteen_percent():
    engine = RecommendationEngine()
    weather = {
        "temperature_c": 28,
        "humidity_percent": 60,
        "rainfall_mm_hr": 0,
        "cloud_cover_percent": 30,
    }
    grid = {
        "current_demand_mw": 1000,
        "current_generation_mw": 1050,
        "total_available_capacity_mw": 1300,
        "reserve_margin_percent": 30,
    }

    at_threshold = engine.evaluate(
        weather,
        grid,
        calibration={"selected_demand_mw": 1000, "selected_spin_mw": 150},
    )
    below_threshold = engine.evaluate(
        weather,
        grid,
        calibration={"selected_demand_mw": 1000, "selected_spin_mw": 149},
    )

    assert not any("spinning reserve" in factor for factor in at_threshold["factors"])
    assert any("spinning reserve" in factor for factor in below_threshold["factors"])


def test_live_temperature_takes_priority_over_historical_calibration():
    engine = RecommendationEngine()
    grid = {
        "current_demand_mw": 800,
        "current_generation_mw": 900,
        "total_available_capacity_mw": 1200,
        "reserve_margin_percent": 50,
    }
    result = engine.evaluate(
        {
            "temperature_c": 27,
            "humidity_percent": 50,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 20,
        },
        grid,
        calibration={"selected_temperature_c": 36},
    )

    assert not any("High temperature" in factor for factor in result["factors"])


def test_scenario_confidence_controls_forecast_blend():
    engine = RecommendationEngine()
    weather = {
        "temperature_c": 28,
        "humidity_percent": 60,
        "rainfall_mm_hr": 0,
        "cloud_cover_percent": 20,
    }
    grid = {
        "current_demand_mw": 800,
        "current_generation_mw": 900,
        "total_available_capacity_mw": 1200,
        "reserve_margin_percent": 50,
    }

    low_confidence = engine.evaluate(
        weather,
        grid,
        calibration={
            "selected_demand_mw": 1200,
            "selection_confidence": 0.0,
        },
    )
    high_confidence = engine.evaluate(
        weather,
        grid,
        calibration={
            "selected_demand_mw": 1200,
            "selection_confidence": 1.0,
        },
    )

    assert low_confidence["forecast_demand_30m"] == 800
    assert high_confidence["forecast_demand_30m"] == 1000


def test_low_score_with_reduced_reserve_still_requires_monitoring():
    engine = RecommendationEngine()
    result = engine.evaluate(
        {
            "temperature_c": 27,
            "humidity_percent": 50,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 20,
        },
        {
            "current_demand_mw": 800,
            "current_generation_mw": 900,
            "total_available_capacity_mw": 1000,
            "reserve_margin_percent": 24,
        },
    )

    assert result["risk_level"] == "MEDIUM"
    assert result["recommendation"] == "MONITOR CONDITIONS"
