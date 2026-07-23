from __future__ import annotations

from datetime import datetime
from pathlib import Path

import joblib

from app.services.frozen_snapshot_model_service import FrozenSnapshotModelService


class PredictOnlyEstimator:
    def predict(self, rows):
        return [rows[0][0] + 25.0]

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
