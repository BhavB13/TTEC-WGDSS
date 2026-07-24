from __future__ import annotations

from datetime import datetime
from pathlib import Path

import joblib

from app.services.frozen_snapshot_model_service import FrozenSnapshotModelService
from app.models.demand_forecast import ForecastTrainingRow
from app.services.demand_forecast_model_service import (
    _ModelCandidate,
    _fit_feature_transform,
    _feature_vector,
)


class PredictOnlyEstimator:
    def predict(self, rows):
        return [rows[0][0] + 25.0]

    def fit(self, *_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("fit must not be called")


class CanonicalPredictOnlyEstimator:
    def predict(self, rows):
        return [rows[0][0]]

    def fit(self, *_args, **_kwargs):  # pragma: no cover - must never run
        raise AssertionError("fit must not be called")


def test_missing_artifact_fails_closed_without_refit(tmp_path: Path):
    service = FrozenSnapshotModelService(tmp_path / "missing.joblib")
    metadata, forecasts = service.predict([])
    assert metadata.status == "NO_FROZEN_MODEL_ARTIFACT"
    assert metadata.preprocessing_refit is False
    assert forecasts == []


def test_frozen_artifact_is_predict_only_and_excludes_snapshot(tmp_path: Path):
    path = tmp_path / "model.joblib"
    joblib.dump(
        {
            "schema_version": "wgdss-frozen-demand-model-v1",
            "model_name": "TestModel",
            "model_version": "test-v1",
            "feature_profile": "test",
            "training_start_at": "2025-10-01T00:00:00",
            "training_end_at": "2026-05-31T23:00:00",
            "snapshot_used_for_training": False,
            "feature_names": ["current_demand_mw"],
            "fill_values": {},
            "horizon_models": {
                1: {"pipeline": PredictOnlyEstimator(), "residual_std_mw": 10.0}
            },
        },
        path,
    )
    service = FrozenSnapshotModelService(path)
    metadata, forecasts = service.predict(
        [
            {
                "horizon_hours": 1,
                "forecast_timestamp": datetime(2026, 7, 23, 12),
                "input_quality": "GOOD",
                "features": {"current_demand_mw": 1200.0},
            }
        ]
    )
    assert metadata.status == "READY"
    assert metadata.snapshot_used_for_training is False
    assert metadata.preprocessing_refit is False
    assert forecasts[0].forecast_demand_mw == 1225.0


def test_v2_artifact_uses_frozen_transform_for_canonical_row(tmp_path: Path):
    row = ForecastTrainingRow(
        feature_timestamp=datetime(2026, 6, 1, 10),
        horizon_hours=1,
        target_timestamp=datetime(2026, 6, 1, 11),
        target_demand_mw=1010.0,
        current_demand_mw=1000.0,
        hour_of_day=10,
        day_of_week=0,
        source_quality_status="GOOD",
    )
    transform = _fit_feature_transform([row])
    expected = _feature_vector(row, transform)[0]
    path = tmp_path / "model-v2.joblib"
    joblib.dump(
        {
            "schema_version": "wgdss-frozen-demand-model-v2",
            "model_name": "Canonical test",
            "model_version": "test-v2",
            "feature_profile": "test",
            "training_start_at": "2025-10-01T00:00:00",
            "training_end_at": "2026-05-31T23:00:00",
            "snapshot_used_for_training": False,
            "horizon_models": {
                1: {
                    "estimator": CanonicalPredictOnlyEstimator(),
                    "scaler": None,
                    "transform": transform,
                    "candidate": _ModelCandidate(
                        candidate_id="test",
                        model_name="Test",
                        family="test",
                        params={},
                    ),
                    "validation_bias_mw": 0.0,
                    "residual_std_mw": 10.0,
                    "training_rows": [],
                }
            },
        },
        path,
    )

    metadata, forecasts = FrozenSnapshotModelService(path).predict_rows({1: row})

    assert metadata.status == "READY"
    assert forecasts[0].forecast_demand_mw == expected
    assert forecasts[0].forecast_timestamp == row.target_timestamp
