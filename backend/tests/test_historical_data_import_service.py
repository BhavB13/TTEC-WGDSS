from dataclasses import dataclass
from pathlib import Path

import pytest

from app.services.historical_data_import_service import (
    HistoricalDataImportService,
    HistoricalImportReport,
)


@dataclass
class FutureDatasetAdapter:
    adapter_id: str = "future_weather_grid_v2"

    def can_handle(self, source: Path) -> bool:
        return source.suffix == ".future"

    def validate(self, source: Path) -> list[str]:
        if "timestamp,demand,temperature" not in source.read_text():
            raise ValueError("future dataset schema mismatch")
        return []

    def import_dataset(self, source: Path) -> HistoricalImportReport:
        self.validate(source)
        return HistoricalImportReport(
            adapter_id=self.adapter_id,
            source_filename=source.name,
            source_hash="test-hash",
            imported=True,
            skipped_duplicate=False,
            row_count=1,
            validation_status="VALID",
            schema_mapping={"timestamp": "timestamp", "demand": "demand_mw"},
            next_actions=["Rebuild chronological forecast dataset"],
        )


def test_historical_import_registry_accepts_future_adapter(tmp_path):
    source = tmp_path / "new-source.future"
    source.write_text("timestamp,demand,temperature\n2026-01-01,900,30\n")
    service = HistoricalDataImportService(adapters=[])
    service.register(FutureDatasetAdapter())

    result = service.import_dataset(source)

    assert result.adapter_id == "future_weather_grid_v2"
    assert result.validation_status == "VALID"
    assert result.schema_mapping["demand"] == "demand_mw"
    assert "forecast" in result.next_actions[0].lower()


def test_historical_import_registry_rejects_duplicate_adapter():
    adapter = FutureDatasetAdapter()
    service = HistoricalDataImportService(adapters=[adapter])

    with pytest.raises(ValueError, match="already registered"):
        service.register(FutureDatasetAdapter())


def test_historical_import_registry_rejects_unknown_format(tmp_path):
    source = tmp_path / "unknown.bin"
    source.write_bytes(b"not a supported dataset")

    with pytest.raises(ValueError, match="No historical data adapter"):
        HistoricalDataImportService(adapters=[]).import_dataset(source)
