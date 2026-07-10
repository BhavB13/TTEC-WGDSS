from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select

from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.demand_forecast import DemandForecastResult, ForecastTrainingRow
from app.models.scada import ScadaGridSnapshot, ScadaImportRun, ScadaRawMeasurement
from app.services.risk_probability_engine import OperatingRiskInput, RiskProbabilityEngine


@dataclass(frozen=True)
class ImportStatusSummary:
    import_runs: int
    raw_measurements: int
    latest_source_filename: str | None


@dataclass(frozen=True)
class SnapshotQualitySummary:
    total_snapshots: int
    good_snapshots: int
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
                degraded_snapshots=sum(
                    1 for snapshot in snapshots if snapshot.quality_status != "GOOD"
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
            )
        return RiskReadinessSummary(ready=True, status=risk.risk_level, blockers=[])
