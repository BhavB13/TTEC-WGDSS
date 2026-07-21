from app.services.recommendation_engine import RecommendationEngine


def test_probability_thresholds_produce_low_medium_and_high_actions():
    engine = RecommendationEngine()
    grid = {
        "current_demand_mw": 900,
        "current_generation_mw": 1000,
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
        historical_validation_rmse_mw=20,
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
            "current_generation_mw": 940,
            "total_available_capacity_mw": 1040,
            "reserve_margin_percent": 15.6,
        },
        historical_validation_rmse_mw=20,
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
            "current_generation_mw": 910,
            "total_available_capacity_mw": 950,
            "reserve_margin_percent": 5.6,
        },
        historical_validation_rmse_mw=20,
    )

    assert low["risk_level"] == "LOW"
    assert low["capacity_status"] == "Normal"
    assert low["recommendation"] == "NO ACTION REQUIRED"
    assert medium["risk_level"] == "MEDIUM"
    assert medium["capacity_status"] == "Watch"
    assert medium["recommendation"] == "MONITOR CONDITIONS"
    assert high["risk_level"] == "HIGH"
    assert high["capacity_status"] == "Add Generation"
    assert high["recommendation"] == "PREPARE ADDITIONAL GENERATION"
    assert high["decision_action"] == "VERIFY STARTABLE CAPACITY"


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
        historical_validation_rmse_mw=20,
    )
    low = engine.evaluate(
        weather,
        grid,
        calibration={"selected_demand_mw": 900, "selected_spin_mw": 50},
        historical_validation_rmse_mw=20,
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
        historical_validation_rmse_mw=20,
    )
    rising_profile = engine.evaluate(
        weather,
        grid,
        calibration={
            "selected_demand_mw": 1000,
            "selected_next_demand_mw": 1100,
            "selection_confidence": 1.0,
        },
        historical_validation_rmse_mw=20,
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
        historical_validation_rmse_mw=20,
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
        historical_validation_rmse_mw=20,
    )
    high_confidence = engine.evaluate(
        weather,
        grid,
        calibration={
            "selected_demand_mw": 1200,
            "selected_next_demand_mw": 1320,
            "selection_confidence": 1.0,
        },
        historical_validation_rmse_mw=20,
    )

    assert low_confidence["forecast_demand_30m"] == 800
    assert high_confidence["forecast_demand_30m"] == 840


def test_total_available_capacity_does_not_masquerade_as_current_tra():
    engine = RecommendationEngine()
    weather = {
        "temperature_c": 27,
        "humidity_percent": 50,
        "rainfall_mm_hr": 0,
        "cloud_cover_percent": 20,
    }
    constrained_ta = engine.evaluate(
        weather,
        {
            "current_demand_mw": 800,
            "current_generation_mw": 900,
            "total_available_capacity_mw": 925,
            "reserve_margin_percent": 15.6,
        },
        historical_validation_rmse_mw=20,
    )
    ample_ta = engine.evaluate(
        weather,
        {
            "current_demand_mw": 800,
            "current_generation_mw": 900,
            "total_available_capacity_mw": 1300,
            "reserve_margin_percent": 62.5,
        },
        historical_validation_rmse_mw=20,
    )

    assert constrained_ta["forecast_tra_mw"] == 900
    assert constrained_ta["probability_score"] == ample_ta["probability_score"]
    assert constrained_ta["capacity_status"] == "Normal"


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
        historical_validation_rmse_mw=20,
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
        historical_validation_rmse_mw=20,
    )

    assert warming["forecast_demand_60m"] > cooling["forecast_demand_60m"]
    assert "Forecast warming increases short-term cooling demand" in warming["factors"]
    assert "Forecast cooling reduces short-term cooling demand" in cooling["factors"]


def test_missing_validated_error_preserves_forecast_but_inhibits_probability():
    result = RecommendationEngine().evaluate(
        {
            "temperature_c": 29,
            "humidity_percent": 70,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 30,
        },
        {
            "current_demand_mw": 900,
            "current_generation_mw": 950,
            "total_available_capacity_mw": 1200,
            "reserve_margin_percent": 33.3,
        },
        forecast_weather={
            "temperature_c": 32,
            "humidity_percent": 75,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 25,
            "confidence_score": 0.9,
        },
    )

    assert result["forecast_demand_60m"] > 900
    assert result["risk_level"] == "UNAVAILABLE"
    assert result["capacity_status"] == "Unavailable"
    assert result["recommendation"] == "DATA UNAVAILABLE"


def test_missing_ta_does_not_block_tra_based_capacity_risk():
    result = RecommendationEngine().evaluate(
        {
            "temperature_c": 29,
            "humidity_percent": 70,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 30,
        },
        {
            "current_demand_mw": 900,
            "current_generation_mw": 950,
            "total_available_capacity_mw": None,
            "reserve_margin_percent": None,
        },
        historical_validation_rmse_mw=20,
    )

    assert result["risk_level"] != "UNAVAILABLE"
    assert result["forecast_tra_mw"] == 950
    assert result["projected_reserve_mw"] == 50
    assert result["available_start_capacity_mw"] is None
