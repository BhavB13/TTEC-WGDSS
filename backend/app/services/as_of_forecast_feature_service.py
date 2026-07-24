from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.models.demand_forecast import ForecastTrainingRow
from app.models.scada import ScadaGridSnapshot
from app.services.forecast_dataset_service import ForecastDatasetService


@dataclass(frozen=True)
class AsOfFeatureDiagnostics:
    status: str
    issue_time: datetime
    source_provider: str
    data_mode: str
    source_snapshot_count: int
    training_row_count: int
    inference_horizons: tuple[int, ...]
    feature_fingerprint: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AsOfForecastFeatures:
    training_rows: list[ForecastTrainingRow]
    inference_rows: dict[int, ForecastTrainingRow]
    diagnostics: AsOfFeatureDiagnostics


class AsOfForecastFeatureService:
    """Canonical cutoff-safe feature entry point for replay and operational runs."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory
        self.dataset_service = ForecastDatasetService(session_factory=session_factory)

    def build(
        self,
        issue_time: datetime,
        *,
        source_provider: str,
        data_mode: str,
        include_training_rows: bool = True,
    ) -> AsOfForecastFeatures:
        if include_training_rows:
            dataset = self.dataset_service.build_evaluation_dataset(issue_time)
            training_rows = dataset.rows
            inference_rows = dataset.inference_rows
            source_snapshots = dataset.source_snapshots
        else:
            training_rows = []
            inference_rows = self.dataset_service.build_inference_rows(
                as_of=issue_time
            )
            source_snapshots = self._source_snapshot_count(issue_time)
        warnings: list[str] = []
        for horizon, row in inference_rows.items():
            available_at = row.feature_available_at or row.feature_timestamp
            if _naive(available_at) > _naive(issue_time):
                raise ValueError(
                    f"+{horizon}h feature is not available at the issue time"
                )
            if (
                row.forecast_weather_issued_at is not None
                and _naive(row.forecast_weather_issued_at) > _naive(issue_time)
            ):
                raise ValueError(
                    f"+{horizon}h weather forecast was issued after the issue time"
                )
            if row.source_quality_status.upper() != "GOOD":
                warnings.append(
                    f"+{horizon}h input quality is {row.source_quality_status}"
                )
        if not inference_rows:
            warnings.append("No complete inference boundary is available")
        fingerprint = _fingerprint(inference_rows)
        diagnostics = AsOfFeatureDiagnostics(
            status="READY" if inference_rows else "UNAVAILABLE",
            issue_time=issue_time,
            source_provider=source_provider,
            data_mode=data_mode,
            source_snapshot_count=source_snapshots,
            training_row_count=len(training_rows),
            inference_horizons=tuple(sorted(inference_rows)),
            feature_fingerprint=fingerprint,
            warnings=tuple(dict.fromkeys(warnings)),
        )
        return AsOfForecastFeatures(
            training_rows=training_rows,
            inference_rows=inference_rows,
            diagnostics=diagnostics,
        )

    def _source_snapshot_count(self, issue_time: datetime) -> int:
        with self.session_factory() as session:
            return int(
                session.scalar(
                    select(func.count(ScadaGridSnapshot.id)).where(
                        ScadaGridSnapshot.timestamp <= _naive(issue_time),
                        ScadaGridSnapshot.available_at <= _naive(issue_time),
                    )
                )
                or 0
            )


def _fingerprint(rows: dict[int, ForecastTrainingRow]) -> str:
    payload = [
        {
            "horizon": horizon,
            "feature_timestamp": row.feature_timestamp.isoformat(),
            "feature_available_at": (
                row.feature_available_at.isoformat()
                if row.feature_available_at is not None
                else None
            ),
            "target_timestamp": row.target_timestamp.isoformat(),
            "current_demand_mw": row.current_demand_mw,
            "quality": row.source_quality_status,
            "forecast_weather_issued_at": (
                row.forecast_weather_issued_at.isoformat()
                if row.forecast_weather_issued_at is not None
                else None
            ),
        }
        for horizon, row in sorted(rows.items())
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None)
