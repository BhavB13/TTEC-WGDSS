from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select

from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.demand_forecast import ForecastTrainingRow
from app.models.scada import ScadaGridSnapshot
from app.services.demand_forecast_model_service import (
    DemandForecastModelService,
    DemandForecastTrainingResult,
)
from app.services.forecast_dataset_service import (
    ForecastDatasetBuildResult,
    ForecastDatasetService,
)


DEFAULT_MIN_GOOD_SNAPSHOTS = 48


@dataclass(frozen=True)
class ForecastRefreshResult:
    refreshed: bool
    reason: str
    good_snapshot_count: int
    latest_good_snapshot_at: datetime | None
    latest_training_feature_at: datetime | None
    dataset_result: ForecastDatasetBuildResult | None = None
    training_result: DemandForecastTrainingResult | None = None


class ForecastRefreshService:
    """Run a supervised, freshness-aware demand-forecast refresh.

    This service is intentionally invoked by an operator or external scheduler;
    it does not create an in-process background trainer. It never invents SCADA
    data and avoids rebuilding a model unless newer good-quality telemetry is
    available.
    """

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def refresh(
        self,
        *,
        force: bool = False,
        minimum_good_snapshots: int = DEFAULT_MIN_GOOD_SNAPSHOTS,
    ) -> ForecastRefreshResult:
        if minimum_good_snapshots < 3:
            raise ValueError("minimum_good_snapshots must be at least 3")
        if self.session_factory is SessionLocal:
            initialize_database()

        good_count, latest_snapshot, latest_training = self._freshness_state()
        if latest_snapshot is None:
            return self._skipped(
                "No Good-quality SCADA snapshots are available", good_count, None, latest_training
            )
        if good_count < minimum_good_snapshots:
            return self._skipped(
                "Insufficient Good-quality SCADA history "
                f"({good_count}/{minimum_good_snapshots} snapshots)",
                good_count,
                latest_snapshot,
                latest_training,
            )
        if (
            not force
            and latest_training is not None
            and latest_snapshot <= latest_training
        ):
            return self._skipped(
                "No newer Good-quality SCADA snapshot since the last dataset build",
                good_count,
                latest_snapshot,
                latest_training,
            )

        dataset_result = ForecastDatasetService(
            session_factory=self.session_factory
        ).build_training_rows(replace_existing=True)
        if dataset_result.rows_created < 3:
            return self._skipped(
                "Training dataset did not contain enough chronological rows",
                good_count,
                latest_snapshot,
                latest_training,
                dataset_result=dataset_result,
            )

        training_result = DemandForecastModelService(
            session_factory=self.session_factory
        ).train_and_store(replace_existing=True)
        if not training_result.results:
            return self._skipped(
                "No forecast horizon produced a valid model result",
                good_count,
                latest_snapshot,
                latest_training,
                dataset_result=dataset_result,
                training_result=training_result,
            )
        return ForecastRefreshResult(
            refreshed=True,
            reason="Forecast dataset and model refreshed from newer Good-quality SCADA data",
            good_snapshot_count=good_count,
            latest_good_snapshot_at=latest_snapshot,
            latest_training_feature_at=latest_training,
            dataset_result=dataset_result,
            training_result=training_result,
        )

    def _freshness_state(self) -> tuple[int, datetime | None, datetime | None]:
        with self.session_factory() as session:
            good_snapshots = (
                ScadaGridSnapshot.quality_status == "GOOD",
                ScadaGridSnapshot.missing_fields == "",
            )
            good_count = session.scalar(
                select(func.count(ScadaGridSnapshot.id)).where(*good_snapshots)
            ) or 0
            latest_snapshot = session.scalar(
                select(func.max(ScadaGridSnapshot.timestamp)).where(*good_snapshots)
            )
            latest_training = session.scalar(
                select(func.max(ForecastTrainingRow.feature_timestamp))
            )
        return int(good_count), latest_snapshot, latest_training

    @staticmethod
    def _skipped(
        reason: str,
        good_count: int,
        latest_snapshot: datetime | None,
        latest_training: datetime | None,
        dataset_result: ForecastDatasetBuildResult | None = None,
        training_result: DemandForecastTrainingResult | None = None,
    ) -> ForecastRefreshResult:
        return ForecastRefreshResult(
            refreshed=False,
            reason=reason,
            good_snapshot_count=good_count,
            latest_good_snapshot_at=latest_snapshot,
            latest_training_feature_at=latest_training,
            dataset_result=dataset_result,
            training_result=training_result,
        )
