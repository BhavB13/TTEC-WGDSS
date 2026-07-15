from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.services.scada_import_service import ScadaImportService
from app.services.scada_snapshot_service import (
    SCADA_TAG_FIELD_MAP,
    USABLE_QUALITY_VALUES,
    ScadaSnapshotService,
)


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
    quality_counts: dict[str, int] = field(default_factory=dict)
    conditional_hour_count: int = 0
    degraded_hour_count: int = 0


class ScadaReplayPreflightService:
    """Validate historical SCADA exports before the replay pipeline mutates data.

    A report is deliberately conservative: it ensures all operating-risk tags
    overlap by timestamp, but leaves model adequacy decisions to the trainer.
    """

    def __init__(self, import_service: ScadaImportService | None = None) -> None:
        self.import_service = import_service or ScadaImportService()

    def inspect(self, csv_paths: list[str | Path]) -> ScadaReplayPreflightReport:
        required_tags = tuple(sorted(SCADA_TAG_FIELD_MAP))
        usable_rows_by_tag: dict[str, int] = defaultdict(int)
        observed_tags: set[str] = set()
        all_measurements: list[dict[str, object]] = []
        quality_counts: Counter[str] = Counter()
        rows_checked = 0

        for csv_path in csv_paths:
            measurements = self.import_service.read_measurements(csv_path)
            rows_checked += len(measurements)
            for measurement in measurements:
                enriched = {**measurement, "source_filename": Path(csv_path).name}
                all_measurements.append(enriched)
                tag_name = str(measurement["tag_name"]).strip()
                if tag_name not in SCADA_TAG_FIELD_MAP:
                    continue
                observed_tags.add(tag_name)
                quality = str(measurement.get("quality", "")).strip().lower()
                quality_counts[quality] += 1
                if quality in USABLE_QUALITY_VALUES:
                    usable_rows_by_tag[tag_name] += 1

        missing_tags = tuple(tag for tag in required_tags if tag not in observed_tags)
        snapshots = ScadaSnapshotService().preview_hourly_snapshots(all_measurements)
        aligned_snapshots = [
            snapshot for snapshot in snapshots if snapshot.quality_status != "DEGRADED"
        ]
        conditional_hours = sum(
            snapshot.quality_status == "USABLE_WITH_WARNING" for snapshot in snapshots
        )
        degraded_hours = sum(snapshot.quality_status == "DEGRADED" for snapshot in snapshots)
        blockers: list[str] = []
        warnings: list[str] = []
        if missing_tags:
            blockers.append("missing required SCADA tag(s): " + ", ".join(missing_tags))
        missing_usable = [tag for tag in required_tags if usable_rows_by_tag[tag] == 0]
        if missing_usable:
            blockers.append("no usable-quality samples for: " + ", ".join(missing_usable))
        if len(aligned_snapshots) < 8:
            blockers.append(
                "fewer than 8 interval-aligned usable hourly snapshots are available"
            )
        if 8 <= len(aligned_snapshots) < 24:
            warnings.append(
                "limited aligned history; replay is possible but unsuitable for a trusted production model"
            )
        if quality_counts.get("other"):
            warnings.append(
                "'Other' quality is conditionally usable and remains visible in snapshot quality metadata"
            )
        excluded = sorted(set(quality_counts) - USABLE_QUALITY_VALUES)
        if excluded:
            warnings.append("excluded quality values present: " + ", ".join(excluded))

        return ScadaReplayPreflightReport(
            files_checked=len(csv_paths),
            rows_checked=rows_checked,
            required_tags=required_tags,
            observed_tags=tuple(sorted(observed_tags)),
            missing_tags=missing_tags,
            aligned_hour_count=len(aligned_snapshots),
            ready=not blockers,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
            quality_counts=dict(sorted(quality_counts.items())),
            conditional_hour_count=conditional_hours,
            degraded_hour_count=degraded_hours,
        )
