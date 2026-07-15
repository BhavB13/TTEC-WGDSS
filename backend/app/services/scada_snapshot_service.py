from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from sqlalchemy import delete, select

from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.scada import ScadaGridSnapshot, ScadaRawMeasurement

logger = logging.getLogger(__name__)

SCADA_TAG_FIELD_MAP = {
    "PTL132 GENERATION TOTALS": "current_demand_mw",
    "MHO132 AVERAGE AMBIENT TEMPERATURE": "temperature_c",
    "GSYS SYSTEM_CORRECTED_SPIN_TOTAL": "spinning_reserve_mw",
    "GSYS SYSTEM_AVAIL_TOTAL": "available_capacity_mw",
    "GSYS SYSTEM_ONLN_TOTAL": "online_capacity_mw",
}

REQUIRED_SNAPSHOT_FIELDS = {
    "current_demand_mw",
    "temperature_c",
    "spinning_reserve_mw",
    "available_capacity_mw",
    "online_capacity_mw",
}

STRICT_QUALITY_VALUES = {"good"}
CONDITIONAL_QUALITY_VALUES = {"other"}
USABLE_QUALITY_VALUES = STRICT_QUALITY_VALUES | CONDITIONAL_QUALITY_VALUES
MIN_HOURLY_COVERAGE = 0.90
MAX_EXPECTED_COVERAGE = 1.05
RESAMPLING_METHOD = "interval_overlap_hourly"


@dataclass(frozen=True)
class ScadaSnapshotBuildResult:
    snapshots_created: int
    source_measurements: int
    degraded_snapshots: int
    conditional_snapshots: int = 0


class ScadaSnapshotService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def build_hourly_snapshots(
        self,
        import_run_id: int | None = None,
        replace_existing: bool = True,
    ) -> ScadaSnapshotBuildResult:
        if self.session_factory is SessionLocal:
            initialize_database()

        with self.session_factory() as session:
            query = select(ScadaRawMeasurement).where(
                ScadaRawMeasurement.tag_name.in_(SCADA_TAG_FIELD_MAP)
            )
            if import_run_id is not None:
                query = query.where(ScadaRawMeasurement.import_run_id == import_run_id)
            measurements = list(session.scalars(query))
            snapshots = self._build_snapshots(measurements)

            if replace_existing and snapshots:
                timestamps = [snapshot.timestamp for snapshot in snapshots]
                session.execute(
                    delete(ScadaGridSnapshot).where(
                        ScadaGridSnapshot.timestamp.in_(timestamps)
                    )
                )
                session.flush()

            session.add_all(snapshots)
            session.commit()

        degraded = sum(1 for snapshot in snapshots if snapshot.quality_status == "DEGRADED")
        conditional = sum(
            1 for snapshot in snapshots if snapshot.quality_status == "USABLE_WITH_WARNING"
        )
        return ScadaSnapshotBuildResult(
            snapshots_created=len(snapshots),
            source_measurements=len(measurements),
            degraded_snapshots=degraded,
            conditional_snapshots=conditional,
        )

    def preview_hourly_snapshots(
        self,
        measurements: Iterable[ScadaRawMeasurement | Mapping[str, Any]],
    ) -> list[ScadaGridSnapshot]:
        """Build snapshots without persistence for preflight and quality reports."""
        return self._build_snapshots(measurements)

    def _build_snapshots(
        self,
        measurements: Iterable[ScadaRawMeasurement | Mapping[str, Any]],
    ) -> list[ScadaGridSnapshot]:
        unique = self._deduplicate_measurements(measurements)
        buckets: dict[datetime, dict[str, dict[str, Any]]] = defaultdict(
            lambda: defaultdict(
                lambda: {
                    "weighted_sum": 0.0,
                    "coverage_seconds": 0.0,
                    "excluded_seconds": 0.0,
                    "point_values": [],
                    "qualities": set(),
                    "excluded_qualities": set(),
                    "sources": set(),
                }
            )
        )
        bucket_sources: dict[datetime, set[str]] = defaultdict(set)

        for measurement in unique:
            tag_name = str(_measurement_value(measurement, "tag_name") or "").strip()
            field_name = SCADA_TAG_FIELD_MAP.get(tag_name)
            start_time = _measurement_value(measurement, "start_time")
            end_time = _measurement_value(measurement, "end_time")
            if field_name is None or not isinstance(start_time, datetime):
                continue
            value = float(_measurement_value(measurement, "avg_value"))
            quality = str(_measurement_value(measurement, "quality") or "unknown").strip()
            normalized_quality = quality.lower()
            source = str(
                _measurement_value(measurement, "source_filename") or "SCADA CSV"
            )

            if not isinstance(end_time, datetime) or end_time <= start_time:
                hour = _hour_bucket(start_time)
                accumulator = buckets[hour][field_name]
                accumulator["sources"].add(source)
                bucket_sources[hour].add(source)
                if normalized_quality in USABLE_QUALITY_VALUES:
                    accumulator["point_values"].append(value)
                    accumulator["qualities"].add(normalized_quality)
                else:
                    accumulator["excluded_qualities"].add(normalized_quality)
                continue

            hour = _hour_bucket(start_time)
            while hour < end_time:
                hour_end = hour + timedelta(hours=1)
                overlap_seconds = max(
                    0.0,
                    (min(end_time, hour_end) - max(start_time, hour)).total_seconds(),
                )
                if overlap_seconds > 0:
                    accumulator = buckets[hour][field_name]
                    accumulator["sources"].add(source)
                    bucket_sources[hour].add(source)
                    if normalized_quality in USABLE_QUALITY_VALUES:
                        accumulator["weighted_sum"] += value * overlap_seconds
                        accumulator["coverage_seconds"] += overlap_seconds
                        accumulator["qualities"].add(normalized_quality)
                    else:
                        accumulator["excluded_seconds"] += overlap_seconds
                        accumulator["excluded_qualities"].add(normalized_quality)
                hour = hour_end

        return [
            self._snapshot_from_accumulators(
                timestamp,
                field_accumulators,
                bucket_sources[timestamp],
            )
            for timestamp, field_accumulators in sorted(buckets.items())
        ]

    @staticmethod
    def _deduplicate_measurements(
        measurements: Iterable[ScadaRawMeasurement | Mapping[str, Any]],
    ) -> list[ScadaRawMeasurement | Mapping[str, Any]]:
        unique: list[ScadaRawMeasurement | Mapping[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for measurement in measurements:
            identity = (
                str(_measurement_value(measurement, "tag_name") or "").strip(),
                _measurement_value(measurement, "start_time"),
                _measurement_value(measurement, "end_time"),
                _measurement_value(measurement, "avg_value"),
                str(_measurement_value(measurement, "quality") or "").strip().lower(),
            )
            if identity in seen:
                continue
            seen.add(identity)
            unique.append(measurement)
        return unique

    @staticmethod
    def _snapshot_from_accumulators(
        timestamp: datetime,
        field_accumulators: dict[str, dict[str, Any]],
        source_names: set[str],
    ) -> ScadaGridSnapshot:
        field_values: dict[str, float] = {}
        field_coverage: dict[str, float] = {}
        conditional_fields: list[str] = []
        excluded_fields: list[str] = []
        overlapping_fields: list[str] = []
        for field_name, accumulator in field_accumulators.items():
            coverage_seconds = float(accumulator["coverage_seconds"])
            coverage_ratio = coverage_seconds / 3600.0
            point_values = [float(value) for value in accumulator["point_values"]]
            if coverage_seconds <= 0 and point_values:
                coverage_ratio = 1.0
                field_values[field_name] = sum(point_values) / len(point_values)
            field_coverage[field_name] = coverage_ratio
            if coverage_seconds > 0:
                field_values[field_name] = (
                    float(accumulator["weighted_sum"]) / coverage_seconds
                )
            if CONDITIONAL_QUALITY_VALUES & set(accumulator["qualities"]):
                conditional_fields.append(field_name)
            if accumulator["excluded_qualities"]:
                excluded_fields.append(field_name)
            if coverage_ratio > MAX_EXPECTED_COVERAGE:
                overlapping_fields.append(field_name)

        current_demand_mw = field_values.get("current_demand_mw")
        available_capacity_mw = field_values.get("available_capacity_mw")
        online_capacity_mw = field_values.get("online_capacity_mw")

        reserve_margin_mw = None
        reserve_margin_percent = None
        online_spare_mw = None
        if current_demand_mw is not None and available_capacity_mw is not None:
            reserve_margin_mw = available_capacity_mw - current_demand_mw
            if current_demand_mw > 0:
                reserve_margin_percent = reserve_margin_mw / current_demand_mw * 100.0
        if current_demand_mw is not None and online_capacity_mw is not None:
            online_spare_mw = online_capacity_mw - current_demand_mw

        insufficient_fields = {
            field
            for field in REQUIRED_SNAPSHOT_FIELDS
            if field_coverage.get(field, 0.0) < MIN_HOURLY_COVERAGE
        }
        missing_fields = sorted(insufficient_fields)
        quality_notes: list[str] = []
        if insufficient_fields:
            quality_notes.append(
                "Hourly coverage below 90% for " + ", ".join(sorted(insufficient_fields))
            )
        if conditional_fields:
            quality_notes.append(
                "Conditionally accepted 'Other' quality for "
                + ", ".join(sorted(conditional_fields))
            )
        if excluded_fields:
            quality_notes.append(
                "Excluded non-usable quality for " + ", ".join(sorted(excluded_fields))
            )
        if overlapping_fields:
            quality_notes.append(
                "Overlapping interval coverage for " + ", ".join(sorted(overlapping_fields))
            )

        if insufficient_fields or excluded_fields or overlapping_fields:
            quality_status = "DEGRADED"
        elif conditional_fields:
            quality_status = "USABLE_WITH_WARNING"
        else:
            quality_status = "GOOD"
        required_coverages = [field_coverage.get(field, 0.0) for field in REQUIRED_SNAPSHOT_FIELDS]
        coverage_percent = min(required_coverages, default=0.0) * 100.0
        source = ", ".join(sorted(source_names)) if source_names else "SCADA CSV"

        return ScadaGridSnapshot(
            timestamp=timestamp,
            current_demand_mw=_round_or_none(current_demand_mw),
            temperature_c=_round_or_none(field_values.get("temperature_c")),
            spinning_reserve_mw=_round_or_none(field_values.get("spinning_reserve_mw")),
            available_capacity_mw=_round_or_none(available_capacity_mw),
            online_capacity_mw=_round_or_none(online_capacity_mw),
            reserve_margin_mw=_round_or_none(reserve_margin_mw),
            reserve_margin_percent=_round_or_none(reserve_margin_percent),
            online_spare_mw=_round_or_none(online_spare_mw),
            quality_status=quality_status,
            missing_fields=", ".join(missing_fields),
            coverage_percent=round(min(100.0, coverage_percent), 2),
            quality_notes="; ".join(quality_notes),
            resampling_method=RESAMPLING_METHOD,
            source=source,
        )


def _hour_bucket(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _measurement_value(
    measurement: ScadaRawMeasurement | Mapping[str, Any],
    field_name: str,
) -> Any:
    if isinstance(measurement, Mapping):
        return measurement.get(field_name)
    return getattr(measurement, field_name, None)


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)
