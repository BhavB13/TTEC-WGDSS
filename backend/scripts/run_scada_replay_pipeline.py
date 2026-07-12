from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.session import SessionLocal
from app.services.demand_forecast_model_service import DemandForecastTrainingResult
from app.services.forecast_dataset_service import ForecastDatasetBuildResult
from app.services.scada_import_service import ScadaImportResult, ScadaImportService
from app.services.scada_replay_validation_service import (
    ScadaReplayValidationReport,
    ScadaReplayValidationService,
)
from app.services.scada_replay_preflight_service import (
    ScadaReplayPreflightReport,
    ScadaReplayPreflightService,
)
from app.services.scada_snapshot_service import ScadaSnapshotBuildResult, ScadaSnapshotService
from app.services.demand_forecast_model_service import DemandForecastModelService
from app.services.forecast_dataset_service import ForecastDatasetService


@dataclass(frozen=True)
class ScadaReplayPipelineResult:
    preflight_report: ScadaReplayPreflightReport
    import_results: list[ScadaImportResult]
    snapshot_result: ScadaSnapshotBuildResult
    dataset_result: ForecastDatasetBuildResult
    training_result: DemandForecastTrainingResult
    validation_report: ScadaReplayValidationReport

    @property
    def files_imported(self) -> int:
        return sum(1 for result in self.import_results if result.imported)

    @property
    def duplicates_skipped(self) -> int:
        return sum(1 for result in self.import_results if result.skipped_duplicate)

    @property
    def raw_rows_stored(self) -> int:
        return sum(result.row_count for result in self.import_results if result.imported)


def run_pipeline(
    csv_paths: list[str | Path],
    session_factory=SessionLocal,
) -> ScadaReplayPipelineResult:
    import_service = ScadaImportService(session_factory=session_factory)
    preflight_report = ScadaReplayPreflightService(import_service=import_service).inspect(
        csv_paths
    )
    if not preflight_report.ready:
        raise ValueError(
            "SCADA replay preflight failed: " + "; ".join(preflight_report.blockers)
        )
    import_results = [import_service.import_csv(path) for path in csv_paths]

    snapshot_result = ScadaSnapshotService(
        session_factory=session_factory
    ).build_hourly_snapshots(import_run_id=None, replace_existing=True)
    dataset_result = ForecastDatasetService(
        session_factory=session_factory
    ).build_training_rows(replace_existing=True)
    training_result = DemandForecastModelService(
        session_factory=session_factory
    ).train_and_store(replace_existing=True)
    validation_report = ScadaReplayValidationService(
        session_factory=session_factory
    ).build_report()

    return ScadaReplayPipelineResult(
        preflight_report=preflight_report,
        import_results=import_results,
        snapshot_result=snapshot_result,
        dataset_result=dataset_result,
        training_result=training_result,
        validation_report=validation_report,
    )


def format_summary(result: ScadaReplayPipelineResult) -> str:
    lines = [
        "SCADA Replay Pipeline Summary",
        f"preflight aligned Good-quality hours: {result.preflight_report.aligned_hour_count}",
        f"files imported: {result.files_imported}",
        f"duplicates skipped: {result.duplicates_skipped}",
        f"raw rows stored: {result.raw_rows_stored}",
        f"snapshots created: {result.snapshot_result.snapshots_created}",
        f"degraded snapshots: {result.snapshot_result.degraded_snapshots}",
        f"training rows created: {result.dataset_result.rows_created}",
        f"skipped rows: {result.dataset_result.skipped_rows}",
        f"model horizons evaluated: {len(result.training_result.results)}",
    ]
    if result.preflight_report.warnings:
        lines.append("preflight warnings: " + "; ".join(result.preflight_report.warnings))
    for item in result.training_result.results:
        lines.extend(
            [
                f"{item.horizon_hours}h active model: {item.active_model}",
                (
                    f"{item.horizon_hours}h metrics: "
                    f"MAE={item.metrics.mae:.4f}, "
                    f"RMSE={item.metrics.rmse:.4f}, "
                    f"MAPE={item.metrics.mape:.4f}, "
                    f"residual_std={item.metrics.residual_std:.4f}"
                ),
                (
                    f"{item.horizon_hours}h ML beats baseline: "
                    f"{str(item.ml_beats_baseline).lower()}"
                ),
            ]
        )

    report = result.validation_report
    lines.extend(
        [
            f"validation import runs: {report.import_status.import_runs}",
            (
                "validation training rows by horizon: "
                f"{report.training_rows.by_horizon}"
            ),
            (
                "risk-engine readiness: "
                f"{report.risk_readiness.status} "
                f"(ready={str(report.risk_readiness.ready).lower()})"
            ),
        ]
    )
    if report.risk_readiness.blockers:
        lines.append(
            "risk-engine blockers: " + "; ".join(report.risk_readiness.blockers)
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the historical SCADA replay, forecast, and risk validation pipeline."
    )
    parser.add_argument(
        "csv_paths",
        nargs="+",
        help="One or more historical SCADA CSV exports",
    )
    args = parser.parse_args()

    result = run_pipeline(args.csv_paths)
    print(format_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
