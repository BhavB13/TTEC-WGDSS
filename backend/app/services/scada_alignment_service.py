from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Iterable, Mapping

from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.scada import (
    ScadaArchiveImportRun,
    ScadaGridSnapshot,
    ScadaImportRun,
    ScadaRawMeasurement,
)
from app.services.scada_data_contract import interval_anomalies
from app.services.scada_snapshot_service import USABLE_QUALITY_VALUES


DEMAND_TAG = "PTL132 GENERATION TOTALS"
SELECTED_ALIGNMENT_METHOD = "interval_overlap_hourly"
ALIGNMENT_METHOD_VERSION = "scada-hourly-alignment-v1"
RECONCILIATION_TOLERANCE_MW = 0.1
HOLDOUT_FRACTION = 0.2
EVALUATED_HORIZONS = (1, 2, 3, 4, 5, 6)


@dataclass(frozen=True)
class AlignmentHorizonMetrics:
    horizon_hours: int
    baseline: str
    sample_count: int
    mae_mw: float
    rmse_mw: float
    mape_percent: float


@dataclass(frozen=True)
class AlignmentMethodMetrics:
    method: str
    hourly_values: int
    mean_mae_mw: float
    mean_rmse_mw: float
    horizons: tuple[AlignmentHorizonMetrics, ...]


@dataclass(frozen=True)
class AlignmentMismatch:
    timestamp: datetime
    expected_demand_mw: float
    stored_demand_mw: float | None
    absolute_difference_mw: float | None
    reason: str


@dataclass(frozen=True)
class ScadaAlignmentValidationReport:
    version: str
    validation_status: str
    selected_method: str
    selection_basis: str
    source_demand_intervals: int
    duplicate_intervals_removed: int
    method_metrics: tuple[AlignmentMethodMetrics, ...]
    reconciled_hours: int
    mismatch_count: int
    max_absolute_mismatch_mw: float
    reconciliation_tolerance_mw: float
    mismatches: tuple[AlignmentMismatch, ...]


class ScadaAlignmentService:
    """Audit hourly alignment without changing the interval-summary source layer."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def validate_archive_import(
        self,
        archive_import_run_id: int,
        *,
        persist: bool = True,
    ) -> ScadaAlignmentValidationReport:
        with self.session_factory() as session:
            measurements = list(
                session.scalars(
                    select(ScadaRawMeasurement)
                    .join(ScadaImportRun)
                    .where(
                        ScadaImportRun.archive_import_run_id
                        == archive_import_run_id,
                        ScadaRawMeasurement.tag_name == DEMAND_TAG,
                    )
                    .order_by(ScadaRawMeasurement.start_time)
                )
            )
            report = self.validate(measurements, self._snapshots_for(measurements, session))
            if persist:
                archive_run = session.get(ScadaArchiveImportRun, archive_import_run_id)
                if archive_run is not None:
                    try:
                        payload = json.loads(archive_run.validation_report or "{}")
                    except json.JSONDecodeError:
                        payload = {}
                    payload["alignment_validation"] = asdict(report)
                    archive_run.validation_report = json.dumps(
                        payload,
                        default=_json_default,
                        sort_keys=True,
                    )
                    session.commit()
            return report

    def validate(
        self,
        measurements: Iterable[ScadaRawMeasurement | Mapping[str, Any]],
        snapshots: Iterable[ScadaGridSnapshot],
    ) -> ScadaAlignmentValidationReport:
        intervals, duplicate_count = _clean_demand_intervals(measurements)
        if not intervals:
            return ScadaAlignmentValidationReport(
                version=ALIGNMENT_METHOD_VERSION,
                validation_status="UNAVAILABLE",
                selected_method=SELECTED_ALIGNMENT_METHOD,
                selection_basis="No usable demand intervals were available",
                source_demand_intervals=0,
                duplicate_intervals_removed=duplicate_count,
                method_metrics=(),
                reconciled_hours=0,
                mismatch_count=0,
                max_absolute_mismatch_mw=0.0,
                reconciliation_tolerance_mw=RECONCILIATION_TOLERANCE_MW,
                mismatches=(),
            )

        series_by_method = {
            SELECTED_ALIGNMENT_METHOD: _overlap_weighted_series(intervals),
            "interval_containing_hour_midpoint": _containing_midpoint_series(intervals),
            "nearest_interval_midpoint": _nearest_midpoint_series(intervals),
        }
        metrics = tuple(
            _evaluate_series(method, series)
            for method, series in series_by_method.items()
        )
        error_winner = min(
            metrics,
            key=lambda item: (item.mean_mae_mw, item.mean_rmse_mw, item.method),
        ).method

        expected = series_by_method[SELECTED_ALIGNMENT_METHOD]
        stored = {
            _hour_key(snapshot.timestamp): snapshot.current_demand_mw
            for snapshot in snapshots
        }
        mismatches: list[AlignmentMismatch] = []
        reconciled = 0
        max_difference = 0.0
        for timestamp, expected_value in sorted(expected.items()):
            stored_value = stored.get(timestamp)
            if stored_value is None:
                mismatches.append(
                    AlignmentMismatch(
                        timestamp=timestamp,
                        expected_demand_mw=round(expected_value, 4),
                        stored_demand_mw=None,
                        absolute_difference_mw=None,
                        reason="missing_hourly_snapshot",
                    )
                )
                continue
            difference = abs(float(stored_value) - expected_value)
            max_difference = max(max_difference, difference)
            if difference > RECONCILIATION_TOLERANCE_MW:
                mismatches.append(
                    AlignmentMismatch(
                        timestamp=timestamp,
                        expected_demand_mw=round(expected_value, 4),
                        stored_demand_mw=round(float(stored_value), 4),
                        absolute_difference_mw=round(difference, 4),
                        reason="stored_value_differs_from_source_overlap_weighting",
                    )
                )
            else:
                reconciled += 1

        selected_metrics = next(
            item for item in metrics if item.method == SELECTED_ALIGNMENT_METHOD
        )
        validation_status = (
            "VALID"
            if not mismatches and error_winner == SELECTED_ALIGNMENT_METHOD
            else "VALID_WITH_WARNING"
            if not mismatches
            else "MISMATCH"
        )
        selection_basis = (
            "Selected by lowest chronological holdout error and interval-average "
            "semantics; raw irregular intervals remain preserved"
            if error_winner == SELECTED_ALIGNMENT_METHOD
            else (
                f"{SELECTED_ALIGNMENT_METHOD} is retained for interval-average "
                f"fidelity; {error_winner} had lower holdout error and requires review"
            )
        )
        return ScadaAlignmentValidationReport(
            version=ALIGNMENT_METHOD_VERSION,
            validation_status=validation_status,
            selected_method=SELECTED_ALIGNMENT_METHOD,
            selection_basis=selection_basis,
            source_demand_intervals=len(intervals),
            duplicate_intervals_removed=duplicate_count,
            method_metrics=metrics,
            reconciled_hours=reconciled,
            mismatch_count=len(mismatches),
            max_absolute_mismatch_mw=round(max_difference, 4),
            reconciliation_tolerance_mw=RECONCILIATION_TOLERANCE_MW,
            mismatches=tuple(
                sorted(
                    mismatches,
                    key=lambda item: (
                        -(item.absolute_difference_mw or math.inf),
                        item.timestamp,
                    ),
                )[:50]
            ),
        )

    @staticmethod
    def _snapshots_for(measurements, session) -> list[ScadaGridSnapshot]:
        starts = [item.start_time for item in measurements if item.start_time is not None]
        ends = [item.end_time for item in measurements if item.end_time is not None]
        if not starts or not ends:
            return []
        first = _hour_key(min(starts))
        last = _ceil_hour(max(ends))
        return list(
            session.scalars(
                select(ScadaGridSnapshot)
                .where(
                    ScadaGridSnapshot.timestamp >= first,
                    ScadaGridSnapshot.timestamp < last,
                )
                .order_by(ScadaGridSnapshot.timestamp)
            )
        )


@dataclass(frozen=True)
class _DemandInterval:
    start_time: datetime
    end_time: datetime
    avg_value: float
    quality: str


def _clean_demand_intervals(
    measurements: Iterable[ScadaRawMeasurement | Mapping[str, Any]],
) -> tuple[list[_DemandInterval], int]:
    intervals: list[_DemandInterval] = []
    seen: set[tuple[object, ...]] = set()
    duplicates = 0
    for measurement in measurements:
        tag = str(_value(measurement, "tag_name") or "").strip()
        if tag != DEMAND_TAG:
            continue
        start = _value(measurement, "start_time")
        end = _value(measurement, "end_time")
        avg = _value(measurement, "avg_value")
        quality = str(_value(measurement, "quality") or "unknown").strip().lower()
        if not isinstance(start, datetime) or not isinstance(end, datetime) or end <= start:
            continue
        try:
            numeric = float(avg)
        except (TypeError, ValueError):
            continue
        anomalies = set(interval_anomalies(
            start_time=start,
            end_time=end,
            min_time=_value(measurement, "min_time"),
            min_value=_value(measurement, "min_value"),
            max_time=_value(measurement, "max_time"),
            max_value=_value(measurement, "max_value"),
            avg_value=numeric,
            raw_quality=quality,
        )) | _stored_anomalies(measurement)
        if "outside_expected_reporting_window" in anomalies:
            continue
        if quality not in USABLE_QUALITY_VALUES:
            continue
        identity = (start, end, numeric, quality)
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        intervals.append(_DemandInterval(start, end, numeric, quality))
    return sorted(intervals, key=lambda item: (item.start_time, item.end_time)), duplicates


def _overlap_weighted_series(intervals: list[_DemandInterval]) -> dict[datetime, float]:
    series: dict[datetime, float] = {}
    for hour in _hour_range(intervals):
        end = hour + timedelta(hours=1)
        weighted = [
            (
                item.avg_value,
                max(
                    0.0,
                    (min(item.end_time, end) - max(item.start_time, hour)).total_seconds(),
                ),
            )
            for item in intervals
            if item.start_time < end and item.end_time > hour
        ]
        accepted = [(value, seconds) for value, seconds in weighted if seconds > 0]
        coverage = sum(seconds for _, seconds in accepted)
        if coverage > 0:
            series[hour] = sum(value * seconds for value, seconds in accepted) / coverage
    return series


def _containing_midpoint_series(
    intervals: list[_DemandInterval],
) -> dict[datetime, float]:
    series: dict[datetime, float] = {}
    for hour in _hour_range(intervals):
        midpoint = hour + timedelta(minutes=30)
        containing = [
            item for item in intervals if item.start_time <= midpoint < item.end_time
        ]
        if containing:
            series[hour] = containing[-1].avg_value
    return series


def _nearest_midpoint_series(intervals: list[_DemandInterval]) -> dict[datetime, float]:
    series: dict[datetime, float] = {}
    for hour in _hour_range(intervals):
        midpoint = hour + timedelta(minutes=30)
        nearest = min(
            intervals,
            key=lambda item: abs(
                (
                    item.start_time
                    + (item.end_time - item.start_time) / 2
                    - midpoint
                ).total_seconds()
            ),
        )
        series[hour] = nearest.avg_value
    return series


def _evaluate_series(
    method: str,
    series: dict[datetime, float],
) -> AlignmentMethodMetrics:
    timestamps = sorted(series)
    if len(timestamps) < 10:
        return AlignmentMethodMetrics(method, len(timestamps), 0.0, 0.0, ())
    holdout_start = timestamps[max(1, int(len(timestamps) * (1.0 - HOLDOUT_FRACTION)))]
    horizon_metrics: list[AlignmentHorizonMetrics] = []
    for horizon in EVALUATED_HORIZONS:
        actual: list[float] = []
        candidates: dict[str, list[float]] = {
            "persistence": [],
            "same_hour_yesterday": [],
            "seasonal_naive_weekly": [],
        }
        for issue_time in timestamps:
            target_time = issue_time + timedelta(hours=horizon)
            if issue_time < holdout_start or target_time not in series:
                continue
            actual.append(series[target_time])
            candidates["persistence"].append(series[issue_time])
            candidates["same_hour_yesterday"].append(
                series.get(target_time - timedelta(hours=24), series[issue_time])
            )
            candidates["seasonal_naive_weekly"].append(
                series.get(target_time - timedelta(hours=168), series[issue_time])
            )
        scored = [
            (_error_metrics(actual, predicted), name)
            for name, predicted in candidates.items()
            if actual
        ]
        if not scored:
            continue
        (mae, rmse, mape), baseline = min(
            scored,
            key=lambda item: (item[0][0], item[0][1], item[1]),
        )
        horizon_metrics.append(
            AlignmentHorizonMetrics(
                horizon_hours=horizon,
                baseline=baseline,
                sample_count=len(actual),
                mae_mw=round(mae, 4),
                rmse_mw=round(rmse, 4),
                mape_percent=round(mape, 4),
            )
        )
    return AlignmentMethodMetrics(
        method=method,
        hourly_values=len(series),
        mean_mae_mw=round(mean(item.mae_mw for item in horizon_metrics), 4),
        mean_rmse_mw=round(mean(item.rmse_mw for item in horizon_metrics), 4),
        horizons=tuple(horizon_metrics),
    )


def _error_metrics(actual: list[float], predicted: list[float]) -> tuple[float, float, float]:
    errors = [observed - estimate for observed, estimate in zip(actual, predicted)]
    mae = mean(abs(error) for error in errors)
    rmse = math.sqrt(mean(error * error for error in errors))
    percentage = [
        abs(error) / observed * 100.0
        for observed, error in zip(actual, errors)
        if observed != 0
    ]
    return mae, rmse, mean(percentage) if percentage else 0.0


def _hour_range(intervals: list[_DemandInterval]) -> list[datetime]:
    first = _hour_key(min(item.start_time for item in intervals))
    last = _ceil_hour(max(item.end_time for item in intervals))
    result: list[datetime] = []
    current = first
    while current < last:
        result.append(current)
        current += timedelta(hours=1)
    return result


def _hour_key(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0, tzinfo=None)


def _ceil_hour(value: datetime) -> datetime:
    local = value.replace(tzinfo=None)
    floor = _hour_key(local)
    return floor if local == floor else floor + timedelta(hours=1)


def _value(measurement: ScadaRawMeasurement | Mapping[str, Any], name: str) -> Any:
    if isinstance(measurement, Mapping):
        return measurement.get(name)
    return getattr(measurement, name, None)


def _stored_anomalies(
    measurement: ScadaRawMeasurement | Mapping[str, Any],
) -> set[str]:
    value = _value(measurement, "anomaly_flags")
    if not isinstance(value, str):
        return set()
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return set()
    return {str(item) for item in decoded} if isinstance(decoded, list) else set()


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported alignment report value: {type(value).__name__}")
