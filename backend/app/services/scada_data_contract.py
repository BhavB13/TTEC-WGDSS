from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


SOURCE_SYSTEM = "AspenTech OSI trend export"
SOURCE_PROVIDER = "csv_trend_export"
SOURCE_TIMEZONE = "America/Port_of_Spain"
AGGREGATION_INTERVAL_SUMMARY = "interval_summary"


class NormalizedQuality(StrEnum):
    GOOD = "good"
    UNCERTAIN = "uncertain"
    BAD = "bad"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ScadaTagDefinition:
    source_tag: str
    canonical_variable: str
    snapshot_field: str
    business_alias: str | None = None
    semantic_status: str = "pending_utility_confirmation"
    engineering_unit: str | None = None


TAG_DEFINITIONS = (
    ScadaTagDefinition(
        source_tag="PTL132 GENERATION TOTALS",
        canonical_variable="system_generation_total_mw",
        snapshot_field="current_demand_mw",
        business_alias="demand_proxy",
    ),
    ScadaTagDefinition(
        source_tag="MHO132 AVERAGE AMBIENT TEMPERATURE",
        canonical_variable="ambient_temperature_c",
        snapshot_field="temperature_c",
    ),
    ScadaTagDefinition(
        source_tag="GSYS SYSTEM_CORRECTED_SPIN_TOTAL",
        canonical_variable="corrected_spinning_reserve_mw",
        snapshot_field="spinning_reserve_mw",
    ),
    ScadaTagDefinition(
        source_tag="GSYS SYSTEM_AVAIL_TOTAL",
        canonical_variable="total_available_capacity_mw",
        snapshot_field="available_capacity_mw",
    ),
    ScadaTagDefinition(
        source_tag="GSYS SYSTEM_ONLN_TOTAL",
        canonical_variable="total_running_available_capacity_mw",
        snapshot_field="online_capacity_mw",
    ),
)

TAG_REGISTRY = {definition.source_tag: definition for definition in TAG_DEFINITIONS}
SCADA_TAG_FIELD_MAP = {
    definition.source_tag: definition.snapshot_field for definition in TAG_DEFINITIONS
}

# These mappings are provisional defaults from the authoritative context. Raw
# quality is always retained so an approved OSI mapping can replace them later.
DEFAULT_QUALITY_MAP: Mapping[str, NormalizedQuality] = {
    "good": NormalizedQuality.GOOD,
    "questionable": NormalizedQuality.UNCERTAIN,
    "other": NormalizedQuality.UNKNOWN,
    "": NormalizedQuality.UNKNOWN,
    "missing": NormalizedQuality.UNKNOWN,
    "unknown": NormalizedQuality.UNKNOWN,
}


def normalize_quality(raw_quality: str | None) -> NormalizedQuality:
    normalized = (raw_quality or "").strip().lower()
    return DEFAULT_QUALITY_MAP.get(normalized, NormalizedQuality.UNKNOWN)


def interval_anomalies(
    *,
    start_time: datetime | None,
    end_time: datetime | None,
    min_time: datetime | None,
    min_value: float | None,
    max_time: datetime | None,
    max_value: float | None,
    avg_value: float | None,
    raw_quality: str | None,
) -> list[str]:
    flags: list[str] = []
    if start_time is None:
        flags.append("missing_start_time")
    if end_time is None:
        flags.append("missing_end_time")
    if start_time is not None and end_time is not None:
        if end_time <= start_time:
            flags.append("non_positive_interval")
        else:
            if min_time is not None and not start_time <= min_time <= end_time:
                flags.append("min_time_outside_interval")
            if max_time is not None and not start_time <= max_time <= end_time:
                flags.append("max_time_outside_interval")
    if min_value is not None and max_value is not None and min_value > max_value:
        flags.append("min_value_greater_than_max_value")
    if avg_value is not None:
        if not math.isfinite(avg_value):
            flags.append("non_finite_average")
        if min_value is not None and avg_value < min_value:
            flags.append("average_below_minimum")
        if max_value is not None and avg_value > max_value:
            flags.append("average_above_maximum")
    if normalize_quality(raw_quality) is NormalizedQuality.UNKNOWN:
        flags.append("unconfirmed_quality_mapping")
    # Engineering units do not exist in the supplied trend-export schema.
    flags.append("engineering_unit_unconfirmed")
    return list(dict.fromkeys(flags))


def stable_record_hash(measurement: Mapping[str, Any]) -> str:
    identity = {
        "source_system": measurement.get("source_system", SOURCE_SYSTEM),
        "source_tag": measurement.get("tag_name"),
        "pen_index": measurement.get("pen_index"),
        "start_time": _serialize(measurement.get("start_time")),
        "end_time": _serialize(measurement.get("end_time")),
        "min_time": _serialize(measurement.get("min_time")),
        "min_value": measurement.get("min_value"),
        "max_time": _serialize(measurement.get("max_time")),
        "max_value": measurement.get("max_value"),
        "avg_value": measurement.get("avg_value"),
        "raw_quality": str(measurement.get("quality") or "").strip(),
        "aggregation": measurement.get(
            "aggregation", AGGREGATION_INTERVAL_SUMMARY
        ),
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _serialize(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value
