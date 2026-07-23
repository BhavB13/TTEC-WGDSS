from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.providers.excel_snapshot_scada_provider import (
    ExcelSnapshotScadaProvider,
    SnapshotMissingRequiredVariablesError,
    TRINIDAD_TZ,
)


HEADERS = [
    "Pen Index",
    "Name",
    "Start Time",
    "End Time",
    "Min Time",
    "Min Value",
    "Max Time",
    "Max Value",
    "Avg Value",
    "Quality",
]
TAGS = {
    "load.csv": ("PTL132 GENERATION TOTALS", 1000.0),
    "temp.csv": ("MHO132 TRINIDAD AVERAGE AMBIENT TEMP", 31.0),
    "spin.csv": ("GSYS SYSTEM_CORRECTED_SPIN_TOTAL", 75.0),
    "tra.csv": ("GSYS SYSTEM_ONLN_TOTAL", 1180.0),
}


def _archive(path: Path, *, include_ta: bool = False, duplicate: bool = False) -> Path:
    tags = dict(TAGS)
    if include_ta:
        tags["ta.csv"] = ("GSYS SYSTEM_AVAIL_TOTAL", 1350.0)
    with ZipFile(path, "w") as archive:
        for filename, (tag, base) in tags.items():
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(HEADERS)
            rows = [
                [1, tag, "07/23/2026 00:00", "07/23/2026 00:37", "", base, "", base, base, "Good"],
                [2, tag, "07/23/2026 00:37", "07/23/2026 01:15", "", base + 10, "", base + 10, base + 10, "Good"],
            ]
            writer.writerows(rows)
            if duplicate:
                writer.writerow(rows[-1])
            archive.writestr(filename, output.getvalue())
    return path


def test_snapshot_aligns_irregular_intervals_and_reports_missing_ta(tmp_path: Path):
    source = _archive(tmp_path / "snapshot.zip")
    result = ExcelSnapshotScadaProvider(
        source,
        imported_at=datetime(2026, 7, 23, 12, tzinfo=TRINIDAD_TZ),
    ).load_snapshot()

    assert result.summary.latest_valid_timestamp == datetime(
        2026, 7, 23, 1, 15, tzinfo=TRINIDAD_TZ
    )
    assert result.summary.missing_required_variables == ["available_capacity_ta_mw"]
    assert len(result.summary.hourly_series) == 2
    # 37 minutes at 1000 MW and 23 minutes at 1010 MW.
    assert result.summary.hourly_series[0].demand_mw == pytest.approx(1003.8333)
    assert result.summary.source_file_hash


def test_snapshot_deduplicates_and_grid_contract_fails_closed_without_ta(
    tmp_path: Path,
):
    provider = ExcelSnapshotScadaProvider(
        _archive(tmp_path / "snapshot.zip", duplicate=True),
        imported_at=datetime(2026, 7, 23, 12, tzinfo=TRINIDAD_TZ),
    )
    result = provider.load_snapshot()
    assert result.summary.duplicate_record_count == 4
    with pytest.raises(SnapshotMissingRequiredVariablesError):
        import asyncio

        asyncio.run(provider.get_grid_status())


def test_snapshot_source_is_not_modified(tmp_path: Path):
    source = _archive(tmp_path / "snapshot.zip", include_ta=True)
    before = source.read_bytes()
    provider = ExcelSnapshotScadaProvider(
        source,
        imported_at=datetime(2026, 7, 23, 12, tzinfo=TRINIDAD_TZ),
    )
    result = provider.load_snapshot()
    assert source.read_bytes() == before
    assert not result.summary.missing_required_variables
