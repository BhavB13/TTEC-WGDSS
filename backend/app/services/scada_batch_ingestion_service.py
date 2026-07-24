from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.scada import ScadaGridSnapshot
from app.services.scada_archive_service import ScadaArchiveService
from app.services.scada_import_service import ScadaImportService
from app.services.scada_snapshot_service import ScadaSnapshotService


@dataclass(frozen=True)
class BatchFileResult:
    filename: str
    status: str
    detail: str


@dataclass(frozen=True)
class ScadaBatchRunResult:
    run_at: str
    mode: str
    input_directory: str
    prior_watermark: str | None
    latest_complete_watermark: str | None
    watermark_advanced: bool
    forecast_issued: bool
    forecast_status: str
    files: tuple[BatchFileResult, ...]


class ScadaBatchIngestionService:
    """Process stable periodic exports; this is not a continuous SCADA stream."""

    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        input_directory: str | Path | None = None,
        state_path: str | Path | None = None,
        stable_seconds: int | None = None,
        clock: Callable[[], datetime] | None = None,
        on_watermark_advanced: Callable[[datetime], object] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.input_directory = Path(
            input_directory or settings.SCADA_BATCH_INPUT_DIR
        )
        self.state_path = Path(state_path or settings.SCADA_BATCH_STATE_PATH)
        self.stable_seconds = (
            settings.SCADA_BATCH_FILE_STABLE_SECONDS
            if stable_seconds is None
            else stable_seconds
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.on_watermark_advanced = on_watermark_advanced

    def run(self) -> ScadaBatchRunResult:
        now = self.clock()
        self.input_directory.mkdir(parents=True, exist_ok=True)
        state = self._load_state()
        prior_watermark = _parse_datetime(state.get("watermark"))
        processed = set(state.get("processed_files", []))
        results: list[BatchFileResult] = []
        imported_any = False
        for path in sorted(self.input_directory.iterdir(), key=lambda item: item.name):
            if not path.is_file() or path.suffix.lower() not in {".csv", ".zip"}:
                continue
            signature = f"{path.name}:{path.stat().st_size}:{path.stat().st_mtime_ns}"
            if signature in processed:
                results.append(BatchFileResult(path.name, "UNCHANGED", "Already processed"))
                continue
            age = now.timestamp() - path.stat().st_mtime
            if age < self.stable_seconds:
                results.append(
                    BatchFileResult(
                        path.name,
                        "DEFERRED",
                        f"File has not been stable for {self.stable_seconds} seconds",
                    )
                )
                continue
            try:
                if path.suffix.lower() == ".zip":
                    imported = ScadaArchiveService(
                        session_factory=self.session_factory
                    ).import_archive(path)
                    changed = not imported.skipped_duplicate
                else:
                    imported = ScadaImportService(
                        session_factory=self.session_factory
                    ).import_csv(path)
                    changed = imported.imported
                processed.add(signature)
                imported_any = imported_any or changed
                results.append(
                    BatchFileResult(
                        path.name,
                        "IMPORTED" if changed else "DUPLICATE",
                        "Hash-idempotent import completed",
                    )
                )
            except Exception as exc:
                results.append(BatchFileResult(path.name, "FAILED", str(exc)))

        if imported_any:
            ScadaSnapshotService(
                session_factory=self.session_factory
            ).build_hourly_snapshots(replace_existing=True)
        watermark = self._latest_complete_watermark()
        advanced = watermark is not None and (
            prior_watermark is None or _naive(watermark) > _naive(prior_watermark)
        )
        forecast_issued = False
        forecast_status = "NOT_REQUESTED"
        if advanced and self.on_watermark_advanced is not None:
            issued = self.on_watermark_advanced(watermark)
            forecast_status = str(getattr(issued, "status", "READY"))
            forecast_issued = forecast_status == "READY"
        result = ScadaBatchRunResult(
            run_at=now.isoformat(),
            mode="BATCH_SCADA_EXPORT",
            input_directory=str(self.input_directory),
            prior_watermark=prior_watermark.isoformat() if prior_watermark else None,
            latest_complete_watermark=watermark.isoformat() if watermark else None,
            watermark_advanced=advanced,
            forecast_issued=forecast_issued,
            forecast_status=forecast_status,
            files=tuple(results),
        )
        self._save_state(
            {
                "schema": "wgdss-scada-batch-state-v1",
                "watermark": result.latest_complete_watermark,
                "processed_files": sorted(processed),
                "last_run": asdict(result),
            }
        )
        return result

    def _latest_complete_watermark(self) -> datetime | None:
        with self.session_factory() as session:
            return session.scalar(
                select(ScadaGridSnapshot.timestamp)
                .where(
                    ScadaGridSnapshot.quality_status.in_(
                        ("GOOD", "USABLE_WITH_WARNING")
                    ),
                    ScadaGridSnapshot.current_demand_mw.is_not(None),
                    ScadaGridSnapshot.online_capacity_mw.is_not(None),
                )
                .order_by(ScadaGridSnapshot.timestamp.desc())
                .limit(1)
            )

    def _load_state(self) -> dict[str, object]:
        if not self.state_path.is_file():
            return {}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save_state(self, state: dict[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None)
