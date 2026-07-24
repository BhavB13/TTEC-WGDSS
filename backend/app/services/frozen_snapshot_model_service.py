from __future__ import annotations

import hashlib
from functools import lru_cache
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib

from app.core.config import settings
from app.schemas.live_scada_experiment import (
    ExperimentalForecastPoint,
    FrozenModelMetadata,
)
from app.services.demand_forecast_model_service import FEATURE_PROFILE, MODEL_VERSION
from app.models.demand_forecast import ForecastTrainingRow
from app.services.demand_forecast_model_service import (
    _feature_vector,
    _load_state_anchor,
)
from app.services.frozen_model_artifact_service import (
    ARTIFACT_SCHEMA as ARTIFACT_SCHEMA_V2,
)
from app.services.similar_period_service import similar_period_forecast


ARTIFACT_SCHEMA = "wgdss-frozen-demand-model-v1"
LATEST_ALLOWED_TRAINING_DATE = datetime.fromisoformat("2026-05-31T23:59:59")


class FrozenSnapshotModelService:
    """Inference-only adapter for a previously fitted, serialized pipeline."""

    def __init__(self, artifact_path: str | Path | None) -> None:
        self.artifact_path = Path(artifact_path) if artifact_path else None

    def metadata(self) -> FrozenModelMetadata:
        if self.artifact_path is None or not self.artifact_path.is_file():
            return FrozenModelMetadata(
                status="NO_FROZEN_MODEL_ARTIFACT",
                model_name="Existing WGDSS demand ensemble (metadata only)",
                model_version=MODEL_VERSION,
                feature_profile=FEATURE_PROFILE,
                training_start_at=datetime.fromisoformat(
                    settings.MODEL_TRAINING_START_DATE
                ),
                training_end_at=datetime.fromisoformat(
                    settings.MODEL_TRAINING_END_DATE
                ),
                warnings=[
                    "The repository contains model metadata but no serialized "
                    "fitted estimator. Snapshot inference is unavailable; no "
                    "training or preprocessing refit was performed."
                ],
            )
        artifact = self._load()
        training_end = _parse_datetime(artifact.get("training_end_at"))
        warnings: list[str] = []
        status = "READY"
        if artifact.get("schema_version") not in {ARTIFACT_SCHEMA, ARTIFACT_SCHEMA_V2}:
            status = "INVALID_ARTIFACT"
            warnings.append("Unsupported frozen-model artifact schema")
        if training_end is None or _naive(training_end) > LATEST_ALLOWED_TRAINING_DATE:
            status = "LEAKAGE_GUARD_FAILED"
            warnings.append("Training must end by May 31, 2026")
        if bool(artifact.get("snapshot_used_for_training")):
            status = "LEAKAGE_GUARD_FAILED"
            warnings.append("Artifact metadata says the snapshot entered training")
        return FrozenModelMetadata(
            status=status,
            model_name=artifact.get("model_name"),
            model_version=artifact.get("model_version"),
            feature_profile=artifact.get("feature_profile"),
            artifact_hash=_sha256_cached(
                str(self.artifact_path.resolve()),
                self.artifact_path.stat().st_mtime_ns,
            ),
            artifact_path=self.artifact_path.name,
            training_start_at=_parse_datetime(artifact.get("training_start_at")),
            training_end_at=training_end,
            training_row_count=(
                int(artifact["training_row_count"])
                if artifact.get("training_row_count") is not None
                else None
            ),
            snapshot_used_for_training=bool(
                artifact.get("snapshot_used_for_training", False)
            ),
            preprocessing_refit=False,
            warnings=warnings,
        )

    def predict(
        self,
        model_inputs: list[dict[str, object]],
    ) -> tuple[FrozenModelMetadata, list[ExperimentalForecastPoint]]:
        metadata = self.metadata()
        if metadata.status != "READY":
            return metadata, []
        artifact = self._load()
        feature_names = list(artifact.get("feature_names") or [])
        fill_values = dict(artifact.get("fill_values") or {})
        horizon_models = artifact.get("horizon_models") or {}
        forecasts: list[ExperimentalForecastPoint] = []
        for model_input in model_inputs:
            horizon = int(model_input["horizon_hours"])
            entry = horizon_models.get(horizon) or horizon_models.get(str(horizon))
            if not entry:
                metadata.warnings.append(f"No fitted model for +{horizon}h")
                continue
            estimator = entry.get("pipeline") if isinstance(entry, dict) else entry
            if estimator is None or not hasattr(estimator, "predict"):
                metadata.warnings.append(f"Invalid fitted model for +{horizon}h")
                continue
            features = model_input.get("features")
            if not isinstance(features, dict):
                continue
            vector = [
                float(features.get(name, fill_values.get(name, 0.0)))
                for name in feature_names
            ]
            # Deliberately call predict only. No fit, partial_fit, fit_transform,
            # or scaler mutation is permitted in this experiment.
            prediction = float(estimator.predict([vector])[0])
            sigma = float(
                entry.get("residual_std_mw", 0.0)
                if isinstance(entry, dict)
                else 0.0
            )
            forecasts.append(
                ExperimentalForecastPoint(
                    horizon_hours=horizon,
                    forecast_timestamp=model_input["forecast_timestamp"],
                    forecast_demand_mw=round(prediction, 2),
                    uncertainty_mw=round(sigma, 2),
                    lower_bound_mw=round(prediction - 1.645 * sigma, 2),
                    upper_bound_mw=round(prediction + 1.645 * sigma, 2),
                    model_name=metadata.model_name or "Frozen model",
                    model_version=metadata.model_version or "unknown",
                    status="MODEL_INFERENCE",
                    input_quality=str(model_input.get("input_quality", "UNKNOWN")),
                    reasons=["Frozen estimator inference; preprocessing was not refit"],
                )
            )
        return metadata, forecasts

    def predict_rows(
        self,
        inference_rows: dict[int, ForecastTrainingRow],
    ) -> tuple[FrozenModelMetadata, list[ExperimentalForecastPoint]]:
        """Run canonical-row inference without fitting or mutating preprocessing."""

        metadata = self.metadata()
        if metadata.status != "READY":
            return metadata, []
        artifact = self._load()
        if artifact.get("schema_version") != ARTIFACT_SCHEMA_V2:
            metadata.warnings.append("Canonical row inference requires v2 artifact")
            return metadata, []
        horizon_models = artifact.get("horizon_models") or {}
        forecasts: list[ExperimentalForecastPoint] = []
        for horizon, row in sorted(inference_rows.items()):
            entry = horizon_models.get(horizon) or horizon_models.get(str(horizon))
            if not isinstance(entry, dict):
                metadata.warnings.append(f"No fitted model for +{horizon}h")
                continue
            estimator = entry.get("estimator")
            transform = entry.get("transform")
            candidate = entry.get("candidate")
            training_rows = entry.get("training_rows") or []
            if estimator is None or transform is None or candidate is None:
                metadata.warnings.append(f"Incomplete fitted state for +{horizon}h")
                continue
            vector = [_feature_vector(row, transform)]
            scaler = entry.get("scaler")
            if scaler is not None:
                vector = scaler.transform(vector)
            prediction = float(estimator.predict(vector)[0])
            if candidate.target_mode == "load_state_residual":
                prediction += _load_state_anchor(row)
            if candidate.similarity_weight > 0:
                similarity = similar_period_forecast(
                    training_rows,
                    row,
                    extra_holiday_dates=settings.FORECAST_EXTRA_HOLIDAY_DATES,
                ).forecast_mw
                if similarity is not None:
                    prediction = (
                        (1.0 - candidate.similarity_weight) * prediction
                        + candidate.similarity_weight * similarity
                    )
            prediction = max(
                0.0,
                prediction + float(entry.get("validation_bias_mw", 0.0)),
            )
            sigma = max(0.0, float(entry.get("residual_std_mw", 0.0)))
            forecasts.append(
                ExperimentalForecastPoint(
                    horizon_hours=horizon,
                    forecast_timestamp=row.target_timestamp,
                    forecast_demand_mw=round(prediction, 2),
                    uncertainty_mw=round(sigma, 2),
                    lower_bound_mw=round(max(0.0, prediction - 1.645 * sigma), 2),
                    upper_bound_mw=round(prediction + 1.645 * sigma, 2),
                    model_name=metadata.model_name or "Frozen model",
                    model_version=metadata.model_version or "unknown",
                    status="MODEL_INFERENCE",
                    input_quality=row.source_quality_status,
                    reasons=[
                        "Frozen October-May estimator and preprocessing",
                        "No fit or preprocessing mutation during inference",
                    ],
                )
            )
        return metadata, forecasts

    def _load(self) -> dict[str, Any]:
        if self.artifact_path is None:
            raise FileNotFoundError("Frozen model artifact path is not configured")
        return _load_artifact(
            str(self.artifact_path.resolve()),
            self.artifact_path.stat().st_mtime_ns,
        )


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=8)
def _sha256_cached(path: str, _mtime_ns: int) -> str:
    return _sha256(Path(path))


@lru_cache(maxsize=4)
def _load_artifact(path: str, _mtime_ns: int) -> dict[str, Any]:
    artifact = joblib.load(path)
    if not isinstance(artifact, dict):
        raise ValueError("Frozen model artifact must be a dictionary")
    return artifact
