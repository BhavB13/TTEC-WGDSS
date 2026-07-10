from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

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

GOOD_QUALITY_VALUES = {"good"}


@dataclass(frozen=True)
class ScadaSnapshotBuildResult:
    snapshots_created: int
    source_measurements: int
    degraded_snapshots: int


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

        degraded = sum(1 for snapshot in snapshots if snapshot.quality_status != "GOOD")
        return ScadaSnapshotBuildResult(
            snapshots_created=len(snapshots),
            source_measurements=len(measurements),
            degraded_snapshots=degraded,
        )

    def _build_snapshots(
        self,
        measurements: Iterable[ScadaRawMeasurement],
    ) -> list[ScadaGridSnapshot]:
        grouped: dict[datetime, list[ScadaRawMeasurement]] = defaultdict(list)
        for measurement in measurements:
            grouped[_hour_bucket(measurement.start_time)].append(measurement)

        snapshots: list[ScadaGridSnapshot] = []
        for timestamp, rows in sorted(grouped.items()):
            field_values, field_qualities, source_names = self._aggregate_rows(rows)
            snapshot = self._snapshot_from_fields(
                timestamp=timestamp,
                field_values=field_values,
                field_qualities=field_qualities,
                source_names=source_names,
            )
            snapshots.append(snapshot)
        return snapshots

    @staticmethod
    def _aggregate_rows(
        rows: list[ScadaRawMeasurement],
    ) -> tuple[dict[str, float], dict[str, list[str]], set[str]]:
        values_by_field: dict[str, list[float]] = defaultdict(list)
        qualities_by_field: dict[str, list[str]] = defaultdict(list)
        source_names: set[str] = set()

        for row in rows:
            field_name = SCADA_TAG_FIELD_MAP.get(row.tag_name)
            if field_name is None:
                continue
            values_by_field[field_name].append(row.avg_value)
            qualities_by_field[field_name].append(row.quality)
            source_names.add(row.source_filename)

        field_values = {
            field_name: sum(values) / len(values)
            for field_name, values in values_by_field.items()
            if values
        }
        return field_values, dict(qualities_by_field), source_names

    @staticmethod
    def _snapshot_from_fields(
        timestamp: datetime,
        field_values: dict[str, float],
        field_qualities: dict[str, list[str]],
        source_names: set[str],
    ) -> ScadaGridSnapshot:
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

        quality_status = _snapshot_quality(field_values, field_qualities)
        missing_fields = sorted(REQUIRED_SNAPSHOT_FIELDS - set(field_values))
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
            source=source,
        )


def _hour_bucket(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def _snapshot_quality(
    field_values: dict[str, float],
    field_qualities: dict[str, list[str]],
) -> str:
    if not REQUIRED_SNAPSHOT_FIELDS.issubset(field_values):
        return "DEGRADED"

    for required_field in REQUIRED_SNAPSHOT_FIELDS:
        qualities = field_qualities.get(required_field, [])
        if not qualities:
            return "DEGRADED"
        if any(quality.strip().lower() not in GOOD_QUALITY_VALUES for quality in qualities):
            return "DEGRADED"

    return "GOOD"


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)
