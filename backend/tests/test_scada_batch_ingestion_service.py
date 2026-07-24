import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.scada_batch_ingestion_service import ScadaBatchIngestionService


def test_batch_defers_changing_file(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    source = inbox / "latest.csv"
    source.write_text("still changing", encoding="utf-8")
    now = datetime.now(timezone.utc)

    result = ScadaBatchIngestionService(
        input_directory=inbox,
        state_path=tmp_path / "state.json",
        stable_seconds=60,
        clock=lambda: now,
    ).run()

    assert result.files[0].status == "DEFERRED"
    assert result.mode == "BATCH_SCADA_EXPORT"
    assert result.forecast_issued is False


def test_batch_processes_stable_file_once_and_advances_once(monkeypatch, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    source = inbox / "latest.csv"
    source.write_text("stable", encoding="utf-8")
    now = datetime.now(timezone.utc)
    old = (now - timedelta(minutes=5)).timestamp()
    os.utime(source, (old, old))
    imported = []
    issued = []

    class FakeImporter:
        def __init__(self, session_factory):
            pass

        def import_csv(self, path):
            imported.append(path.name)
            return SimpleNamespace(imported=True)

    class FakeSnapshots:
        def __init__(self, session_factory):
            pass

        def build_hourly_snapshots(self, replace_existing):
            return None

    monkeypatch.setattr(
        "app.services.scada_batch_ingestion_service.ScadaImportService",
        FakeImporter,
    )
    monkeypatch.setattr(
        "app.services.scada_batch_ingestion_service.ScadaSnapshotService",
        FakeSnapshots,
    )
    service = ScadaBatchIngestionService(
        input_directory=inbox,
        state_path=tmp_path / "state.json",
        stable_seconds=60,
        clock=lambda: now,
        on_watermark_advanced=issued.append,
    )
    watermark = datetime(2026, 7, 23, 12)
    monkeypatch.setattr(service, "_latest_complete_watermark", lambda: watermark)

    first = service.run()
    second = service.run()

    assert imported == ["latest.csv"]
    assert first.watermark_advanced is True
    assert first.forecast_issued is True
    assert second.watermark_advanced is False
    assert second.forecast_issued is False
    assert issued == [watermark]
    assert second.files[0].status == "UNCHANGED"


def test_batch_does_not_claim_forecast_when_orchestrator_fails_closed(
    monkeypatch,
    tmp_path,
):
    service = ScadaBatchIngestionService(
        input_directory=tmp_path / "inbox",
        state_path=tmp_path / "state.json",
        stable_seconds=0,
        on_watermark_advanced=lambda _watermark: SimpleNamespace(
            status="UNAVAILABLE"
        ),
    )
    watermark = datetime(2026, 7, 23, 12)
    monkeypatch.setattr(service, "_latest_complete_watermark", lambda: watermark)

    result = service.run()

    assert result.watermark_advanced is True
    assert result.forecast_issued is False
    assert result.forecast_status == "UNAVAILABLE"
