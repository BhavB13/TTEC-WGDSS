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
        {
            **grid,
            "total_available_capacity_mw": 1040,
            "reserve_margin_percent": 15.6,
        },
    )
    high = engine.evaluate(
        {
            "temperature_c": 34,
            "humidity_percent": 85,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 10,
        },
        {
            **grid,
            "total_available_capacity_mw": 950,
            "reserve_margin_percent": 5.6,
        },
    )

    assert low["risk_level"] == "LOW"
    assert low["recommendation"] == "NO ACTION REQUIRED"
    assert medium["risk_level"] == "MEDIUM"
    assert medium["recommendation"] == "MONITOR CONDITIONS"
    assert high["risk_level"] == "HIGH"
    assert high["recommendation"] == "START HEAVY GENERATOR SET"


def test_historical_spin_profile_does_not_masquerade_as_live_grid_telemetry():
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

    assert low["probability_score"] == adequate["probability_score"]
    assert not any("spinning reserve" in factor for factor in low["factors"])


def test_scenario_profile_needs_a_followup_point_to_change_demand():
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

    no_followup = engine.evaluate(
        weather,
        grid,
        calibration={
            "selected_demand_mw": 1000,
            "selection_confidence": 1.0,
        },
    )
    rising_profile = engine.evaluate(
        weather,
        grid,
        calibration={
            "selected_demand_mw": 1000,
            "selected_next_demand_mw": 1100,
            "selection_confidence": 1.0,
        },
    )

    assert no_followup["forecast_demand_60m"] == 1000
    assert rising_profile["forecast_demand_60m"] == 1100


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
            "selected_next_demand_mw": 1320,
            "selection_confidence": 0.0,
        },
    )
    high_confidence = engine.evaluate(
        weather,
        grid,
        calibration={
            "selected_demand_mw": 1200,
            "selected_next_demand_mw": 1320,
            "selection_confidence": 1.0,
        },
    )

    assert low_confidence["forecast_demand_30m"] == 800
    assert high_confidence["forecast_demand_30m"] == 840


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
            "total_available_capacity_mw": 925,
            "reserve_margin_percent": 15.6,
        },
    )

    assert result["risk_level"] == "MEDIUM"
    assert result["recommendation"] == "MONITOR CONDITIONS"


def test_target_hour_weather_changes_fallback_demand_direction():
    engine = RecommendationEngine()
    weather = {
        "temperature_c": 29,
        "humidity_percent": 70,
        "rainfall_mm_hr": 0,
        "cloud_cover_percent": 30,
    }
    grid = {
        "current_demand_mw": 900,
        "current_generation_mw": 950,
        "total_available_capacity_mw": 1300,
        "reserve_margin_percent": 44.4,
    }

    warming = engine.evaluate(
        weather,
        grid,
        forecast_weather={
            "temperature_c": 32,
            "humidity_percent": 75,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 25,
            "confidence_score": 0.9,
        },
    )
    cooling = engine.evaluate(
        weather,
        grid,
        forecast_weather={
            "temperature_c": 27,
            "humidity_percent": 65,
            "rainfall_mm_hr": 3,
            "cloud_cover_percent": 70,
            "confidence_score": 0.9,
        },
    )

    assert warming["forecast_demand_60m"] > cooling["forecast_demand_60m"]
    assert "Forecast warming increases short-term cooling demand" in warming["factors"]
    assert "Forecast cooling reduces short-term cooling demand" in cooling["factors"]
