from __future__ import annotations

import asyncio
import json
import logging
import math
import threading
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select

from app.core.config import settings
from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.demo_replay import DemoObservation, DemoReplayState
from app.models.demand_forecast import ScadaReplayForecastResult
from app.models.scada import ScadaArchiveImportRun, ScadaGridSnapshot
from app.models.weather import Weather
from app.providers.open_meteo_replay_provider import (
    ArchivedForecastResult,
    OpenMeteoReplayProvider,
)
from app.schemas.model_status import (
    BaselineComparisonResponse,
    DemandForecastBundleResponse,
    DemandForecastHorizonResponse,
    ModelMetricsResponse,
    ModelStatusResponse,
    ScadaStatusResponse,
)
from app.schemas.replay import (
    LoadForecastPointResponse,
    MonthlyHistoryPointResponse,
    OperationalTrendPointResponse,
    ReplayControlRequest,
    ReplayDashboardResponse,
    ReplayStatusResponse,
    ReplaySummaryResponse,
)
from app.services.demo_load_forecast_service import (
    DEMO_FORECAST_MODEL_VERSION,
    MIN_REQUIRED_HISTORY_ROWS,
    DemoLoadForecastService,
)
from app.services.risk_probability_engine import (
    OperatingForecastPoint,
    OperatingRiskInput,
    RiskProbabilityEngine,
    risk_result_details,
)
from app.services.weather_service import WeatherService


DEMO_SOURCE = "WGDSS 12-Month Synthetic SCADA/Weather Demonstration"
STATE_ID = 1
TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")
SCADA_REPLAY_SOURCE = "Historical SCADA Replay — June 2026"
logger = logging.getLogger(__name__)


class _WeatherGridObservation(Protocol):
    timestamp: datetime
    demand_mw: float
    generation_mw: float
    spinning_reserve_mw: float
    available_capacity_mw: float
    online_capacity_mw: float
    temperature_c: float
    humidity_percent: float
    rainfall_mm_hr: float
    cloud_cover_percent: float
    wind_speed_kmh: float
    wind_direction_deg: float
    pressure_hpa: float
    quality_status: str
    source: str


class _ReplayWeatherProvider(Protocol):
    def get_forecast_sources(
        self,
        latitude: float,
        longitude: float,
        source_cursor: datetime,
        hours: int = 24,
    ) -> ArchivedForecastResult: ...


@dataclass(frozen=True)
class _ScadaReplayObservation:
    timestamp: datetime
    source_observation_time: datetime
    source_timestamp: datetime
    source_available_at: datetime
    demand_mw: float
    generation_mw: float
    spinning_reserve_mw: float
    available_capacity_mw: float
    online_capacity_mw: float
    temperature_c: float
    humidity_percent: float
    rainfall_mm_hr: float
    cloud_cover_percent: float
    wind_speed_kmh: float
    wind_direction_deg: float
    pressure_hpa: float
    quality_status: str
    source: str
    missing_fields: str = ""
    coverage_percent: float = 0.0
    quality_notes: str = ""
    anomaly_flags: str = "[]"
    field_provenance: str = "{}"
    formula_version: str | None = None
    resampling_method: str = "interval_overlap_hourly"


class DemoReplayService:
    """Own immutable demo history and a separately persisted simulated-live cursor."""

    _lock = threading.Lock()

    def __init__(
        self,
        session_factory=SessionLocal,
        clock: Callable[[], datetime] | None = None,
        replay_weather_provider: _ReplayWeatherProvider | None = None,
        live_weather_service: WeatherService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(TRINIDAD_TZ))
        self.forecast_service = DemoLoadForecastService()
        self.risk_engine = RiskProbabilityEngine()
        self.replay_weather_provider = (
            replay_weather_provider or OpenMeteoReplayProvider()
        )
        self.live_weather_service = live_weather_service
        self._forecast_cache: dict[tuple[datetime, tuple[str, ...]], object] = {}

    def ensure_seeded(self, force: bool = False) -> int:
        if self.session_factory is SessionLocal:
            initialize_database()
        with self._lock, self.session_factory() as session:
            existing = session.scalar(select(func.count(DemoObservation.id))) or 0
            expected = 365 * 24 if not _is_leap_year(settings.DEMO_DATASET_YEAR) else 366 * 24
            if existing == expected and not force:
                state = self._ensure_state(session)
                if not state.clock_aligned:
                    self._sync_state_to_wallclock(state)
                session.commit()
                return int(existing)
            if existing:
                session.execute(delete(DemoReplayState))
                session.execute(delete(DemoObservation))
                session.flush()
            rows = _generate_demo_year(settings.DEMO_DATASET_YEAR)
            session.add_all(rows)
            session.flush()
            self._ensure_state(session)
            session.commit()
            return len(rows)

    def get_dashboard_context(self) -> dict[str, object] | None:
        if not settings.DEMO_REPLAY_ENABLED:
            return None
        self.ensure_seeded()
        with self._lock, self.session_factory() as session:
            state = self._state(session)
            self._advance_if_playing(state)
            observation_timestamp = state.cursor_at.replace(
                minute=0,
                second=0,
                microsecond=0,
            )
            observation = session.scalar(
                select(DemoObservation).where(
                    DemoObservation.timestamp == observation_timestamp
                )
            )
            if observation is None:
                return None
            scada_overlay = self._scada_overlay(session, state)
            forecast_scada_overlay = self._available_scada_overlay(
                scada_overlay,
                state.cursor_at,
            )
            active_observation = scada_overlay.get(observation_timestamp, observation)
            decision_observation = self._decision_observation(
                observation_timestamp,
                observation,
                forecast_scada_overlay,
            )
            replay_forecasts = self._persisted_replay_forecasts(
                session,
                active_observation,
            )
            weather_forecast = self._weather_forecast(
                session,
                state,
                active_observation,
                forecast_scada_overlay,
            )
            archived_weather_active = _has_multi_source_forecast(weather_forecast)
            active_replay_forecasts = (
                [] if archived_weather_active else replay_forecasts
            )
            replay = self._dashboard_bundle(
                session,
                state,
                active_observation,
                weather_forecast,
                scada_overlay,
                forecast_scada_overlay,
                active_replay_forecasts,
            )
            risk_payload = self._operating_risk_payload(
                decision_observation,
                replay,
                active_replay_forecasts,
            )
            demand_forecast = self._replay_demand_forecast_bundle(
                active_observation,
                active_replay_forecasts,
                replay,
            )
            model_status = self._replay_model_status(
                active_replay_forecasts,
                replay,
            )
            scada_status = self._replay_scada_status(session, active_observation)
            session.commit()
        return {
            "weather": _weather_payload(active_observation),
            "forecast": weather_forecast,
            "grid": _grid_payload(active_observation),
            "generation_units": _generation_units(active_observation),
            "replay": replay,
            "risk_payload": risk_payload,
            "demand_forecast": demand_forecast,
            "model_status": model_status,
            "scada_status": scada_status,
        }

    def _operating_risk_payload(
        self,
        observation: _WeatherGridObservation,
        replay: ReplayDashboardResponse,
        replay_forecasts: list[ScadaReplayForecastResult],
    ) -> dict[str, object]:
        future = [
            point
            for point in replay.full_day_load_forecast
            if point.timestamp > observation.timestamp
            and point.timestamp <= observation.timestamp + timedelta(hours=6)
        ]
        profile = self._direct_operating_profile(
            observation,
            replay,
            replay_forecasts,
        )
        if not profile and future:
            first = future[0]
            first_horizon = max(
                1,
                int((first.timestamp - observation.timestamp).total_seconds() / 60),
            )
            for horizon in (20, 30):
                if horizon < first_horizon:
                    fraction = horizon / first_horizon
                    profile.append(
                        OperatingForecastPoint(
                            horizon_minutes=horizon,
                            forecast_demand_mw=(
                                observation.demand_mw
                                + (first.forecast_demand_mw - observation.demand_mw) * fraction
                            ),
                            forecast_uncertainty_mw=max(
                                5.0,
                                first.uncertainty_mw * math.sqrt(fraction),
                            ),
                            weather_effect_mw=first.weather_impact_mw * fraction,
                            confidence=first.weather_confidence,
                            forecast_timestamp=(
                                observation.timestamp + timedelta(minutes=horizon)
                            ),
                            uncertainty_source="CALIBRATED_HISTORICAL_RESIDUALS",
                        )
                    )
            profile.extend(
                OperatingForecastPoint(
                    horizon_minutes=int(
                        (point.timestamp - observation.timestamp).total_seconds() / 60
                    ),
                    forecast_demand_mw=point.forecast_demand_mw,
                    forecast_uncertainty_mw=point.uncertainty_mw,
                    weather_effect_mw=point.weather_impact_mw,
                    confidence=point.weather_confidence,
                    forecast_timestamp=point.timestamp,
                    uncertainty_source="CALIBRATED_HISTORICAL_RESIDUALS",
                )
                for point in future
            )
        if not profile:
            profile.append(
                OperatingForecastPoint(
                    horizon_minutes=60,
                    forecast_demand_mw=observation.demand_mw,
                    forecast_uncertainty_mw=(
                        replay.summary.residual_std_mw
                        if replay.summary.residual_std_mw > 0
                        else None
                    ),
                    confidence=0.5,
                    forecast_timestamp=observation.timestamp + timedelta(hours=1),
                    uncertainty_source="CALIBRATED_HISTORICAL_RESIDUALS",
                )
            )

        risk = self.risk_engine.evaluate(
            OperatingRiskInput(
                forecast_demand_mw=profile[0].forecast_demand_mw,
                forecast_uncertainty_mw=profile[0].forecast_uncertainty_mw,
                current_demand_mw=observation.demand_mw,
                online_capacity_mw=observation.online_capacity_mw,
                available_capacity_mw=observation.available_capacity_mw,
                spinning_reserve_mw=observation.spinning_reserve_mw,
                historical_validation_mae_mw=(
                    replay.summary.forecast_mae_mw
                    if replay.summary.forecast_mae_mw > 0
                    else None
                ),
                historical_validation_rmse_mw=(
                    replay.summary.residual_std_mw
                    if replay.summary.residual_std_mw > 0
                    else None
                ),
                forecast_profile=tuple(profile),
                available_capacity_is_verified=(
                    isinstance(observation, _ScadaReplayObservation)
                    and not _has_missing_operating_capacity(observation.missing_fields)
                ),
                data_quality_status=observation.quality_status,
                data_quality_warnings=tuple(
                    warning
                    for warning in (
                        getattr(observation, "quality_notes", ""),
                        *_json_string_list(
                            getattr(observation, "anomaly_flags", "[]")
                        ),
                    )
                    if warning
                ),
            )
        )
        forecast_30 = min(profile, key=lambda point: abs(point.horizon_minutes - 30))
        forecast_60 = min(profile, key=lambda point: abs(point.horizon_minutes - 60))
        return {
            "engine_version": risk.engine_version,
            "policy_status": risk.policy_status,
            "probability_score": risk.probability_score,
            "risk_level": risk.risk_level,
            "forecast_demand_30m": round(forecast_30.forecast_demand_mw, 2),
            "forecast_demand_60m": round(forecast_60.forecast_demand_mw, 2),
            "recommendation": risk.recommendation,
            "factors": risk.reasons,
            "reason": "; ".join(risk.reasons),
            **risk_result_details(risk),
        }

    @staticmethod
    def _direct_operating_profile(
        observation: _WeatherGridObservation,
        replay: ReplayDashboardResponse,
        replay_forecasts: list[ScadaReplayForecastResult],
    ) -> list[OperatingForecastPoint]:
        if not replay_forecasts:
            return []
        replay_by_timestamp = {
            point.timestamp: point for point in replay.full_day_load_forecast
        }
        profile: list[OperatingForecastPoint] = []
        for row in sorted(replay_forecasts, key=lambda item: item.horizon_hours):
            display_timestamp = observation.timestamp + timedelta(
                hours=row.horizon_hours
            )
            display_point = replay_by_timestamp.get(display_timestamp)
            profile.append(
                OperatingForecastPoint(
                    horizon_minutes=row.horizon_hours * 60,
                    forecast_demand_mw=row.forecast_demand_mw,
                    forecast_uncertainty_mw=row.forecast_uncertainty_mw,
                    weather_effect_mw=(
                        display_point.weather_impact_mw
                        if display_point is not None
                        else 0.0
                    ),
                    confidence=_replay_forecast_confidence(row),
                    forecast_timestamp=display_timestamp,
                    confidence_lower_mw=row.confidence_lower_mw,
                    confidence_upper_mw=row.confidence_upper_mw,
                    confidence_level=row.confidence_level,
                    uncertainty_source="CALIBRATED_HISTORICAL_RESIDUALS",
                )
            )
        first = profile[0]
        for horizon in (20, 30):
            if horizon >= first.horizon_minutes:
                continue
            fraction = horizon / first.horizon_minutes
            profile.append(
                OperatingForecastPoint(
                    horizon_minutes=horizon,
                    forecast_demand_mw=(
                        observation.demand_mw
                        + (first.forecast_demand_mw - observation.demand_mw)
                        * fraction
                    ),
                    forecast_uncertainty_mw=max(
                        5.0,
                        first.forecast_uncertainty_mw * math.sqrt(fraction),
                    ),
                    weather_effect_mw=first.weather_effect_mw * fraction,
                    confidence=first.confidence,
                    forecast_timestamp=(
                        observation.timestamp + timedelta(minutes=horizon)
                    ),
                    uncertainty_source="CALIBRATED_HISTORICAL_RESIDUALS",
                )
            )
        return sorted(profile, key=lambda point: point.horizon_minutes)

    @staticmethod
    def _persisted_replay_forecasts(
        session,
        observation: _WeatherGridObservation,
    ) -> list[ScadaReplayForecastResult]:
        if not isinstance(observation, _ScadaReplayObservation):
            return []
        source_cursor = observation.source_timestamp.replace(tzinfo=None)
        rows = list(
            session.scalars(
                select(ScadaReplayForecastResult)
                .where(ScadaReplayForecastResult.source_cursor_at == source_cursor)
                .order_by(ScadaReplayForecastResult.horizon_hours)
            )
        )
        valid: list[ScadaReplayForecastResult] = []
        for row in rows:
            expected_target = source_cursor + timedelta(hours=row.horizon_hours)
            if (
                row.horizon_hours in {1, 2, 3, 4, 5, 6}
                and row.feature_timestamp == source_cursor
                and row.forecast_timestamp == expected_target
            ):
                valid.append(row)
        # New refreshes contain every direct 1-6h horizon. Older replay stores
        # may contain only 1h, 2h, and 6h; keep those usable during migration.
        return valid if 1 in {row.horizon_hours for row in valid} else []

    @staticmethod
    def _replay_demand_forecast_bundle(
        observation: _WeatherGridObservation,
        replay_forecasts: list[ScadaReplayForecastResult],
        replay: ReplayDashboardResponse,
    ) -> DemandForecastBundleResponse:
        if not replay_forecasts:
            chart_by_timestamp = {
                point.timestamp: point for point in replay.full_day_load_forecast
            }
            fallback_horizons: list[DemandForecastHorizonResponse] = []
            for horizon in (1, 2, 3, 4, 5, 6):
                target = observation.timestamp + timedelta(hours=horizon)
                point = chart_by_timestamp.get(target)
                if point is None:
                    continue
                fallback_horizons.append(
                    DemandForecastHorizonResponse(
                        horizon_hours=horizon,
                        forecast_timestamp=target,
                        forecast_demand_mw=point.forecast_demand_mw,
                        forecast_uncertainty_mw=point.uncertainty_mw,
                        model_name=replay.summary.forecast_model,
                        model_version=DEMO_FORECAST_MODEL_VERSION,
                        baseline_name="HourlyHistoricalAverage",
                        baseline_forecast_mw=point.historical_average_mw,
                        quality_status=replay.summary.forecast_mode,
                        feature_timestamp=observation.timestamp,
                        feature_profile="replay_weather_load_state_v4",
                        validation_status="PROTOTYPE",
                        training_rows=replay.summary.training_rows,
                    )
                )
            return DemandForecastBundleResponse(horizons=fallback_horizons)
        return DemandForecastBundleResponse(
            horizons=[
                DemandForecastHorizonResponse(
                    horizon_hours=row.horizon_hours,
                    forecast_timestamp=(
                        observation.timestamp + timedelta(hours=row.horizon_hours)
                    ),
                    forecast_demand_mw=row.forecast_demand_mw,
                    forecast_uncertainty_mw=row.forecast_uncertainty_mw,
                    model_name=row.model_name,
                    model_version=row.model_version,
                    baseline_name=row.baseline_name,
                    baseline_forecast_mw=row.baseline_forecast_mw,
                    quality_status=row.quality_status,
                    feature_timestamp=observation.timestamp,
                    generated_at=row.generated_at,
                    feature_profile=row.feature_profile,
                    validation_status=row.validation_status,
                    training_rows=row.training_rows,
                    confidence_lower_mw=row.confidence_lower_mw,
                    confidence_upper_mw=row.confidence_upper_mw,
                    confidence_level=row.confidence_level,
                    p10_demand_mw=(
                        row.p10_demand_mw
                        if row.p10_demand_mw > 0
                        else row.confidence_lower_mw
                    ),
                    p50_demand_mw=(
                        row.p50_demand_mw
                        if row.p50_demand_mw > 0
                        else row.forecast_demand_mw
                    ),
                    p90_demand_mw=(
                        row.p90_demand_mw
                        if row.p90_demand_mw > 0
                        else row.confidence_upper_mw
                    ),
                    training_start_at=row.training_start_at,
                    training_end_at=row.training_end_at,
                    feature_importance=_json_float_object(row.feature_importance),
                    fallback_reason=row.fallback_reason,
                    temperature_load_correlation=(
                        row.temperature_load_correlation
                    ),
                    similar_period_forecast_mw=row.similar_period_forecast_mw,
                    similar_examples=_json_list(row.similar_examples),
                    contributing_factors=_json_string_list(
                        row.contributing_factors
                    ),
                    mae=row.mae,
                    rmse=row.rmse,
                    mape=row.mape,
                    residual_std=row.residual_std,
                )
                for row in replay_forecasts
            ]
        )

    @staticmethod
    def _replay_model_status(
        replay_forecasts: list[ScadaReplayForecastResult],
        replay: ReplayDashboardResponse,
    ) -> ModelStatusResponse:
        if not replay_forecasts:
            return ModelStatusResponse(
                active_model=replay.summary.forecast_model,
                model_version=DEMO_FORECAST_MODEL_VERSION,
                mode=replay.summary.forecast_mode,
                trained_through=(
                    replay.summary.forecast_trained_through
                    or replay.status.cursor_at
                ),
                feature_profile="replay_weather_load_state_v4",
                validation_status="PROTOTYPE",
                train_row_count=replay.summary.training_rows,
                test_row_count=0,
                metrics=ModelMetricsResponse(
                    mae=replay.summary.forecast_mae_mw,
                    residual_std=replay.summary.residual_std_mw,
                ),
                baseline_comparison=BaselineComparisonResponse(
                    best_baseline="HourlyHistoricalAverage",
                    ml_beats_baseline=(replay.summary.forecast_mode == "ML_ACTIVE"),
                ),
            )
        primary = min(replay_forecasts, key=lambda row: row.horizon_hours)
        return ModelStatusResponse(
            active_model=primary.model_name,
            model_version=primary.model_version,
            mode=primary.quality_status,
            trained_through=primary.feature_timestamp,
            generated_at=primary.generated_at,
            feature_profile=primary.feature_profile,
            validation_status=primary.validation_status,
            training_span_hours=primary.training_span_hours,
            train_row_count=primary.train_row_count,
            test_row_count=primary.test_row_count,
            candidate_metrics=_json_object(primary.candidate_metrics),
            metrics=ModelMetricsResponse(
                mae=primary.mae,
                rmse=primary.rmse,
                mape=primary.mape,
                residual_std=primary.residual_std,
            ),
            baseline_comparison=BaselineComparisonResponse(
                best_baseline=primary.baseline_name,
                ml_beats_baseline=primary.ml_beats_baseline,
            ),
        )

    def _replay_scada_status(
        self,
        session,
        observation: _WeatherGridObservation,
    ) -> ScadaStatusResponse | None:
        if not isinstance(observation, _ScadaReplayObservation):
            return None
        archive = session.scalar(
            select(ScadaArchiveImportRun)
            .where(
                ScadaArchiveImportRun.data_start_at
                <= observation.source_timestamp,
                ScadaArchiveImportRun.data_end_at
                >= observation.source_timestamp,
            )
            .order_by(ScadaArchiveImportRun.imported_at.desc())
        )
        archive_report = _json_object(archive.validation_report) if archive else {}
        alignment = archive_report.get("alignment_validation")
        alignment = alignment if isinstance(alignment, dict) else {}
        method_metrics = alignment.get("method_metrics")
        return ScadaStatusResponse(
            mode="historical_replay",
            source=observation.source,
            aggregation=observation.resampling_method,
            latest_snapshot=observation.source_observation_time,
            available_at=observation.source_available_at,
            quality_status=observation.quality_status,
            missing_fields=observation.missing_fields,
            coverage_percent=observation.coverage_percent,
            quality_notes="; ".join(
                value
                for value in (
                    "Historical interval-aligned SCADA replay; not live telemetry",
                    observation.quality_notes,
                )
                if value
            ),
            anomaly_flags=_json_string_list(observation.anomaly_flags),
            field_provenance=_json_object(observation.field_provenance),
            formula_version=observation.formula_version,
            archive_source=archive.source_filename if archive else None,
            archive_import_status=archive.import_status if archive else None,
            archive_validation_status=(
                str(archive_report.get("validation_status"))
                if archive_report.get("validation_status")
                else None
            ),
            archive_data_start_at=archive.data_start_at if archive else None,
            archive_data_end_at=archive.data_end_at if archive else None,
            alignment_validation_status=(
                str(alignment.get("validation_status"))
                if alignment.get("validation_status")
                else None
            ),
            alignment_selected_method=(
                str(alignment.get("selected_method"))
                if alignment.get("selected_method")
                else None
            ),
            alignment_mismatch_count=(
                int(alignment.get("mismatch_count", 0)) if alignment else None
            ),
            alignment_method_metrics=(
                [item for item in method_metrics if isinstance(item, dict)]
                if isinstance(method_metrics, list)
                else []
            ),
        )

    def get_status(self) -> ReplayStatusResponse:
        self.ensure_seeded()
        with self._lock, self.session_factory() as session:
            state = self._state(session)
            self._advance_if_playing(state)
            status = self._status(session, state)
            session.commit()
            return status

    def control(self, request: ReplayControlRequest) -> ReplayStatusResponse:
        self.ensure_seeded()
        with self._lock, self.session_factory() as session:
            state = self._state(session)
            self._advance_if_playing(state)
            if request.step_minutes is not None:
                state.step_minutes = request.step_minutes
            if request.speed_multiplier is not None:
                state.speed_multiplier = request.speed_multiplier
            now = _utc_now_naive()
            if request.action == "play":
                state.is_playing = True
                state.last_wallclock_at = now
            elif request.action == "pause":
                state.is_playing = False
                state.last_wallclock_at = None
            elif request.action == "reset":
                self._sync_state_to_wallclock(state)
            elif request.action == "step":
                state.cursor_at = min(
                    state.replay_end,
                    state.cursor_at + timedelta(minutes=state.step_minutes),
                )
                if state.cursor_at >= state.replay_end:
                    state.is_playing = False
            elif request.action == "configure" and state.is_playing:
                state.last_wallclock_at = now
            session.commit()
            return self._status(session, state)

    @staticmethod
    def _scada_overlay(
        session,
        state: DemoReplayState,
    ) -> dict[datetime, _ScadaReplayObservation]:
        snapshots = list(
            session.scalars(
                select(ScadaGridSnapshot).order_by(ScadaGridSnapshot.timestamp)
            )
        )
        matching = [
            snapshot
            for snapshot in snapshots
            if snapshot.timestamp.month == settings.DEMO_REPLAY_MONTH
            and snapshot.quality_status in {"GOOD", "USABLE_WITH_WARNING"}
            and not snapshot.missing_fields.strip()
            and all(
                value is not None
                for value in (
                    snapshot.current_demand_mw,
                    snapshot.temperature_c,
                    snapshot.spinning_reserve_mw,
                    snapshot.available_capacity_mw,
                    snapshot.online_capacity_mw,
                )
            )
        ]
        if not matching:
            return {}
        source_year = max(
            snapshot.timestamp.year
            for snapshot in matching
        )
        matching = [
            snapshot
            for snapshot in matching
            if snapshot.timestamp.year == source_year
        ]
        demo_rows = {
            row.timestamp: row
            for row in session.scalars(
                select(DemoObservation).where(
                    DemoObservation.timestamp >= state.replay_start,
                    DemoObservation.timestamp <= state.replay_end,
                )
            )
        }
        weather_by_hour: dict[datetime, Weather] = {}
        for weather in session.scalars(
            select(Weather).order_by(Weather.timestamp, Weather.created_at)
        ):
            timestamp = weather.timestamp.replace(
                minute=0,
                second=0,
                microsecond=0,
                tzinfo=None,
            )
            existing = weather_by_hour.get(timestamp)
            if (
                existing is None
                or weather.provider_name == "Open-Meteo Historical Weather"
            ):
                weather_by_hour[timestamp] = weather

        overlay: dict[datetime, _ScadaReplayObservation] = {}
        for snapshot in matching:
            source_observation_time = snapshot.timestamp.replace(tzinfo=None)
            source_available_at = snapshot.available_at or snapshot.timestamp
            # Historical charts are keyed to the civil hour represented by the
            # aggregate. Availability remains separate and continues to gate
            # model features; it must not shift or overwrite observed values.
            source_timestamp = snapshot.timestamp.replace(
                minute=0,
                second=0,
                microsecond=0,
                tzinfo=None,
            )
            if source_timestamp.month != settings.DEMO_REPLAY_MONTH:
                continue
            display_timestamp = datetime(
                state.replay_start.year,
                state.replay_start.month,
                source_timestamp.day,
                source_timestamp.hour,
            )
            base = demo_rows.get(display_timestamp)
            if base is None:
                continue
            weather = weather_by_hour.get(source_timestamp)
            assert snapshot.current_demand_mw is not None
            assert snapshot.temperature_c is not None
            assert snapshot.spinning_reserve_mw is not None
            assert snapshot.available_capacity_mw is not None
            assert snapshot.online_capacity_mw is not None
            overlay[display_timestamp] = _ScadaReplayObservation(
                timestamp=display_timestamp,
                source_observation_time=source_observation_time,
                source_timestamp=source_timestamp,
                source_available_at=source_available_at,
                demand_mw=snapshot.current_demand_mw,
                # The project currently maps Total Online TRA to replay
                # generation; official semantics remain pending confirmation.
                generation_mw=snapshot.online_capacity_mw,
                spinning_reserve_mw=snapshot.spinning_reserve_mw,
                available_capacity_mw=snapshot.available_capacity_mw,
                online_capacity_mw=snapshot.online_capacity_mw,
                temperature_c=snapshot.temperature_c,
                humidity_percent=_value_or(
                    weather.humidity_percent if weather is not None else None,
                    base.humidity_percent,
                ),
                rainfall_mm_hr=_value_or(
                    weather.rainfall_mm_hr if weather is not None else None,
                    base.rainfall_mm_hr,
                ),
                cloud_cover_percent=_value_or(
                    weather.cloud_cover_percent if weather is not None else None,
                    base.cloud_cover_percent,
                ),
                wind_speed_kmh=_value_or(
                    weather.wind_speed_kph if weather is not None else None,
                    base.wind_speed_kmh,
                ),
                wind_direction_deg=_value_or(
                    weather.wind_direction_deg if weather is not None else None,
                    base.wind_direction_deg,
                ),
                pressure_hpa=_value_or(
                    weather.pressure_hpa if weather is not None else None,
                    base.pressure_hpa,
                ),
                quality_status=_dashboard_grid_quality(snapshot.quality_status),
                source=f"{SCADA_REPLAY_SOURCE} · {snapshot.source}",
                missing_fields=snapshot.missing_fields,
                coverage_percent=snapshot.coverage_percent,
                quality_notes=snapshot.quality_notes,
                anomaly_flags=snapshot.anomaly_flags,
                field_provenance=snapshot.field_provenance,
                formula_version=snapshot.formula_version,
                resampling_method=snapshot.resampling_method,
            )
        return overlay

    @staticmethod
    def _decision_observation(
        display_timestamp: datetime,
        fallback: _WeatherGridObservation,
        available_overlay: dict[datetime, _ScadaReplayObservation],
    ) -> _WeatherGridObservation:
        if not isinstance(fallback, _ScadaReplayObservation):
            return fallback
        eligible = [
            item
            for timestamp, item in available_overlay.items()
            if timestamp <= display_timestamp
        ]
        if not eligible:
            return fallback
        latest = max(eligible, key=lambda item: item.timestamp)
        # Keep the decision clock at the replay cursor while carrying only the
        # newest SCADA values that had actually finalized by that cursor.
        return replace(latest, timestamp=display_timestamp)

    @staticmethod
    def _available_scada_overlay(
        overlay: dict[datetime, _ScadaReplayObservation],
        display_cursor: datetime,
    ) -> dict[datetime, _ScadaReplayObservation]:
        if not overlay:
            return {}
        source_year = max(item.source_timestamp.year for item in overlay.values())
        source_cutoff = datetime(
            source_year,
            settings.DEMO_REPLAY_MONTH,
            display_cursor.day,
            display_cursor.hour,
            display_cursor.minute,
            display_cursor.second,
        )
        return {
            timestamp: item
            for timestamp, item in overlay.items()
            if item.source_available_at.replace(tzinfo=None) <= source_cutoff
        }

    def _weather_forecast(
        self,
        session,
        state: DemoReplayState,
        observation: _WeatherGridObservation,
        scada_overlay: dict[datetime, _ScadaReplayObservation],
    ) -> list[dict[str, object]]:
        if isinstance(observation, _ScadaReplayObservation):
            try:
                archived = self.replay_weather_provider.get_forecast_sources(
                    latitude=settings.DEFAULT_LATITUDE,
                    longitude=settings.DEFAULT_LONGITUDE,
                    source_cursor=observation.source_timestamp,
                    hours=24,
                )
                reconciled = WeatherService.reconcile_forecast_sources(
                    archived.source_payloads,
                    expected_source_count=archived.expected_source_count,
                )
                mapped = _map_archived_forecast_to_replay(
                    reconciled,
                    source_cursor=observation.source_timestamp,
                    display_cursor=state.cursor_at,
                    run_initialized_at=archived.run_initialized_at,
                    assumed_available_at=archived.assumed_available_at,
                )
                if mapped:
                    return mapped
            except Exception as exc:  # pragma: no cover - network resilience
                logger.warning(
                    "Archived replay weather unavailable; using past-only baseline: %s",
                    exc,
                )

        if (
            not isinstance(observation, _ScadaReplayObservation)
            and self.live_weather_service is not None
        ):
            try:
                live_forecast = _run_coroutine(
                    self.live_weather_service.get_forecast(
                        settings.DEFAULT_LATITUDE,
                        settings.DEFAULT_LONGITUDE,
                        days=2,
                        force_refresh=False,
                    )
                )
                mapped = _map_live_forecast_to_simulation(
                    live_forecast,
                    display_cursor=state.cursor_at,
                    live_reference=self.clock(),
                )
                if mapped:
                    return mapped
            except Exception as exc:  # pragma: no cover - network resilience
                logger.warning(
                    "Live weather ensemble unavailable for simulation; using "
                    "past-only baseline: %s",
                    exc,
                )

        if isinstance(observation, _ScadaReplayObservation):
            history: list[_WeatherGridObservation] = [
                row
                for timestamp, row in sorted(scada_overlay.items())
                if timestamp <= state.cursor_at
            ]
        else:
            history = list(
                session.scalars(
                    select(DemoObservation)
                    .where(DemoObservation.timestamp <= state.cursor_at)
                    .order_by(DemoObservation.timestamp)
                )
            )
        if not history:
            history = [observation]

        payloads: list[dict[str, object]] = []
        for horizon in range(1, 25):
            target = state.cursor_at + timedelta(hours=horizon)
            same_hour = [
                row
                for row in history
                if row.timestamp.hour == target.hour
                and row.timestamp <= state.cursor_at
            ][-21:]
            samples = same_hour or history[-24:]
            temperature = mean(row.temperature_c for row in samples)
            humidity = mean(row.humidity_percent for row in samples)
            rainfall = mean(row.rainfall_mm_hr for row in samples)
            cloud = mean(row.cloud_cover_percent for row in samples)
            wind = mean(row.wind_speed_kmh for row in samples)
            pressure = mean(row.pressure_hpa for row in samples)
            confidence = max(0.45, min(0.82, 0.45 + len(samples) * 0.025))
            payloads.append(
                {
                    "forecast_timestamp": target,
                    "temperature_c": round(temperature, 2),
                    "humidity_percent": round(humidity, 2),
                    "rainfall_mm_hr": round(rainfall, 2),
                    "cloud_cover_percent": round(cloud, 2),
                    "wind_speed_kmh": round(wind, 2),
                    "pressure_hpa": round(pressure, 2),
                    "weather_condition": _condition(rainfall, cloud),
                    "precipitation_probability_percent": min(
                        100.0,
                        round(10.0 + cloud * 0.65 + rainfall * 7.0, 1),
                    ),
                    "provider_name": "Replay Historical Weather Baseline",
                    "confidence_score": round(confidence, 2),
                    "temperature_aggregation": _source_temperature_aggregation(
                        round(temperature, 2),
                        label="Historical Trinidad average temperature",
                        method="past_only_scada_average_baseline",
                        source_name="Replay Historical Weather Baseline",
                        policy_status="HISTORICAL_SOURCE_AVERAGE",
                    ),
                }
            )
        return WeatherService.reconcile_forecast_sources([payloads])

    def _dashboard_bundle(
        self,
        session,
        state: DemoReplayState,
        observation: _WeatherGridObservation,
        weather_forecast: list[dict[str, object]],
        scada_overlay: dict[datetime, _ScadaReplayObservation],
        forecast_scada_overlay: dict[datetime, _ScadaReplayObservation],
        replay_forecasts: list[ScadaReplayForecastResult],
    ) -> ReplayDashboardResponse:
        history_start = state.cursor_at - timedelta(hours=47)
        raw_history = list(
            session.scalars(
                select(DemoObservation)
                .where(
                    DemoObservation.timestamp >= history_start,
                    DemoObservation.timestamp <= state.cursor_at,
                )
                .order_by(DemoObservation.timestamp)
            )
        )
        display_history: list[_WeatherGridObservation] = [
            scada_overlay.get(row.timestamp, row) for row in raw_history
        ]
        forecast_result = self._full_day_forecast(
            session,
            state,
            weather_forecast,
            scada_overlay,
            forecast_scada_overlay,
        )
        direct_by_display_timestamp = {
            observation.timestamp + timedelta(hours=row.horizon_hours): row
            for row in replay_forecasts
        }
        forecast = [
            LoadForecastPointResponse(
                timestamp=point.timestamp,
                forecast_demand_mw=(
                    direct_by_display_timestamp[point.timestamp].forecast_demand_mw
                    if point.timestamp in direct_by_display_timestamp
                    else point.forecast_demand_mw
                ),
                historical_average_mw=point.historical_average_mw,
                actual_demand_mw=point.actual_demand_mw,
                actual_temperature_c=point.actual_temperature_c,
                forecast_temperature_c=point.forecast_temperature_c,
                uncertainty_mw=(
                    direct_by_display_timestamp[point.timestamp].forecast_uncertainty_mw
                    if point.timestamp in direct_by_display_timestamp
                    else point.uncertainty_mw
                ),
                weather_impact_mw=point.weather_impact_mw,
                weather_confidence=point.weather_confidence,
                weather_source_count=point.weather_source_count,
            )
            for point in forecast_result.points
        ]
        historical = list(
            session.scalars(
                select(DemoObservation).where(
                    or_(
                        DemoObservation.timestamp < state.replay_start,
                        DemoObservation.timestamp > state.replay_end,
                    )
                )
            )
        )
        historical_count = len(historical)
        average = sum(row.demand_mw for row in historical) / historical_count
        peak = max(row.demand_mw for row in historical)
        current_day_forecast = [
            point
            for point in forecast
            if point.timestamp.date() == state.cursor_at.date()
        ]
        replay_status = self._status(session, state)
        if isinstance(observation, _ScadaReplayObservation):
            replay_status = replay_status.model_copy(
                update={
                    "mode": "historical_replay",
                    "dataset_label": (
                        "Historical replay — June 2026 · OSI trend exports + archived weather"
                    ),
                    "source": SCADA_REPLAY_SOURCE,
                }
            )
        return ReplayDashboardResponse(
            status=replay_status,
            operational_history=[
                OperationalTrendPointResponse(
                    timestamp=row.timestamp,
                    demand_mw=row.demand_mw,
                    generation_mw=row.generation_mw,
                    spinning_reserve_mw=row.spinning_reserve_mw,
                    available_capacity_mw=row.available_capacity_mw,
                    reserve_margin_percent=_reserve_margin_percent(row),
                    temperature_c=row.temperature_c,
                    rainfall_mm_hr=row.rainfall_mm_hr,
                    data_phase=(
                        "REPLAY_REVEALED"
                        if row.timestamp >= state.replay_start
                        else "HISTORICAL_SOURCE"
                    ),
                )
                for row in display_history
            ],
            full_day_load_forecast=forecast,
            monthly_history=self._monthly_history(session, state),
            summary=ReplaySummaryResponse(
                historical_months=11,
                historical_record_count=historical_count,
                historical_average_demand_mw=round(average, 2),
                historical_peak_demand_mw=round(peak, 2),
                replay_month_label=state.replay_start.strftime("%B %Y"),
                current_day_peak_forecast_mw=round(
                    max(
                        point.forecast_demand_mw
                        for point in (current_day_forecast or forecast)
                    ),
                    2,
                ),
                forecast_model=_replay_forecast_model_label(
                    replay_forecasts,
                    forecast_result.model_name,
                ),
                forecast_mode=(
                    replay_forecasts[0].quality_status
                    if replay_forecasts
                    else forecast_result.model_mode
                ),
                forecast_mae_mw=(
                    round(mean(row.mae for row in replay_forecasts), 2)
                    if replay_forecasts
                    else forecast_result.mae_mw
                ),
                baseline_mae_mw=(
                    round(mean(row.baseline_mae for row in replay_forecasts), 2)
                    if replay_forecasts
                    else forecast_result.baseline_mae_mw
                ),
                residual_std_mw=(
                    round(max(row.residual_std for row in replay_forecasts), 2)
                    if replay_forecasts
                    else forecast_result.residual_std_mw
                ),
                training_rows=(
                    min(row.training_rows for row in replay_forecasts)
                    if replay_forecasts
                    else forecast_result.training_rows
                ),
                forecast_trained_through=forecast_result.trained_through,
                weather_features=list(forecast_result.weather_features),
            ),
        )

    @staticmethod
    def _monthly_history(session, state: DemoReplayState) -> list[MonthlyHistoryPointResponse]:
        rows = list(session.scalars(select(DemoObservation).order_by(DemoObservation.timestamp)))
        grouped: dict[tuple[int, int], list[DemoObservation]] = defaultdict(list)
        for row in rows:
            grouped[(row.timestamp.year, row.timestamp.month)].append(row)
        result: list[MonthlyHistoryPointResponse] = []
        for (year, month), month_rows in grouped.items():
            count = len(month_rows)
            result.append(
                MonthlyHistoryPointResponse(
                    month=datetime(year, month, 1).strftime("%b"),
                    average_demand_mw=round(sum(row.demand_mw for row in month_rows) / count, 2),
                    peak_demand_mw=round(max(row.demand_mw for row in month_rows), 2),
                    average_temperature_c=round(sum(row.temperature_c for row in month_rows) / count, 2),
                    rainfall_total_mm=round(sum(row.rainfall_mm_hr for row in month_rows), 2),
                    data_phase=(
                        "REPLAY_SOURCE"
                        if year == state.replay_start.year and month == state.replay_start.month
                        else "HISTORICAL"
                    ),
                )
            )
        return result

    def _full_day_forecast(
        self,
        session,
        state: DemoReplayState,
        weather_forecast: list[dict[str, object]],
        scada_overlay: dict[datetime, _ScadaReplayObservation],
        forecast_scada_overlay: dict[datetime, _ScadaReplayObservation],
    ):
        scada_regime = state.cursor_at in scada_overlay
        weather_sources = tuple(
            str(name)
            for name in (
                weather_forecast[0].get("source_names", [])
                if weather_forecast
                else []
            )
        )
        source_signature = (
            DEMO_FORECAST_MODEL_VERSION,
            "historical_scada" if scada_regime else "simulation",
            *weather_sources,
        )
        cache_key = (state.cursor_at, source_signature)
        cached = self._forecast_cache.get(cache_key)
        if cached is not None:
            return cached
        day_start = state.cursor_at.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = max(
            day_start + timedelta(hours=23),
            state.cursor_at + timedelta(hours=6),
        )
        history_start = state.replay_start if scada_regime else state.dataset_start
        raw_history = list(
            session.scalars(
                select(DemoObservation).where(
                    DemoObservation.timestamp >= history_start,
                    DemoObservation.timestamp <= state.cursor_at,
                ).order_by(DemoObservation.timestamp)
            )
        )
        available_scada_history: list[_WeatherGridObservation] = [
            row
            for timestamp, row in sorted(forecast_scada_overlay.items())
            if timestamp <= state.cursor_at
        ]
        if (
            scada_regime
            and len(available_scada_history) >= MIN_REQUIRED_HISTORY_ROWS
        ):
            # Once enough historical SCADA exists, never train through a gap by
            # silently substituting deterministic demo observations. This keeps
            # one provenance regime and honors each interval's available_at.
            history = available_scada_history
            model_issue_at = history[-1].timestamp
        elif scada_regime:
            history = [
                forecast_scada_overlay.get(row.timestamp, row)
                for row in raw_history
            ]
            model_issue_at = state.cursor_at
        else:
            history = raw_history
            model_issue_at = state.cursor_at
        raw_day_rows = list(
            session.scalars(
                select(DemoObservation).where(
                    DemoObservation.timestamp >= day_start,
                    DemoObservation.timestamp <= day_end,
                ).order_by(DemoObservation.timestamp)
            )
        )
        day_rows: list[_WeatherGridObservation] = (
            [scada_overlay.get(row.timestamp, row) for row in raw_day_rows]
            if scada_regime
            else raw_day_rows
        )
        result = self.forecast_service.forecast_day(
            history=history,
            day_rows=day_rows,
            weather_forecast=weather_forecast,
            cursor_at=model_issue_at,
            actual_reveal_at=state.cursor_at,
        )
        self._forecast_cache = {cache_key: result}
        return result

    def _status(self, session, state: DemoReplayState) -> ReplayStatusResponse:
        total = session.scalar(
            select(func.count(DemoObservation.id)).where(
                DemoObservation.timestamp >= state.replay_start,
                DemoObservation.timestamp <= state.replay_end,
            )
        ) or 0
        revealed = session.scalar(
            select(func.count(DemoObservation.id)).where(
                DemoObservation.timestamp >= state.replay_start,
                DemoObservation.timestamp <= state.cursor_at,
            )
        ) or 0
        duration = max(1.0, (state.replay_end - state.replay_start).total_seconds())
        progress = (state.cursor_at - state.replay_start).total_seconds() / duration * 100
        return ReplayStatusResponse(
            mode="simulation",
            dataset_label=(
                f"Simulation — {settings.DEMO_DATASET_YEAR} synthetic hourly grid + weather"
            ),
            dataset_start=state.dataset_start,
            dataset_end=state.dataset_end,
            replay_start=state.replay_start,
            replay_end=state.replay_end,
            cursor_at=state.cursor_at,
            is_playing=state.is_playing,
            step_minutes=state.step_minutes,
            speed_multiplier=state.speed_multiplier,
            progress_percent=round(max(0.0, min(100.0, progress)), 2),
            revealed_records=int(revealed),
            total_replay_records=int(total),
            source=DEMO_SOURCE,
            clock_aligned=state.clock_aligned,
        )

    @staticmethod
    def _advance_if_playing(state: DemoReplayState) -> None:
        if not state.is_playing:
            return
        now = _utc_now_naive()
        if state.last_wallclock_at is None:
            state.last_wallclock_at = now
            return
        elapsed = max(0.0, (now - state.last_wallclock_at).total_seconds())
        simulated_minutes = elapsed * state.speed_multiplier / 60.0
        steps = int(simulated_minutes // state.step_minutes)
        if steps <= 0:
            return
        state.cursor_at = min(
            state.replay_end,
            state.cursor_at + timedelta(minutes=steps * state.step_minutes),
        )
        state.last_wallclock_at = now
        if state.cursor_at >= state.replay_end:
            state.is_playing = False
            state.last_wallclock_at = None

    @staticmethod
    def _state(session) -> DemoReplayState:
        state = session.get(DemoReplayState, STATE_ID)
        if state is None:
            raise RuntimeError("Demo replay state is not initialized")
        return state

    def _ensure_state(self, session) -> DemoReplayState:
        state = session.get(DemoReplayState, STATE_ID)
        if state is not None:
            return state
        year = settings.DEMO_DATASET_YEAR
        month = settings.DEMO_REPLAY_MONTH
        dataset_start = datetime(year, 1, 1)
        dataset_end = datetime(year, 12, 31, 23)
        replay_start = datetime(year, month, 1)
        replay_end = (
            datetime(year + 1, 1, 1) - timedelta(hours=1)
            if month == 12
            else datetime(year, month + 1, 1) - timedelta(hours=1)
        )
        state = DemoReplayState(
            id=STATE_ID,
            dataset_start=dataset_start,
            dataset_end=dataset_end,
            replay_start=replay_start,
            replay_end=replay_end,
            cursor_at=replay_start,
            is_playing=True,
            step_minutes=60,
            speed_multiplier=1.0,
            last_wallclock_at=_utc_now_naive(),
            clock_aligned=True,
        )
        state.cursor_at = self._mapped_wallclock_cursor(state)
        session.add(state)
        return state

    def _sync_state_to_wallclock(self, state: DemoReplayState) -> None:
        state.cursor_at = self._mapped_wallclock_cursor(state)
        state.is_playing = True
        state.speed_multiplier = 1.0
        state.last_wallclock_at = _utc_now_naive()
        state.clock_aligned = True

    def _mapped_wallclock_cursor(self, state: DemoReplayState) -> datetime:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=TRINIDAD_TZ)
        else:
            now = now.astimezone(TRINIDAD_TZ)
        last_day = monthrange(state.replay_start.year, state.replay_start.month)[1]
        day = min(max(1, now.day), last_day)
        mapped = datetime(
            state.replay_start.year,
            state.replay_start.month,
            day,
            now.hour,
        )
        return min(state.replay_end, max(state.replay_start, mapped))


def _generate_demo_year(year: int) -> list[DemoObservation]:
    start = datetime(year, 1, 1)
    hours = (366 if _is_leap_year(year) else 365) * 24
    rows: list[DemoObservation] = []
    for offset in range(hours):
        timestamp = start + timedelta(hours=offset)
        day = timestamp.timetuple().tm_yday
        hour = timestamp.hour
        wet_season = 1.0 if 6 <= timestamp.month <= 12 else 0.0
        solar = max(0.0, math.sin(math.pi * (hour - 6) / 12))
        seasonal = math.sin(2 * math.pi * (day - 45) / 365)
        temperature = 24.2 + 6.1 * solar + 0.9 * seasonal + 0.35 * math.sin(offset * 0.37)
        rain_trigger = (day * 17 + hour * 29 + int(20 * math.sin(day))) % 100
        rain_threshold = 17 if wet_season else 7
        rainfall = 0.0
        if rain_trigger < rain_threshold:
            rainfall = 0.4 + ((day * 11 + hour * 7) % 65) / 10
        humidity = min(98.0, 86.0 - 19.0 * solar + 6.0 * wet_season + min(8.0, rainfall * 1.6))
        cloud = min(100.0, 28.0 + 38.0 * wet_season + rainfall * 7.0 + 18 * (1 - solar))
        wind = 9.0 + 8.0 * solar + 2.4 * math.sin(offset * 0.19)
        pressure = 1013.2 + 2.1 * math.sin(2 * math.pi * hour / 24) - rainfall * 0.18
        if hour < 5:
            load_shape = 700 + hour * 8
        elif hour < 9:
            load_shape = 750 + (hour - 5) * 65
        elif hour < 14:
            load_shape = 990 + (hour - 9) * 28
        elif hour < 18:
            load_shape = 1130 - (hour - 14) * 16
        elif hour < 22:
            load_shape = 1080 + 92 * math.sin(math.pi * (hour - 18) / 4)
        else:
            load_shape = 930 - (hour - 22) * 70
        weekday_adjustment = -70 if timestamp.weekday() == 6 else (-35 if timestamp.weekday() == 5 else 0)
        weather_load = max(0.0, temperature - 27.0) * 15.0 + max(0.0, humidity - 75.0) * 1.7 - rainfall * 3.0
        demand = load_shape + weekday_adjustment + weather_load + 12 * math.sin(offset * 0.11)
        available = 1460.0 - (90.0 if day % 53 in {0, 1, 2} else 0.0)
        online = min(available, demand + 170.0 + 25.0 * math.sin(offset * 0.07))
        generation = demand + 8.0 + 4.0 * math.sin(offset * 0.23)
        online_headroom = max(0.0, online - demand)
        # Simulation only: mirror the exploratory June archive relationship
        # without redefining the OSI corrected-spin tag as TRA minus demand.
        synthetic_spin = max(
            0.0,
            min(
                online_headroom,
                0.744 * online_headroom
                + 19.10
                + 7.5 * math.sin(offset * 0.13),
            ),
        )
        rows.append(
            DemoObservation(
                timestamp=timestamp,
                demand_mw=round(demand, 2),
                generation_mw=round(generation, 2),
                spinning_reserve_mw=round(synthetic_spin, 2),
                available_capacity_mw=round(available, 2),
                online_capacity_mw=round(online, 2),
                temperature_c=round(temperature, 2),
                humidity_percent=round(humidity, 2),
                rainfall_mm_hr=round(rainfall, 2),
                cloud_cover_percent=round(cloud, 2),
                wind_speed_kmh=round(max(1.0, wind), 2),
                wind_direction_deg=round((75 + 24 * math.sin(offset * 0.05)) % 360, 2),
                pressure_hpa=round(pressure, 2),
                quality_status="GOOD",
                source=DEMO_SOURCE,
            )
        )
    return rows


def _weather_payload(row: _WeatherGridObservation) -> dict[str, object]:
    condition = _condition(row.rainfall_mm_hr, row.cloud_cover_percent)
    is_scada_replay = row.source.startswith(SCADA_REPLAY_SOURCE)
    return {
        "timestamp": row.timestamp,
        "temperature_c": row.temperature_c,
        "humidity_percent": row.humidity_percent,
        "rainfall_mm_hr": row.rainfall_mm_hr,
        "cloud_cover_percent": row.cloud_cover_percent,
        "wind_speed_kmh": row.wind_speed_kmh,
        "weather_condition": condition,
        "heat_index_c": round(row.temperature_c + 0.033 * row.humidity_percent - 0.70, 2),
        "rain_severity": _rain_severity(row.rainfall_mm_hr),
        "wind_direction_deg": row.wind_direction_deg,
        "pressure_hpa": row.pressure_hpa,
        "provider_name": (
            "Historical replay · June SCADA + archived weather"
            if is_scada_replay
            else "Simulation replay · historical weather"
        ),
        "temperature_aggregation": _source_temperature_aggregation(
            row.temperature_c,
            label=(
                "SCADA Trinidad average temperature"
                if is_scada_replay
                else "Simulated Trinidad average temperature"
            ),
            method=(
                "scada_exported_trinidad_average"
                if is_scada_replay
                else "simulation_average_temperature"
            ),
            source_name=(
                "MHO132 AVERAGE AMBIENT TEMPERATURE"
                if is_scada_replay
                else "WGDSS simulation profile"
            ),
            policy_status=(
                "SOURCE_DEFINITION_REQUIRES_TTEC_CONFIRMATION"
                if is_scada_replay
                else "SIMULATED"
            ),
        ),
    }


def _source_temperature_aggregation(
    temperature_c: float,
    *,
    label: str,
    method: str,
    source_name: str,
    policy_status: str,
) -> dict[str, object]:
    return {
        "label": label,
        "method": method,
        "policy_version": "SOURCE_AGGREGATE_V1",
        "policy_status": policy_status,
        "status": "SOURCE_AGGREGATE",
        "source_name": source_name,
        "weighted_average_c": round(temperature_c, 2),
        "minimum_c": round(temperature_c, 2),
        "maximum_c": round(temperature_c, 2),
        "spread_c": 0.0,
        "sample_count": 0,
        "expected_sample_count": 0,
        "weight_coverage_percent": 100.0,
        "samples": [],
    }


def _grid_payload(row: _WeatherGridObservation) -> dict[str, object]:
    margin = _reserve_margin_percent(row)
    is_historical_scada = row.source.startswith(SCADA_REPLAY_SOURCE)
    missing_fields = [
        field.strip()
        for field in str(getattr(row, "missing_fields", "")).split(",")
        if field.strip()
    ]
    return {
        "timestamp": row.timestamp,
        "current_demand_mw": row.demand_mw,
        "current_generation_mw": row.generation_mw,
        "total_available_capacity_mw": row.available_capacity_mw,
        "reserve_margin_percent": margin,
        "spinning_reserve_mw": row.spinning_reserve_mw,
        "spinning_reserve_source": (
            "GSYS SYSTEM_CORRECTED_SPIN_TOTAL"
            if is_historical_scada
            else "SYNTHETIC_REPLAY_MODEL"
        ),
        "grid_status": "NORMAL" if margin >= 20 else ("WATCH" if margin >= 10 else "CRITICAL"),
        "demand_period": _demand_period(row.timestamp.hour),
        "source_provider": (
            "HistoricalScadaReplay"
            if is_historical_scada
            else "SyntheticReplayProvider"
        ),
        "quality_status": row.quality_status,
        "missing_fields": missing_fields,
    }


def _generation_units(row: _WeatherGridObservation) -> list[dict[str, object]]:
    stations = (
        ("Point Lisas", "GT-1", 0.24),
        ("Point Lisas", "GT-2", 0.20),
        ("Penal", "Unit-1", 0.22),
        ("Cove", "Unit-1", 0.14),
        ("La Brea", "Unit-1", 0.20),
    )
    return [
        {
            "station_name": station,
            "unit_name": unit,
            "fuel_type": "Natural Gas",
            "available_capacity_mw": round(row.available_capacity_mw * share, 2),
            "current_output_mw": round(row.generation_mw * share, 2),
            "status": "ONLINE",
            "is_dispatchable": True,
            "observed_at": row.timestamp,
            "quality_status": row.quality_status,
            "source_tag": (
                "HISTORICAL_SCADA_REPLAY"
                if row.source.startswith(SCADA_REPLAY_SOURCE)
                else "DEMO_REPLAY"
            ),
        }
        for station, unit, share in stations
    ]


def _map_archived_forecast_to_replay(
    forecast: list[dict[str, object]],
    source_cursor: datetime,
    display_cursor: datetime,
    run_initialized_at: datetime,
    assumed_available_at: datetime,
) -> list[dict[str, object]]:
    source_reference = _trinidad_datetime(source_cursor)
    display_reference = _trinidad_datetime(display_cursor)
    mapped: list[dict[str, object]] = []
    for item in forecast:
        source_timestamp = _forecast_datetime(item.get("forecast_timestamp"))
        if source_timestamp is None:
            continue
        lead_hours_value = (
            source_timestamp - source_reference
        ).total_seconds() / 3600.0
        lead_hours = int(round(lead_hours_value))
        if lead_hours < 1 or lead_hours > 24:
            continue
        if abs(lead_hours_value - lead_hours) > 0.01:
            continue
        mapped.append(
            {
                **item,
                "forecast_timestamp": (
                    display_reference + timedelta(hours=lead_hours)
                ).isoformat(),
                "forecast_mode": "ARCHIVED_ISSUED_MODEL_ENSEMBLE",
                "source_run_at": run_initialized_at.isoformat(),
                "forecast_issued_at": assumed_available_at.isoformat(),
            }
        )
    return mapped


def _map_live_forecast_to_simulation(
    forecast: list[dict[str, object]],
    display_cursor: datetime,
    live_reference: datetime,
) -> list[dict[str, object]]:
    """Map genuine future issue-time forecasts onto the synthetic replay clock.

    This adapter is used only for the simulated-grid dashboard. Historical SCADA
    replay continues to use archived model runs so future information cannot leak
    into a replay decision.
    """

    reference = _trinidad_datetime(live_reference)
    display_reference = _trinidad_datetime(display_cursor)
    future: list[tuple[datetime, dict[str, object]]] = []
    for item in forecast:
        source_timestamp = _forecast_datetime(item.get("forecast_timestamp"))
        if source_timestamp is None or source_timestamp <= reference:
            continue
        future.append((source_timestamp, item))

    future.sort(key=lambda pair: pair[0])
    mapped: list[dict[str, object]] = []
    for index, (source_timestamp, item) in enumerate(future[:24], start=1):
        mapped.append(
            {
                **item,
                "forecast_timestamp": (
                    display_reference + timedelta(hours=index)
                ).isoformat(),
                "source_forecast_timestamp": source_timestamp.isoformat(),
                "forecast_mode": "LIVE_ENSEMBLE_MAPPED_TO_SIMULATION",
            }
        )
    return mapped


def _run_coroutine(coroutine):
    """Run an async provider from the synchronous replay service safely."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result: list[object] = []
    error: list[BaseException] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(coroutine))
        except BaseException as exc:  # pragma: no cover - defensive bridge
            error.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0]


def _has_multi_source_forecast(forecast: list[dict[str, object]]) -> bool:
    return any(int(item.get("source_count", 1) or 1) > 1 for item in forecast)


def _trinidad_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=TRINIDAD_TZ)
    return value.astimezone(TRINIDAD_TZ)


def _forecast_datetime(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _trinidad_datetime(parsed)


def _ceil_hour(value: datetime) -> datetime:
    floored = value.replace(minute=0, second=0, microsecond=0)
    return floored if value == floored else floored + timedelta(hours=1)


def _reserve_margin_percent(row: _WeatherGridObservation) -> float:
    return round((row.available_capacity_mw - row.demand_mw) / row.demand_mw * 100, 2)


def _condition(rainfall: float, cloud: float) -> str:
    if rainfall >= 8:
        return "Heavy rain"
    if rainfall >= 2:
        return "Rain showers"
    if rainfall > 0:
        return "Light rain"
    if cloud >= 75:
        return "Overcast"
    if cloud >= 45:
        return "Partly cloudy"
    return "Mainly clear"


def _rain_severity(rainfall: float) -> str:
    if rainfall >= 15:
        return "SEVERE"
    if rainfall >= 8:
        return "HEAVY"
    if rainfall >= 2:
        return "MODERATE"
    if rainfall > 0:
        return "LIGHT"
    return "DRY"


def _demand_period(hour: int) -> str:
    if hour < 5:
        return "NIGHT"
    if hour < 11:
        return "MORNING"
    if hour < 17:
        return "AFTERNOON"
    if hour < 22:
        return "EVENING PEAK"
    return "LATE NIGHT"


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _value_or(value: float | None, fallback: float) -> float:
    return float(fallback if value is None else value)


def _dashboard_grid_quality(value: str) -> str:
    normalized = value.strip().upper()
    if normalized == "GOOD":
        return "GOOD"
    if normalized == "USABLE_WITH_WARNING":
        return "UNCERTAIN"
    return "BAD"


def _has_missing_operating_capacity(missing_fields: str) -> bool:
    normalized = {
        field.strip().lower()
        for field in missing_fields.split(",")
        if field.strip()
    }
    return bool(
        normalized
        & {
            "available_capacity_mw",
            "online_capacity_mw",
            "gsys system_avail_total",
            "gsys system_onln_total",
        }
    )


def _replay_forecast_confidence(row: ScadaReplayForecastResult) -> float:
    confidence = 0.9 if row.validation_status == "VALIDATED" else 0.78
    if "DEGRADED" in row.quality_status:
        confidence -= 0.15
    return max(0.45, min(0.95, confidence))


def _replay_forecast_model_label(
    rows: list[ScadaReplayForecastResult],
    fallback: str,
) -> str:
    if not rows:
        return fallback
    names = list(dict.fromkeys(row.model_name for row in rows))
    return names[0] if len(names) == 1 else "Per-horizon: " + ", ".join(names)


def _json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_float_object(value: str) -> dict[str, float]:
    return {
        str(key): float(item)
        for key, item in _json_object(value).items()
        if isinstance(item, (int, float))
    }


def _json_list(value: str) -> list[dict[str, object]]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _json_string_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [item for item in parsed if isinstance(item, str)] if isinstance(parsed, list) else []


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
