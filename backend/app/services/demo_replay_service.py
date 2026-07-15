from __future__ import annotations

import math
import threading
from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, or_, select

from app.core.config import settings
from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.demo_replay import DemoObservation, DemoReplayState
from app.models.scada import ScadaGridSnapshot
from app.models.weather import Weather
from app.schemas.replay import (
    LoadForecastPointResponse,
    MonthlyHistoryPointResponse,
    OperationalTrendPointResponse,
    ReplayControlRequest,
    ReplayDashboardResponse,
    ReplayStatusResponse,
    ReplaySummaryResponse,
)
from app.services.demo_load_forecast_service import DemoLoadForecastService
from app.services.risk_probability_engine import (
    OperatingForecastPoint,
    OperatingRiskInput,
    RiskProbabilityEngine,
)
from app.services.weather_service import WeatherService


DEMO_SOURCE = "WGDSS 12-Month Synthetic SCADA/Weather Demonstration"
STATE_ID = 1
TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")
SCADA_REPLAY_SOURCE = "Historical SCADA Simulation"


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


@dataclass(frozen=True)
class _ScadaReplayObservation:
    timestamp: datetime
    source_timestamp: datetime
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


class DemoReplayService:
    """Own immutable demo history and a separately persisted simulated-live cursor."""

    _lock = threading.Lock()

    def __init__(
        self,
        session_factory=SessionLocal,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(TRINIDAD_TZ))
        self.forecast_service = DemoLoadForecastService()
        self.risk_engine = RiskProbabilityEngine()
        self._forecast_cache: dict[datetime, object] = {}

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
            observation = session.scalar(
                select(DemoObservation).where(DemoObservation.timestamp == state.cursor_at)
            )
            if observation is None:
                return None
            scada_overlay = self._scada_overlay(session, state)
            active_observation = scada_overlay.get(state.cursor_at, observation)
            weather_forecast = self._weather_forecast(
                session,
                state,
                active_observation,
                scada_overlay,
            )
            replay = self._dashboard_bundle(
                session,
                state,
                active_observation,
                weather_forecast,
                scada_overlay,
            )
            risk_payload = self._operating_risk_payload(active_observation, replay)
            session.commit()
        return {
            "weather": _weather_payload(active_observation),
            "forecast": weather_forecast,
            "grid": _grid_payload(active_observation),
            "generation_units": _generation_units(active_observation),
            "replay": replay,
            "risk_payload": risk_payload,
        }

    def _operating_risk_payload(
        self,
        observation: _WeatherGridObservation,
        replay: ReplayDashboardResponse,
    ) -> dict[str, object]:
        future = [
            point
            for point in replay.full_day_load_forecast
            if point.timestamp > observation.timestamp
            and point.timestamp <= observation.timestamp + timedelta(hours=6)
        ]
        profile: list[OperatingForecastPoint] = []
        if future:
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
                )
                for point in future
            )
        if not profile:
            profile.append(
                OperatingForecastPoint(
                    horizon_minutes=60,
                    forecast_demand_mw=observation.demand_mw,
                    forecast_uncertainty_mw=15.0,
                    confidence=0.5,
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
                forecast_profile=tuple(profile),
            )
        )
        forecast_30 = min(profile, key=lambda point: abs(point.horizon_minutes - 30))
        forecast_60 = min(profile, key=lambda point: abs(point.horizon_minutes - 60))
        return {
            "engine_version": risk.engine_version,
            "probability_score": risk.probability_score,
            "risk_level": risk.risk_level,
            "forecast_demand_30m": round(forecast_30.forecast_demand_mw, 2),
            "forecast_demand_60m": round(forecast_60.forecast_demand_mw, 2),
            "recommendation": risk.recommendation,
            "factors": risk.reasons,
            "reason": "; ".join(risk.reasons),
            "decision_action": risk.decision_action,
            "generator_set": risk.generator_set,
            "recommended_capacity_mw": risk.recommended_capacity_mw,
            "projected_shortfall_mw": risk.projected_shortfall_mw,
            "expected_shortfall_mw": risk.expected_shortfall_mw,
            "expected_load_rise_mw": risk.expected_load_rise_mw,
            "expected_rise_minutes": risk.expected_rise_minutes,
            "startup_time_minutes": risk.startup_time_minutes,
            "decision_confidence": risk.decision_confidence,
            "weather_effect_mw": risk.weather_effect_mw,
            "available_start_capacity_mw": risk.available_start_capacity_mw,
            "residual_shortfall_mw": risk.residual_shortfall_mw,
        }

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
            if (snapshot.available_at or snapshot.timestamp).month
            == settings.DEMO_REPLAY_MONTH
            and snapshot.current_demand_mw is not None
        ]
        if not matching:
            return {}
        source_year = max(
            (snapshot.available_at or snapshot.timestamp).year
            for snapshot in matching
        )
        matching = [
            snapshot
            for snapshot in matching
            if (snapshot.available_at or snapshot.timestamp).year == source_year
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
            source_timestamp = (snapshot.available_at or snapshot.timestamp).replace(
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
            demand = _value_or(snapshot.current_demand_mw, base.demand_mw)
            available = _value_or(
                snapshot.available_capacity_mw,
                base.available_capacity_mw,
            )
            online = _value_or(
                snapshot.online_capacity_mw,
                base.online_capacity_mw,
            )
            overlay[display_timestamp] = _ScadaReplayObservation(
                timestamp=display_timestamp,
                source_timestamp=source_timestamp,
                demand_mw=demand,
                generation_mw=demand,
                spinning_reserve_mw=_value_or(
                    snapshot.spinning_reserve_mw,
                    base.spinning_reserve_mw,
                ),
                available_capacity_mw=available,
                online_capacity_mw=online,
                temperature_c=_value_or(
                    snapshot.temperature_c,
                    weather.temperature_c if weather is not None else base.temperature_c,
                ),
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
            )
        return overlay

    def _weather_forecast(
        self,
        session,
        state: DemoReplayState,
        observation: _WeatherGridObservation,
        scada_overlay: dict[datetime, _ScadaReplayObservation],
    ) -> list[dict[str, object]]:
        if scada_overlay:
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
        history: list[_WeatherGridObservation] = [
            scada_overlay.get(row.timestamp, row) for row in raw_history
        ]
        forecast_result = self._full_day_forecast(
            session,
            state,
            weather_forecast,
            scada_overlay,
        )
        forecast = [
            LoadForecastPointResponse(
                timestamp=point.timestamp,
                forecast_demand_mw=point.forecast_demand_mw,
                historical_average_mw=point.historical_average_mw,
                actual_demand_mw=point.actual_demand_mw,
                uncertainty_mw=point.uncertainty_mw,
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
        return ReplayDashboardResponse(
            status=self._status(session, state),
            operational_history=[
                OperationalTrendPointResponse(
                    timestamp=row.timestamp,
                    demand_mw=row.demand_mw,
                    generation_mw=row.generation_mw,
                    available_capacity_mw=row.available_capacity_mw,
                    reserve_margin_percent=_reserve_margin_percent(row),
                    temperature_c=row.temperature_c,
                    rainfall_mm_hr=row.rainfall_mm_hr,
                    data_phase=(
                        "SIMULATED_LIVE"
                        if row.timestamp >= state.replay_start
                        else "HISTORICAL"
                    ),
                )
                for row in history
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
                    max(point.forecast_demand_mw for point in forecast), 2
                ),
                forecast_model=forecast_result.model_name,
                forecast_mode=forecast_result.model_mode,
                forecast_mae_mw=forecast_result.mae_mw,
                baseline_mae_mw=forecast_result.baseline_mae_mw,
                residual_std_mw=forecast_result.residual_std_mw,
                training_rows=forecast_result.training_rows,
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
    ):
        cached = self._forecast_cache.get(state.cursor_at)
        if cached is not None:
            return cached
        day_start = state.cursor_at.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(hours=23)
        history_start = (
            state.replay_start
            if scada_overlay
            else state.dataset_start
        )
        raw_history = list(
            session.scalars(
                select(DemoObservation).where(
                    DemoObservation.timestamp >= history_start,
                    DemoObservation.timestamp <= state.cursor_at,
                )
            )
        )
        history: list[_WeatherGridObservation] = [
            scada_overlay.get(row.timestamp, row) for row in raw_history
        ]
        raw_day_rows = list(
            session.scalars(
                select(DemoObservation).where(
                    DemoObservation.timestamp >= day_start,
                    DemoObservation.timestamp <= day_end,
                ).order_by(DemoObservation.timestamp)
            )
        )
        day_rows: list[_WeatherGridObservation] = [
            scada_overlay.get(row.timestamp, row) for row in raw_day_rows
        ]
        result = self.forecast_service.forecast_day(
            history=history,
            day_rows=day_rows,
            weather_forecast=weather_forecast,
            cursor_at=state.cursor_at,
        )
        self._forecast_cache = {state.cursor_at: result}
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
            dataset_label=f"{settings.DEMO_DATASET_YEAR} hourly SCADA + weather demonstration",
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
        rows.append(
            DemoObservation(
                timestamp=timestamp,
                demand_mw=round(demand, 2),
                generation_mw=round(generation, 2),
                spinning_reserve_mw=round(max(0.0, online - demand), 2),
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
            "Simulated Live · June SCADA + Open-Meteo Replay"
            if row.source.startswith(SCADA_REPLAY_SOURCE)
            else "Simulated Live · Historical Weather Replay"
        ),
    }


def _grid_payload(row: _WeatherGridObservation) -> dict[str, object]:
    margin = _reserve_margin_percent(row)
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
        "grid_status": "NORMAL" if margin >= 20 else ("WATCH" if margin >= 10 else "CRITICAL"),
        "demand_period": _demand_period(row.timestamp.hour),
        "source_provider": (
            "HistoricalScadaSimulatedReplay"
            if row.source.startswith(SCADA_REPLAY_SOURCE)
            else "SimulatedLiveScadaReplay"
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


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
