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
