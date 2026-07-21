from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, or_, select

from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.demand_forecast import (
    DemandForecastResult,
    ForecastTrainingRow,
    ScadaReplayForecastResult,
)
from app.models.scada import ScadaGridSnapshot, ScadaImportRun, ScadaRawMeasurement
from app.services.risk_probability_engine import OperatingRiskInput, RiskProbabilityEngine
from app.services.risk_probability_engine import OperatingForecastPoint


@dataclass(frozen=True)
class ImportStatusSummary:
    import_runs: int
    raw_measurements: int
    latest_source_filename: str | None


@dataclass(frozen=True)
class SnapshotQualitySummary:
    total_snapshots: int
    good_snapshots: int
    conditional_snapshots: int
    degraded_snapshots: int
    missing_fields: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingRowsSummary:
    total_rows: int
    by_horizon: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelMetricSummary:
    horizon_hours: int
    active_model: str
    quality_status: str
    best_baseline: str
    mae: float
    rmse: float
    mape: float
    residual_std: float
    ml_beats_baseline: bool


@dataclass(frozen=True)
class RiskReadinessSummary:
    ready: bool
    status: str
    blockers: list[str] = field(default_factory=list)
    forecast_source: str = "UNAVAILABLE"
    source_cursor_at: datetime | None = None


@dataclass(frozen=True)
class ScadaReplayValidationReport:
    import_status: ImportStatusSummary
    snapshot_quality: SnapshotQualitySummary
    training_rows: TrainingRowsSummary
    model_metrics: list[ModelMetricSummary]
    risk_readiness: RiskReadinessSummary


class ScadaReplayValidationService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def build_report(self) -> ScadaReplayValidationReport:
        if self.session_factory is SessionLocal:
            initialize_database()

        with self.session_factory() as session:
            import_status = ImportStatusSummary(
                import_runs=session.scalar(select(func.count(ScadaImportRun.id))) or 0,
                raw_measurements=(
                    session.scalar(select(func.count(ScadaRawMeasurement.id))) or 0
                ),
                latest_source_filename=self._latest_source_filename(session),
            )

            snapshots = list(
                session.scalars(
                    select(ScadaGridSnapshot).order_by(ScadaGridSnapshot.timestamp)
                )
            )
            snapshot_quality = SnapshotQualitySummary(
                total_snapshots=len(snapshots),
                good_snapshots=sum(
                    1 for snapshot in snapshots if snapshot.quality_status == "GOOD"
                ),
                conditional_snapshots=sum(
                    1
                    for snapshot in snapshots
                    if snapshot.quality_status == "USABLE_WITH_WARNING"
                ),
                degraded_snapshots=sum(
                    1 for snapshot in snapshots if snapshot.quality_status == "DEGRADED"
                ),
                missing_fields=self._missing_field_counts(snapshots),
            )

            training_rows = TrainingRowsSummary(
                total_rows=session.scalar(select(func.count(ForecastTrainingRow.id))) or 0,
                by_horizon=self._training_rows_by_horizon(session),
            )

            model_metrics = self._latest_model_metrics(session)
            risk_readiness = self._risk_readiness(session)

        return ScadaReplayValidationReport(
            import_status=import_status,
            snapshot_quality=snapshot_quality,
            training_rows=training_rows,
            model_metrics=model_metrics,
            risk_readiness=risk_readiness,
        )

    @staticmethod
    def _latest_source_filename(session) -> str | None:
        latest = session.scalar(
            select(ScadaImportRun).order_by(ScadaImportRun.imported_at.desc())
        )
        return latest.source_filename if latest is not None else None

    @staticmethod
    def _missing_field_counts(snapshots: list[ScadaGridSnapshot]) -> dict[str, int]:
        counter: Counter[str] = Counter()
        for snapshot in snapshots:
            fields = [
                field.strip()
                for field in (snapshot.missing_fields or "").split(",")
                if field.strip()
            ]
            counter.update(fields)
        return dict(sorted(counter.items()))

    @staticmethod
    def _training_rows_by_horizon(session) -> dict[int, int]:
        rows = session.execute(
            select(ForecastTrainingRow.horizon_hours, func.count(ForecastTrainingRow.id))
            .group_by(ForecastTrainingRow.horizon_hours)
            .order_by(ForecastTrainingRow.horizon_hours)
        ).all()
        return {int(horizon): int(count) for horizon, count in rows}

    @staticmethod
    def _latest_model_metrics(session) -> list[ModelMetricSummary]:
        results = list(
            session.scalars(
                select(DemandForecastResult).order_by(
                    DemandForecastResult.horizon_hours,
                    DemandForecastResult.generated_at.desc(),
                    DemandForecastResult.id.desc(),
                )
            )
        )
        latest_by_horizon: dict[int, DemandForecastResult] = {}
        for result in results:
            latest_by_horizon.setdefault(result.horizon_hours, result)

        return [
            ModelMetricSummary(
                horizon_hours=result.horizon_hours,
                active_model=result.model_name,
                quality_status=result.quality_status,
                best_baseline=result.baseline_name,
                mae=result.mae,
                rmse=result.rmse,
                mape=result.mape,
                residual_std=result.residual_std,
                ml_beats_baseline=result.ml_beats_baseline,
            )
            for result in latest_by_horizon.values()
        ]

    def _risk_readiness(self, session) -> RiskReadinessSummary:
        replay_forecasts = list(
            session.scalars(
                select(ScadaReplayForecastResult).order_by(
                    ScadaReplayForecastResult.source_cursor_at.desc(),
                    ScadaReplayForecastResult.horizon_hours,
                )
            )
        )
        if replay_forecasts:
            source_cursor = replay_forecasts[0].source_cursor_at
            replay_forecasts = [
                row
                for row in replay_forecasts
                if row.source_cursor_at == source_cursor
            ]
            return self._replay_risk_readiness(
                session,
                source_cursor,
                replay_forecasts,
            )

        latest_snapshot = session.scalar(
            select(ScadaGridSnapshot).order_by(ScadaGridSnapshot.timestamp.desc())
        )
        latest_forecast = session.scalar(
            select(DemandForecastResult)
            .where(DemandForecastResult.horizon_hours == 1)
            .order_by(
                DemandForecastResult.generated_at.desc(),
                DemandForecastResult.id.desc(),
            )
        )

        blockers: list[str] = []
        if latest_snapshot is None:
            blockers.append("missing SCADA grid snapshot")
        if latest_forecast is None:
            blockers.append("missing 1h demand forecast result")

        if latest_snapshot is not None:
            if latest_snapshot.current_demand_mw is None:
                blockers.append("missing current demand")
            if latest_snapshot.online_capacity_mw is None:
                blockers.append("missing online capacity")

        if latest_forecast is not None and latest_forecast.forecast_uncertainty_mw <= 0:
            blockers.append("missing positive forecast uncertainty")

        if blockers:
            return RiskReadinessSummary(
                ready=False,
                status="UNAVAILABLE",
                blockers=blockers,
                forecast_source="LATEST_STORED_FORECAST",
            )

        assert latest_snapshot is not None
        assert latest_forecast is not None
        risk = RiskProbabilityEngine().evaluate(
            OperatingRiskInput(
                forecast_demand_mw=latest_forecast.forecast_demand_mw,
                forecast_uncertainty_mw=latest_forecast.forecast_uncertainty_mw,
                current_demand_mw=latest_snapshot.current_demand_mw,
                online_capacity_mw=latest_snapshot.online_capacity_mw,
                available_capacity_mw=latest_snapshot.available_capacity_mw,
                spinning_reserve_mw=latest_snapshot.spinning_reserve_mw,
            )
        )

        if risk.risk_level == "UNAVAILABLE":
            return RiskReadinessSummary(
                ready=False,
                status=risk.risk_level,
                blockers=risk.reasons,
                forecast_source="LATEST_STORED_FORECAST",
            )
        return RiskReadinessSummary(
            ready=True,
            status=risk.risk_level,
            blockers=[],
            forecast_source="LATEST_STORED_FORECAST",
        )

    @staticmethod
    def _replay_risk_readiness(
        session,
        source_cursor: datetime,
        forecasts: list[ScadaReplayForecastResult],
    ) -> RiskReadinessSummary:
        horizons = {row.horizon_hours for row in forecasts}
        blockers: list[str] = []
        missing_horizons = sorted({1, 2, 3, 4, 5, 6} - horizons)
        if missing_horizons:
            blockers.append(
                "missing cutoff-safe forecast horizon(s): "
                + ", ".join(f"{h}h" for h in missing_horizons)
            )
        snapshot = session.scalar(
            select(ScadaGridSnapshot)
            .where(
                or_(
                    ScadaGridSnapshot.available_at <= source_cursor,
                    (
                        ScadaGridSnapshot.available_at.is_(None)
                        & (ScadaGridSnapshot.timestamp <= source_cursor)
                    ),
                )
            )
            .order_by(
                ScadaGridSnapshot.available_at.desc(),
                ScadaGridSnapshot.timestamp.desc(),
            )
        )
        if snapshot is None:
            blockers.append("missing SCADA snapshot for replay forecast cursor")
        elif snapshot.missing_fields.strip():
            blockers.append(
                "SCADA replay cursor is missing: " + snapshot.missing_fields
            )
        if any(row.forecast_uncertainty_mw <= 0 for row in forecasts):
            blockers.append("missing positive forecast uncertainty")
        if blockers:
            return RiskReadinessSummary(
                ready=False,
                status="UNAVAILABLE",
                blockers=blockers,
                forecast_source="CUTOFF_SAFE_REPLAY",
                source_cursor_at=source_cursor,
            )

        assert snapshot is not None
        one_hour = next(row for row in forecasts if row.horizon_hours == 1)
        profile = tuple(
            OperatingForecastPoint(
                horizon_minutes=row.horizon_hours * 60,
                forecast_demand_mw=row.forecast_demand_mw,
                forecast_uncertainty_mw=row.forecast_uncertainty_mw,
                confidence=(0.75 if "DEGRADED" in row.quality_status else 0.9),
            )
            for row in sorted(forecasts, key=lambda item: item.horizon_hours)
        )
        risk = RiskProbabilityEngine().evaluate(
            OperatingRiskInput(
                forecast_demand_mw=one_hour.forecast_demand_mw,
                forecast_uncertainty_mw=one_hour.forecast_uncertainty_mw,
                current_demand_mw=snapshot.current_demand_mw,
                online_capacity_mw=snapshot.online_capacity_mw,
                available_capacity_mw=snapshot.available_capacity_mw,
                spinning_reserve_mw=snapshot.spinning_reserve_mw,
                forecast_profile=profile,
                available_capacity_is_verified=True,
            )
        )
        if risk.risk_level == "UNAVAILABLE":
            return RiskReadinessSummary(
                ready=False,
                status=risk.risk_level,
                blockers=risk.reasons,
                forecast_source="CUTOFF_SAFE_REPLAY",
                source_cursor_at=source_cursor,
            )
        return RiskReadinessSummary(
            ready=True,
            status=risk.risk_level,
            blockers=[],
            forecast_source="CUTOFF_SAFE_REPLAY",
            source_cursor_at=source_cursor,
        )
