from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.demand_forecast import ScadaReplayForecastResult
from app.models.scada import ScadaGridSnapshot
from app.services.frozen_snapshot_model_service import FrozenSnapshotModelService
from app.services.scada_replay_forecast_service import ScadaReplayForecastService


@dataclass(frozen=True)
class IssuedRiskHorizon:
    horizon_hours: int
    forecast_timestamp: datetime
    forecast_demand_mw: float
    forecast_uncertainty_mw: float
    current_tra_held_mw: float
    required_reserve_mw: float
    generation_need_probability: float


@dataclass(frozen=True)
class OperationalForecastIssue:
    status: str
    issue_time: datetime
    data_mode: str
    source_provider: str
    source_observation_time: datetime | None
    source_available_at: datetime | None
    model_version: str | None
    artifact_hash: str | None
    training_end_at: datetime | None
    horizons: tuple[IssuedRiskHorizon, ...]
    warnings: tuple[str, ...]


class OperationalForecastOrchestrator:
    """Issue one frozen forecast/risk calculation for a complete source boundary."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def issue(
        self,
        issue_time: datetime,
        *,
        data_mode: str,
        source_provider: str,
    ) -> OperationalForecastIssue:
        artifact_path = settings.FROZEN_DEMAND_MODEL_ARTIFACT_PATH.strip()
        metadata = FrozenSnapshotModelService(artifact_path or None).metadata()
        if metadata.status != "READY":
            return self._unavailable(
                issue_time,
                data_mode,
                source_provider,
                f"Frozen model unavailable: {metadata.status}",
            )
        snapshot = self._snapshot_as_of(issue_time)
        if (
            snapshot is None
            or snapshot.online_capacity_mw is None
            or snapshot.quality_status not in {"GOOD", "USABLE_WITH_WARNING"}
        ):
            return self._unavailable(
                issue_time,
                data_mode,
                source_provider,
                "Current TRA is missing, stale, or not quality-accepted",
                metadata=metadata,
                snapshot=snapshot,
            )
        ScadaReplayForecastService(
            session_factory=self.session_factory
        ).refresh(
            issue_time,
            source_provider=source_provider,
            data_mode=data_mode,
        )
        forecasts = self._forecasts(issue_time)
        horizons = tuple(
            _risk_horizon(row, snapshot.online_capacity_mw)
            for row in forecasts
        )
        if not horizons:
            return self._unavailable(
                issue_time,
                data_mode,
                source_provider,
                "No frozen forecast horizons were issued",
                metadata=metadata,
                snapshot=snapshot,
            )
        return OperationalForecastIssue(
            status="READY",
            issue_time=issue_time,
            data_mode=data_mode,
            source_provider=source_provider,
            source_observation_time=snapshot.timestamp,
            source_available_at=snapshot.available_at,
            model_version=metadata.model_version,
            artifact_hash=metadata.artifact_hash,
            training_end_at=metadata.training_end_at,
            horizons=horizons,
            warnings=tuple(metadata.warnings),
        )

    def _snapshot_as_of(self, issue_time: datetime) -> ScadaGridSnapshot | None:
        with self.session_factory() as session:
            return session.scalar(
                select(ScadaGridSnapshot)
                .where(
                    ScadaGridSnapshot.timestamp <= _naive(issue_time),
                    ScadaGridSnapshot.available_at <= _naive(issue_time),
                )
                .order_by(ScadaGridSnapshot.timestamp.desc())
                .limit(1)
            )

    def _forecasts(self, issue_time: datetime) -> list[ScadaReplayForecastResult]:
        with self.session_factory() as session:
            return list(
                session.scalars(
                    select(ScadaReplayForecastResult)
                    .where(
                        ScadaReplayForecastResult.source_cursor_at
                        == _naive(issue_time)
                    )
                    .order_by(ScadaReplayForecastResult.horizon_hours)
                )
            )

    @staticmethod
    def _unavailable(
        issue_time,
        data_mode,
        source_provider,
        warning,
        *,
        metadata=None,
        snapshot=None,
    ):
        return OperationalForecastIssue(
            status="UNAVAILABLE",
            issue_time=issue_time,
            data_mode=data_mode,
            source_provider=source_provider,
            source_observation_time=snapshot.timestamp if snapshot else None,
            source_available_at=snapshot.available_at if snapshot else None,
            model_version=metadata.model_version if metadata else None,
            artifact_hash=metadata.artifact_hash if metadata else None,
            training_end_at=metadata.training_end_at if metadata else None,
            horizons=(),
            warnings=(warning,),
        )


def _risk_horizon(
    forecast: ScadaReplayForecastResult,
    current_tra_mw: float,
) -> IssuedRiskHorizon:
    sigma = max(1e-6, forecast.forecast_uncertainty_mw)
    safe_capacity = current_tra_mw - settings.CAPACITY_RISK_REQUIRED_RESERVE_MW
    z_score = (safe_capacity - forecast.forecast_demand_mw) / sigma
    probability = 0.5 * math.erfc(z_score / math.sqrt(2.0))
    return IssuedRiskHorizon(
        horizon_hours=forecast.horizon_hours,
        forecast_timestamp=forecast.forecast_timestamp,
        forecast_demand_mw=forecast.forecast_demand_mw,
        forecast_uncertainty_mw=forecast.forecast_uncertainty_mw,
        current_tra_held_mw=current_tra_mw,
        required_reserve_mw=settings.CAPACITY_RISK_REQUIRED_RESERVE_MW,
        generation_need_probability=round(max(0.0, min(1.0, probability)), 6),
    )


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None)
