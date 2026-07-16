from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.session import SessionLocal
from app.services.demand_forecast_model_service import DemandForecastTrainingResult
from app.services.forecast_dataset_service import ForecastDatasetBuildResult
from app.services.historical_weather_backfill_service import (
    HistoricalWeatherBackfillResult,
    HistoricalWeatherBackfillService,
)
from app.services.scada_import_service import (
    ScadaImportResult,
    ScadaImportService,
    parse_reporting_datetime,
)
from app.services.scada_archive_service import ScadaArchiveReport, ScadaArchiveService
from app.services.scada_replay_validation_service import (
    ScadaReplayValidationReport,
    ScadaReplayValidationService,
)
from app.services.scada_replay_forecast_service import (
    ScadaReplayForecastRefreshResult,
    ScadaReplayForecastService,
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
    weather_backfill_result: HistoricalWeatherBackfillResult | None = None
    replay_forecast_result: ScadaReplayForecastRefreshResult | None = None

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
    source_paths: list[str | Path],
    session_factory=SessionLocal,
    backfill_weather: bool = False,
    expected_reporting_start: datetime | None = None,
    expected_reporting_end: datetime | None = None,
) -> ScadaReplayPipelineResult:
    import_service = ScadaImportService(
        session_factory=session_factory,
        expected_reporting_start=expected_reporting_start,
        expected_reporting_end=expected_reporting_end,
    )
    paths = [Path(path) for path in source_paths]
    zip_paths = [path for path in paths if path.suffix.lower() == ".zip"]
    if zip_paths and (len(paths) != 1 or len(zip_paths) != 1):
        raise ValueError("Provide one SCADA ZIP archive or one or more CSV files")

    archive_service = ScadaArchiveService(
        session_factory=session_factory,
        import_service=import_service,
    )
    archive_report: ScadaArchiveReport | None = None
    if zip_paths:
        archive_report = archive_service.inspect_archive(zip_paths[0])
        preflight_report = _archive_preflight_report(archive_report)
    else:
        preflight_report = ScadaReplayPreflightService(
            import_service=import_service
        ).inspect(paths)
    if not preflight_report.ready:
        raise ValueError(
            "SCADA replay preflight failed: " + "; ".join(preflight_report.blockers)
        )
    if archive_report is not None:
        import_results = list(
            archive_service.import_archive(paths[0]).import_results
        )
    else:
        import_results = [import_service.import_csv(path) for path in paths]

    snapshot_result = ScadaSnapshotService(
        session_factory=session_factory
    ).build_hourly_snapshots(import_run_id=None, replace_existing=True)
    weather_backfill_result = (
        HistoricalWeatherBackfillService(
            session_factory=session_factory
        ).backfill_scada_range()
        if backfill_weather
        else None
    )
    dataset_result = ForecastDatasetService(
        session_factory=session_factory
    ).build_training_rows(replace_existing=True)
    training_result = DemandForecastModelService(
        session_factory=session_factory
    ).train_and_store(replace_existing=True)
    replay_forecast_result = ScadaReplayForecastService(
        session_factory=session_factory
    ).refresh_for_current_clock()
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
        weather_backfill_result=weather_backfill_result,
        replay_forecast_result=replay_forecast_result,
    )


def _archive_preflight_report(
    report: ScadaArchiveReport,
) -> ScadaReplayPreflightReport:
    quality_counts: dict[str, int] = {}
    for member in report.member_reports:
        for quality, count in member.quality_counts.items():
            key = quality.strip().lower()
            quality_counts[key] = quality_counts.get(key, 0) + count
    blockers: list[str] = []
    if report.missing_tags:
        blockers.append(
            "missing required SCADA tag(s): " + ", ".join(report.missing_tags)
        )
    if report.aligned_hour_count < 8:
        blockers.append(
            "fewer than 8 interval-aligned usable hourly snapshots are available"
        )
    return ScadaReplayPreflightReport(
        files_checked=len(report.member_reports),
        rows_checked=report.total_rows,
        required_tags=tuple(sorted(report.observed_tags + report.missing_tags)),
        observed_tags=report.observed_tags,
        missing_tags=report.missing_tags,
        aligned_hour_count=report.aligned_hour_count,
        ready=not blockers,
        blockers=tuple(blockers),
        warnings=report.warnings,
        quality_counts=dict(sorted(quality_counts.items())),
        conditional_hour_count=report.conditional_hour_count,
        degraded_hour_count=report.degraded_hour_count,
    )


def format_summary(result: ScadaReplayPipelineResult) -> str:
    lines = [
        "SCADA Replay Pipeline Summary",
        f"preflight aligned usable hours: {result.preflight_report.aligned_hour_count}",
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
    if result.weather_backfill_result is not None:
        lines.append(
            "historical weather rows stored: "
            f"{result.weather_backfill_result.rows_stored}"
        )
    if result.replay_forecast_result is not None:
        lines.append(
            "cutoff-safe replay forecasts stored: "
            f"{result.replay_forecast_result.rows_stored}"
        )
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
                f"(ready={str(report.risk_readiness.ready).lower()}, "
                f"source={report.risk_readiness.forecast_source})"
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
        "source_paths",
        nargs="+",
        help="One SCADA ZIP archive or one or more historical SCADA CSV exports",
    )
    parser.add_argument(
        "--backfill-weather",
        action="store_true",
        help="Backfill Open-Meteo historical feature-time weather for the SCADA range",
    )
    parser.add_argument(
        "--reporting-start",
        default=None,
        help="Optional ISO-8601 export reporting-window start; values are never inferred",
    )
    parser.add_argument(
        "--reporting-end",
        default=None,
        help="Optional ISO-8601 export reporting-window end; values are never inferred",
    )
    args = parser.parse_args()

    result = run_pipeline(
        args.source_paths,
        backfill_weather=args.backfill_weather,
        expected_reporting_start=parse_reporting_datetime(args.reporting_start),
        expected_reporting_end=parse_reporting_datetime(args.reporting_end),
    )
    print(format_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
