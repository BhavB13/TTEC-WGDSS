from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.services.scada_import_service import ScadaImportService
from app.services.scada_snapshot_service import SCADA_TAG_FIELD_MAP


@dataclass(frozen=True)
class ScadaReplayPreflightReport:
    files_checked: int
    rows_checked: int
    required_tags: tuple[str, ...]
    observed_tags: tuple[str, ...]
    missing_tags: tuple[str, ...]
    aligned_hour_count: int
    ready: bool
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ScadaReplayPreflightService:
    """Validate historical SCADA exports before the replay pipeline mutates data.

    A report is deliberately conservative: it ensures all operating-risk tags
    overlap by timestamp, but leaves model adequacy decisions to the trainer.
    """

    def __init__(self, import_service: ScadaImportService | None = None) -> None:
        self.import_service = import_service or ScadaImportService()

    def inspect(self, csv_paths: list[str | Path]) -> ScadaReplayPreflightReport:
        required_tags = tuple(sorted(SCADA_TAG_FIELD_MAP))
        hours_by_tag: dict[str, set[datetime]] = defaultdict(set)
        good_rows_by_tag: dict[str, int] = defaultdict(int)
        observed_tags: set[str] = set()
        rows_checked = 0

        for csv_path in csv_paths:
            measurements = self.import_service.read_measurements(csv_path)
            rows_checked += len(measurements)
            for measurement in measurements:
                tag_name = str(measurement["tag_name"])
                if tag_name not in SCADA_TAG_FIELD_MAP:
                    continue
                observed_tags.add(tag_name)
                start_time = measurement.get("start_time")
                if start_time is None:
                    continue
                if str(measurement.get("quality", "")).strip().lower() == "good":
                    good_rows_by_tag[tag_name] += 1
                    hours_by_tag[tag_name].add(_hour_bucket(start_time))

        missing_tags = tuple(tag for tag in required_tags if tag not in observed_tags)
        aligned_hours = (
            set.intersection(*(hours_by_tag[tag] for tag in required_tags))
            if all(hours_by_tag[tag] for tag in required_tags)
            else set()
        )
        blockers: list[str] = []
        warnings: list[str] = []
        if missing_tags:
            blockers.append("missing required SCADA tag(s): " + ", ".join(missing_tags))
        missing_good = [tag for tag in required_tags if good_rows_by_tag[tag] == 0]
        if missing_good:
            blockers.append("no Good-quality samples for: " + ", ".join(missing_good))
        if len(aligned_hours) < 8:
            blockers.append(
                "fewer than 8 timestamp-aligned Good-quality hourly snapshots are available"
            )
        if 8 <= len(aligned_hours) < 24:
            warnings.append(
                "limited aligned history; replay is possible but unsuitable for a trusted production model"
            )

        return ScadaReplayPreflightReport(
            files_checked=len(csv_paths),
            rows_checked=rows_checked,
            required_tags=required_tags,
            observed_tags=tuple(sorted(observed_tags)),
            missing_tags=missing_tags,
            aligned_hour_count=len(aligned_hours),
            ready=not blockers,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
        )


def _hour_bucket(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)
