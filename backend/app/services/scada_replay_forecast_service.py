from __future__ import annotations

import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.demand_forecast import ScadaReplayForecastResult
from app.models.scada import ScadaGridSnapshot
from app.services.demand_forecast_model_service import (
    MODEL_VERSION,
    DemandForecastModelService,
)
from app.services.forecast_dataset_service import ForecastDatasetService


TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")


@dataclass(frozen=True)
class ScadaReplayForecastRefreshResult:
    source_cursor_at: datetime | None
    rows_stored: int
    source_snapshots: int
    training_rows: int


class ScadaReplayForecastService:
    """Persist expensive, cutoff-safe replay predictions outside API requests."""

    def __init__(
        self,
        session_factory=SessionLocal,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(TRINIDAD_TZ))

    def refresh_for_current_clock(self) -> ScadaReplayForecastRefreshResult:
        source_cursor = self.mapped_source_cursor()
        if source_cursor is None:
            return ScadaReplayForecastRefreshResult(None, 0, 0, 0)
        return self.refresh(source_cursor)

    def refresh(self, source_cursor_at: datetime) -> ScadaReplayForecastRefreshResult:
        dataset = ForecastDatasetService(
            session_factory=self.session_factory
        ).build_evaluation_dataset(source_cursor_at)
        results = DemandForecastModelService(
            session_factory=self.session_factory
        ).evaluate_rows(dataset.rows, dataset.inference_rows)
        generated_at = datetime.now(timezone.utc)
        with self.session_factory() as session:
            session.execute(delete(ScadaReplayForecastResult))
            for result in results:
                feature_timestamp = (
                    dataset.inference_rows[result.horizon_hours].feature_timestamp
                    if result.horizon_hours in dataset.inference_rows
                    else source_cursor_at
                )
                session.add(
                    ScadaReplayForecastResult(
                        source_cursor_at=source_cursor_at,
                        feature_timestamp=feature_timestamp,
                        forecast_timestamp=result.forecast_timestamp,
                        horizon_hours=result.horizon_hours,
                        forecast_demand_mw=result.forecast_demand_mw,
                        forecast_uncertainty_mw=result.forecast_uncertainty_mw,
                        model_name=result.active_model,
                        model_version=MODEL_VERSION,
                        baseline_name=result.best_baseline,
                        baseline_forecast_mw=result.baseline_forecast_mw,
                        quality_status=result.mode,
                        mae=result.metrics.mae,
                        rmse=result.metrics.rmse,
                        mape=result.metrics.mape,
                        residual_std=result.metrics.residual_std,
                        baseline_mae=float(
                            (result.candidate_metrics or {})
                            .get("baseline", {})
                            .get("mae", result.metrics.mae)
                        ),
                        ml_beats_baseline=result.ml_beats_baseline,
                        feature_profile=result.feature_profile,
                        validation_status=result.validation_status,
                        training_span_hours=result.training_span_hours,
                        train_row_count=result.train_rows,
                        test_row_count=result.test_rows,
                        candidate_metrics=json.dumps(
                            result.candidate_metrics or {},
                            sort_keys=True,
                        ),
                        confidence_lower_mw=result.confidence_lower_mw,
                        confidence_upper_mw=result.confidence_upper_mw,
                        confidence_level=result.confidence_level,
                        temperature_load_correlation=(
                            result.temperature_load_correlation
                        ),
                        similar_period_forecast_mw=(
                            result.similar_period_forecast_mw
                        ),
                        similar_examples=json.dumps(
                            result.similar_examples,
                            sort_keys=True,
                        ),
                        contributing_factors=json.dumps(
                            result.contributing_factors,
                        ),
                        training_rows=result.train_rows + result.test_rows,
                        generated_at=generated_at,
                    )
                )
            session.commit()
        return ScadaReplayForecastRefreshResult(
            source_cursor_at=source_cursor_at,
            rows_stored=len(results),
            source_snapshots=dataset.source_snapshots,
            training_rows=len(dataset.rows),
        )

    def mapped_source_cursor(self) -> datetime | None:
        with self.session_factory() as session:
            snapshots = list(
                session.scalars(
                    select(ScadaGridSnapshot).order_by(ScadaGridSnapshot.timestamp)
                )
            )
        available = [
            _available_at(snapshot)
            for snapshot in snapshots
            if _available_at(snapshot).month == settings.DEMO_REPLAY_MONTH
        ]
        if not available:
            return None
        source_year = max(value.year for value in available)
        available = [value for value in available if value.year == source_year]
        now = self.clock()
        if now.tzinfo is not None:
            now = now.astimezone(TRINIDAD_TZ).replace(tzinfo=None)
        last_day = monthrange(source_year, settings.DEMO_REPLAY_MONTH)[1]
        requested = datetime(
            source_year,
            settings.DEMO_REPLAY_MONTH,
            min(max(1, now.day), last_day),
            now.hour,
        )
        return min(max(requested, min(available)), max(available))

    def forecasts_for_source_cursor(
        self,
        source_cursor_at: datetime,
    ) -> list[ScadaReplayForecastResult]:
        with self.session_factory() as session:
            return list(
                session.scalars(
                    select(ScadaReplayForecastResult)
                    .where(
                        ScadaReplayForecastResult.source_cursor_at
                        == source_cursor_at.replace(tzinfo=None)
                    )
                    .order_by(ScadaReplayForecastResult.horizon_hours)
                )
            )


def _available_at(snapshot: ScadaGridSnapshot) -> datetime:
    return (snapshot.available_at or snapshot.timestamp).replace(
        minute=0,
        second=0,
        microsecond=0,
        tzinfo=None,
    )
