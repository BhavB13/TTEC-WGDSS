from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
from sqlalchemy import select

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.demand_forecast import DemandForecastResult, ForecastTrainingRow
from app.services.data_period_policy import DataPeriodPolicy
from app.services.demand_forecast_model_service import (
    FEATURE_PROFILE,
    MODEL_VERSION,
    DemandForecastModelService,
    _ModelCandidate,
    _fit_feature_transform,
    _fit_prepared_model,
    _median_residual,
    _prepare_model_data,
    _walk_forward_splits,
)

ARTIFACT_SCHEMA = "wgdss-frozen-demand-model-v2"


@dataclass(frozen=True)
class FrozenSimilarPeriodRow:
    horizon_hours: int
    feature_timestamp: datetime
    target_timestamp: datetime
    target_demand_mw: float
    temperature_c: float | None
    forecast_temperature_c: float | None
    humidity_percent: float | None
    forecast_rainfall_mm_hr: float | None
    forecast_cloud_cover_percent: float | None
    current_demand_mw: float
    demand_rate_1h_mw: float | None


class FrozenModelArtifactService:
    """Offline exporter for the selected October-May direct-horizon models."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory
        self.period_policy = DataPeriodPolicy.from_settings()
        self.model_service = DemandForecastModelService(
            session_factory=session_factory,
            enforce_period_policy=True,
        )

    def export(self, output_path: str | Path) -> dict[str, object]:
        rows = self._training_rows()
        if not rows:
            raise ValueError("No October-May forecast training rows are available")
        if any(
            not self.period_policy.is_training_timestamp(row.feature_timestamp)
            or not self.period_policy.is_training_timestamp(row.target_timestamp)
            for row in rows
        ):
            raise ValueError("Frozen artifact input contains rows outside training policy")

        releases = self._released_results()
        horizon_models: dict[int, dict[str, Any]] = {}
        for horizon in sorted({row.horizon_hours for row in rows}):
            horizon_rows = [
                row
                for row in rows
                if row.horizon_hours == horizon
                and row.source_quality_status.upper()
                not in {"SCADA_DEGRADED", "BAD", "INACTIVE"}
            ]
            result = releases.get(horizon)
            if result is None or not result.quality_status.startswith("ML_ACTIVE"):
                continue
            metrics = json.loads(result.candidate_metrics or "{}")
            selected_id = next(
                (
                    key
                    for key, value in metrics.items()
                    if isinstance(value, dict)
                    and value.get("selected")
                    and not key.startswith("baseline_")
                ),
                None,
            )
            selected_metrics = metrics.get(selected_id, {}) if selected_id else {}
            base = next(
                (
                    candidate
                    for candidate in self.model_service._model_candidates(20)
                    if selected_id == candidate.candidate_id
                    or (selected_id or "").startswith(candidate.candidate_id + "_similarity_")
                ),
                None,
            )
            if base is None:
                continue
            candidate = _ModelCandidate(
                candidate_id=selected_id,
                model_name=str(selected_metrics.get("model", result.model_name)),
                family=base.family,
                params=base.params,
                similarity_weight=float(selected_metrics.get("similarity_weight", 0.0)),
                target_mode=str(selected_metrics.get("target_mode", base.target_mode)),
            )
            folds = _walk_forward_splits(horizon_rows[: max(1, int(len(horizon_rows) * 0.8))])
            actual, raw = self.model_service._walk_forward_candidate_predictions(
                candidate,
                folds,
            )
            similarity = self.model_service._walk_forward_similarity_values(folds)
            blended = [
                (1.0 - candidate.similarity_weight) * model
                + candidate.similarity_weight * (similar if similar is not None else model)
                for model, similar in zip(raw, similarity)
            ]
            validation_bias = _median_residual(actual, blended)
            prepared = _prepare_model_data(horizon_rows, [])
            estimator, scaler = _fit_prepared_model(candidate, prepared)
            transform = _fit_feature_transform(horizon_rows)
            horizon_models[horizon] = {
                "estimator": estimator,
                "scaler": scaler,
                "transform": transform,
                "candidate": candidate,
                "validation_bias_mw": validation_bias,
                "residual_std_mw": float(result.forecast_uncertainty_mw),
                "training_rows": (
                    [_similar_period_row(row) for row in horizon_rows]
                    if candidate.similarity_weight > 0
                    else []
                ),
                "selection_evidence": metrics,
                "holdout_metrics": {
                    "mae": result.mae,
                    "rmse": result.rmse,
                    "mape": result.mape,
                    "residual_std": result.residual_std,
                },
            }

        if set(horizon_models) != set(range(1, 7)):
            missing = sorted(set(range(1, 7)) - set(horizon_models))
            raise ValueError(f"Validated ML artifact missing horizons: {missing}")

        artifact: dict[str, object] = {
            "schema_version": ARTIFACT_SCHEMA,
            "model_name": "WGDSS frozen direct-horizon ensemble",
            "model_version": MODEL_VERSION,
            "feature_profile": FEATURE_PROFILE,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "training_start_at": min(row.feature_timestamp for row in rows).isoformat(),
            "training_end_at": max(row.target_timestamp for row in rows).isoformat(),
            "configured_training_start": settings.MODEL_TRAINING_START_DATE,
            "configured_training_end": settings.MODEL_TRAINING_END_DATE,
            "snapshot_used_for_training": False,
            "feature_names": [],
            "fill_values": {},
            "horizon_models": horizon_models,
            "training_row_count": len(rows),
        }
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact, path)
        return {
            "path": str(path),
            "sha256": _sha256(path),
            "schema_version": ARTIFACT_SCHEMA,
            "model_version": MODEL_VERSION,
            "training_start_at": artifact["training_start_at"],
            "training_end_at": artifact["training_end_at"],
            "training_row_count": len(rows),
            "horizons": sorted(horizon_models),
        }

    def _training_rows(self) -> list[ForecastTrainingRow]:
        with self.session_factory() as session:
            rows = list(
                session.scalars(
                    select(ForecastTrainingRow).order_by(
                        ForecastTrainingRow.horizon_hours,
                        ForecastTrainingRow.feature_timestamp,
                    )
                )
            )
        return [
            row
            for row in rows
            if self.period_policy.is_training_timestamp(row.feature_timestamp)
            and self.period_policy.is_training_timestamp(row.target_timestamp)
        ]

    def _released_results(self) -> dict[int, DemandForecastResult]:
        with self.session_factory() as session:
            rows = list(
                session.scalars(
                    select(DemandForecastResult).order_by(
                        DemandForecastResult.horizon_hours,
                        DemandForecastResult.generated_at.desc(),
                    )
                )
            )
        return {row.horizon_hours: row for row in rows}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _similar_period_row(row: ForecastTrainingRow) -> FrozenSimilarPeriodRow:
    return FrozenSimilarPeriodRow(
        horizon_hours=row.horizon_hours,
        feature_timestamp=row.feature_timestamp,
        target_timestamp=row.target_timestamp,
        target_demand_mw=row.target_demand_mw,
        temperature_c=row.temperature_c,
        forecast_temperature_c=row.forecast_temperature_c,
        humidity_percent=row.humidity_percent,
        forecast_rainfall_mm_hr=row.forecast_rainfall_mm_hr,
        forecast_cloud_cover_percent=row.forecast_cloud_cover_percent,
        current_demand_mw=row.current_demand_mw,
        demand_rate_1h_mw=row.demand_rate_1h_mw,
    )
