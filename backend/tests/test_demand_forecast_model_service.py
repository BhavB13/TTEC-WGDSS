from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.demand_forecast import DemandForecastResult, ForecastTrainingRow
from app.models.forecast import Forecast
from app.models.scada import ScadaGridSnapshot
from app.models.weather import Weather
from app.services.demand_forecast_baselines import (
    hourly_average_forecast,
    hourly_average_lookup,
)
from app.services.demand_forecast_model_service import (
    DemandForecastModelService,
    _feature_fill_values,
    _feature_vector,
    _training_sample_weights,
)


def _session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed_training_rows(
    session_factory,
    count: int = 30,
    horizon_hours: int = 1,
) -> None:
    start = datetime(2026, 6, 1, 0)
    with session_factory() as session:
        for index in range(count):
            feature_timestamp = start + timedelta(hours=index)
            current_demand = 800 + index * 5
            session.add(
                ForecastTrainingRow(
                    feature_timestamp=feature_timestamp,
                    horizon_hours=horizon_hours,
                    target_timestamp=feature_timestamp + timedelta(hours=horizon_hours),
                    target_demand_mw=current_demand + 8,
                    current_demand_mw=current_demand,
                    lag_1h_demand_mw=current_demand - 5 if index >= 1 else None,
                    lag_2h_demand_mw=current_demand - 10 if index >= 2 else None,
                    lag_24h_demand_mw=current_demand - 120 if index >= 24 else None,
                    rolling_3h_demand_mw=current_demand - 5 if index >= 2 else current_demand,
                    rolling_6h_demand_mw=current_demand - 12 if index >= 5 else current_demand,
                    hour_of_day=feature_timestamp.hour,
                    day_of_week=feature_timestamp.weekday(),
                    temperature_c=28 + (index % 6) * 0.2,
                    humidity_percent=70,
                    rainfall_mm_hr=0.1,
                    cloud_cover_percent=45,
                    wind_speed_kmh=12,
                    forecast_temperature_c=29,
                    forecast_rainfall_mm_hr=0.2,
                    forecast_cloud_cover_percent=50,
                    source_quality_status="GOOD",
                )
            )
        session.commit()


def test_demand_forecast_model_service_uses_chronological_baseline_and_persists(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory)

    result = DemandForecastModelService(session_factory=session_factory).train_and_store()

    assert len(result.results) == 1
    horizon = result.results[0]
    assert horizon.horizon_hours == 1
    assert horizon.train_rows == 24
    assert horizon.test_rows == 6
    assert horizon.mode in {"BASELINE_ACTIVE", "ML_ACTIVE"}
    assert horizon.best_baseline in {
        "persistence",
        "trend_adjusted_persistence",
        "rolling_trend",
        "same_hour_yesterday",
        "hourly_average",
    }
    assert horizon.forecast_uncertainty_mw > 0
    assert horizon.metrics.mae >= 0
    assert horizon.forecast_timestamp == datetime(2026, 6, 2, 6)

    with session_factory() as session:
        stored = session.scalar(select(DemandForecastResult))
        assert session.scalar(select(func.count(DemandForecastResult.id))) == 1

    assert stored is not None
    assert stored.horizon_hours == 1
    assert stored.forecast_demand_mw == horizon.forecast_demand_mw
    assert stored.forecast_uncertainty_mw == horizon.forecast_uncertainty_mw
    assert stored.feature_profile == "demand_weather_v2_1"
    assert stored.validation_status == "PROTOTYPE"
    assert stored.train_row_count == horizon.train_rows
    assert stored.test_row_count == horizon.test_rows
    assert json.loads(stored.candidate_metrics)["active"]["model"] == horizon.active_model


def test_demand_forecast_model_service_replaces_results(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory)
    service = DemandForecastModelService(session_factory=session_factory)

    first = service.train_and_store()
    second = service.train_and_store()

    assert len(first.results) == 1
    assert len(second.results) == 1
    with session_factory() as session:
        assert session.scalar(select(func.count(DemandForecastResult.id))) == 1


def test_demand_forecast_model_service_handles_multiple_horizons(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, horizon_hours=1)
    _seed_training_rows(session_factory, horizon_hours=2)

    result = DemandForecastModelService(session_factory=session_factory).train_and_store()

    assert [item.horizon_hours for item in result.results] == [1, 2]
    with session_factory() as session:
        assert session.scalar(select(func.count(DemandForecastResult.id))) == 2


def test_demand_forecast_model_keeps_baseline_when_ml_loses(monkeypatch, tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=30)
    service = DemandForecastModelService(session_factory=session_factory)

    def bad_ml_predictions(train_rows, test_rows):
        return [0.0 for _ in test_rows], 0.0

    monkeypatch.setattr(service, "_try_ml_model", bad_ml_predictions)

    result = service.train_and_store()

    assert len(result.results) == 1
    horizon = result.results[0]
    assert horizon.mode == "BASELINE_ACTIVE"
    assert horizon.active_model == horizon.best_baseline
    assert horizon.ml_beats_baseline is False

    with session_factory() as session:
        stored = session.scalar(select(DemandForecastResult))
    assert stored is not None
    assert stored.quality_status == "BASELINE_ACTIVE"
    assert stored.ml_beats_baseline is False


def test_model_compares_ridge_boosting_and_forest_chronologically(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=72, horizon_hours=6)

    result = DemandForecastModelService(
        session_factory=session_factory
    ).train_and_store()

    assert len(result.results) == 1
    horizon = result.results[0]
    assert horizon.horizon_hours == 6
    assert horizon.candidate_metrics is not None
    assert {
        "ridge_alpha_10",
        "hist_gradient_boosting",
        "random_forest",
    }.issubset(horizon.candidate_metrics)
    selected = [
        metrics
        for name, metrics in horizon.candidate_metrics.items()
        if name not in {"active", "baseline"} and metrics["selected"] is True
    ]
    assert len(selected) == 1
    assert all(
        horizon.candidate_metrics[name]["validation_mae"] >= 0
        for name in (
            "ridge_alpha_10",
            "hist_gradient_boosting",
            "random_forest",
        )
    )


def test_demand_forecast_model_sorts_rows_chronologically_before_split(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=12)
    with session_factory() as session:
        rows = session.scalars(
            select(ForecastTrainingRow).order_by(ForecastTrainingRow.feature_timestamp)
        ).all()

    shuffled_rows = list(reversed(rows))
    results = DemandForecastModelService(session_factory=session_factory).evaluate_rows(
        shuffled_rows
    )

    assert len(results) == 1
    horizon = results[0]
    assert horizon.train_rows == 9
    assert horizon.test_rows == 3
    assert horizon.forecast_timestamp == datetime(2026, 6, 1, 12)


def test_demand_forecast_uncertainty_uses_operating_floor_for_smooth_data(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=12, horizon_hours=6)

    result = DemandForecastModelService(session_factory=session_factory).train_and_store()

    assert len(result.results) == 1
    horizon = result.results[0]
    demand_floor = horizon.forecast_demand_mw * 0.015
    assert horizon.forecast_uncertainty_mw >= demand_floor
    assert horizon.forecast_uncertainty_mw >= 5.0


def test_demand_forecast_corrects_systematic_baseline_bias(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=20, horizon_hours=1)

    result = DemandForecastModelService(session_factory=session_factory).train_and_store()

    assert len(result.results) == 1
    horizon = result.results[0]
    assert horizon.metrics.mae == 0
    assert horizon.metrics.rmse == 0
    assert horizon.forecast_demand_mw == 903


def test_hourly_average_baseline_uses_target_hour_not_feature_hour(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=26, horizon_hours=6)
    with session_factory() as session:
        rows = session.scalars(
            select(ForecastTrainingRow).order_by(ForecastTrainingRow.feature_timestamp)
        ).all()

    lookup = hourly_average_lookup(rows[:24])
    test_row = rows[24]

    assert test_row.feature_timestamp.hour == 0
    assert test_row.target_timestamp.hour == 6
    assert hourly_average_forecast(test_row, lookup) == lookup[6]


def test_model_excludes_bad_scada_targets_but_keeps_weather_degraded_rows(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=12)
    with session_factory() as session:
        rows = session.scalars(
            select(ForecastTrainingRow).order_by(ForecastTrainingRow.feature_timestamp)
        ).all()
        rows[0].source_quality_status = "SCADA_DEGRADED"
        rows[1].source_quality_status = "WEATHER_DEGRADED"
        session.commit()
        detached_rows = list(rows)

    result = DemandForecastModelService(session_factory=session_factory).evaluate_rows(
        detached_rows
    )

    assert len(result) == 1
    assert result[0].train_rows + result[0].test_rows == 11


def test_model_refits_selected_baseline_for_future_inference(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=30)
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ForecastTrainingRow).order_by(
                    ForecastTrainingRow.feature_timestamp
                )
            )
        )

    feature_timestamp = datetime(2026, 6, 2, 6)
    inference_row = ForecastTrainingRow(
        feature_timestamp=feature_timestamp,
        horizon_hours=1,
        target_timestamp=feature_timestamp + timedelta(hours=1),
        target_demand_mw=1200,
        current_demand_mw=1200,
        lag_1h_demand_mw=1195,
        lag_2h_demand_mw=1190,
        lag_24h_demand_mw=1080,
        rolling_3h_demand_mw=1195,
        rolling_6h_demand_mw=1188,
        hour_of_day=feature_timestamp.hour,
        day_of_week=feature_timestamp.weekday(),
        temperature_c=31,
        humidity_percent=75,
        rainfall_mm_hr=0,
        cloud_cover_percent=30,
        wind_speed_kmh=15,
        forecast_temperature_c=32,
        forecast_rainfall_mm_hr=0,
        forecast_cloud_cover_percent=25,
        source_quality_status="GOOD",
    )

    result = DemandForecastModelService(
        session_factory=session_factory
    ).evaluate_rows(rows, inference_rows={1: inference_row})

    assert len(result) == 1
    assert result[0].forecast_timestamp == inference_row.target_timestamp
    assert result[0].forecast_demand_mw > 1000
    assert result[0].baseline_forecast_mw > 1000


def test_train_and_store_persists_future_inference_when_live_features_exist(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=30)
    start = datetime(2026, 6, 1, 0)
    with session_factory() as session:
        for index in range(30):
            timestamp = start + timedelta(hours=index)
            demand = 800 + index * 5
            session.add(
                ScadaGridSnapshot(
                    timestamp=timestamp,
                    current_demand_mw=demand,
                    temperature_c=29,
                    spinning_reserve_mw=180,
                    available_capacity_mw=1300,
                    online_capacity_mw=1200,
                    reserve_margin_mw=1300 - demand,
                    reserve_margin_percent=(1300 - demand) / demand * 100,
                    online_spare_mw=1200 - demand,
                    quality_status="GOOD",
                    missing_fields="",
                    source="test.csv",
                )
            )
        latest_timestamp = start + timedelta(hours=29)
        session.add(
            Weather(
                timestamp=latest_timestamp,
                temperature_c=30,
                humidity_percent=75,
                wind_speed_kph=15,
                wind_direction_deg=90,
                pressure_hpa=1012,
                precipitation_mm=0,
                rainfall_mm_hr=0,
                cloud_cover_percent=35,
                weather_condition="Clear",
                heat_index_c=32,
                rain_severity="DRY",
                provider_name="TestWeather",
                created_at=latest_timestamp,
            )
        )
        session.add(
            Forecast(
                forecast_timestamp=latest_timestamp + timedelta(hours=1),
                temperature_c=31,
                humidity_percent=74,
                rainfall_mm_hr=0,
                cloud_cover_percent=30,
                wind_speed_kph=16,
                wind_direction_deg=95,
                precipitation_probability_percent=10,
                precipitation_mm=0,
                weather_condition="Clear",
                heat_index_c=33,
                rain_severity="DRY",
                confidence_score=0.9,
                provider_name="TestForecast",
                created_at=latest_timestamp,
            )
        )
        session.commit()

    result = DemandForecastModelService(
        session_factory=session_factory
    ).train_and_store()

    assert len(result.results) == 1
    assert result.results[0].forecast_timestamp == latest_timestamp + timedelta(hours=1)
    with session_factory() as session:
        stored = session.scalar(select(DemandForecastResult))
    assert stored is not None
    assert stored.forecast_timestamp > latest_timestamp


def test_degraded_inference_is_flagged_and_receives_wider_uncertainty(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=30)
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ForecastTrainingRow).order_by(
                    ForecastTrainingRow.feature_timestamp
                )
            )
        )

    feature_timestamp = datetime(2026, 6, 2, 6)
    base_values = dict(
        feature_timestamp=feature_timestamp,
        horizon_hours=1,
        target_timestamp=feature_timestamp + timedelta(hours=1),
        target_demand_mw=950,
        current_demand_mw=950,
        lag_1h_demand_mw=945,
        lag_2h_demand_mw=940,
        lag_24h_demand_mw=830,
        rolling_3h_demand_mw=945,
        rolling_6h_demand_mw=938,
        hour_of_day=feature_timestamp.hour,
        day_of_week=feature_timestamp.weekday(),
        temperature_c=30,
        humidity_percent=70,
        rainfall_mm_hr=0,
        cloud_cover_percent=35,
        wind_speed_kmh=15,
        forecast_temperature_c=None,
        forecast_rainfall_mm_hr=None,
        forecast_cloud_cover_percent=None,
    )
    good = ForecastTrainingRow(source_quality_status="GOOD", **base_values)
    degraded = ForecastTrainingRow(
        source_quality_status="WEATHER_DEGRADED",
        **base_values,
    )
    service = DemandForecastModelService(session_factory=session_factory)

    good_result = service.evaluate_rows(rows, inference_rows={1: good})[0]
    degraded_result = service.evaluate_rows(rows, inference_rows={1: degraded})[0]

    assert degraded_result.mode == "BASELINE_ACTIVE_DEGRADED"
    assert degraded_result.forecast_uncertainty_mw == round(
        good_result.forecast_uncertainty_mw * 1.25,
        4,
    )


def test_ml_sample_weights_favor_recent_complete_rows(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=3)
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ForecastTrainingRow).order_by(
                    ForecastTrainingRow.feature_timestamp
                )
            )
        )
        rows[-1].source_quality_status = "WEATHER_DEGRADED"
        session.commit()

    weights = _training_sample_weights(rows)

    assert weights[1] > weights[0]
    assert weights[2] < weights[1]
    assert round(sum(weights) / len(weights), 10) == 1.0


def test_ml_feature_vector_excludes_scada_generation_context(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=3)
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ForecastTrainingRow).order_by(
                    ForecastTrainingRow.feature_timestamp
                )
            )
        )
        rows[0].spinning_reserve_mw = 150
        rows[0].available_capacity_mw = 1200
        rows[0].online_capacity_mw = 1000
        rows[0].reserve_margin_mw = 240
        rows[0].online_spare_mw = 40
        session.commit()

    fill_values = _feature_fill_values(rows)
    with_generation_context = _feature_vector(rows[0], fill_values)
    rows[0].online_capacity_mw = 0
    rows[0].available_capacity_mw = 0
    rows[0].spinning_reserve_mw = 0
    rows[0].reserve_margin_mw = 0
    rows[0].online_spare_mw = 0
    without_generation_context = _feature_vector(rows[0], fill_values)

    assert len(with_generation_context) == len(without_generation_context)
    assert with_generation_context == without_generation_context


def test_ml_feature_vector_responds_to_known_and_forecast_weather(tmp_path):
    session_factory = _session_factory(tmp_path)
    _seed_training_rows(session_factory, count=3)
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ForecastTrainingRow).order_by(
                    ForecastTrainingRow.feature_timestamp
                )
            )
        )

    fill_values = _feature_fill_values(rows)
    normal_weather = _feature_vector(rows[0], fill_values)
    rows[0].temperature_c = 34
    rows[0].humidity_percent = 90
    rows[0].rainfall_mm_hr = 8
    rows[0].forecast_temperature_c = 35
    rows[0].forecast_humidity_percent = 92
    rows[0].forecast_rainfall_mm_hr = 12
    rows[0].forecast_cloud_cover_percent = 100
    adverse_weather = _feature_vector(rows[0], fill_values)

    assert len(normal_weather) == len(adverse_weather)
    assert normal_weather != adverse_weather
