from __future__ import annotations

import math
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select

from app.core.config import settings
from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.demo_replay import DemoObservation, DemoReplayState
from app.schemas.replay import (
    LoadForecastPointResponse,
    MonthlyHistoryPointResponse,
    OperationalTrendPointResponse,
    ReplayControlRequest,
    ReplayDashboardResponse,
    ReplayStatusResponse,
    ReplaySummaryResponse,
)


DEMO_SOURCE = "WGDSS 12-Month Synthetic SCADA/Weather Demonstration"
STATE_ID = 1


class DemoReplayService:
    """Own immutable demo history and a separately persisted simulated-live cursor."""

    _lock = threading.Lock()

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def ensure_seeded(self, force: bool = False) -> int:
        if self.session_factory is SessionLocal:
            initialize_database()
        with self._lock, self.session_factory() as session:
            existing = session.scalar(select(func.count(DemoObservation.id))) or 0
            expected = 365 * 24 if not _is_leap_year(settings.DEMO_DATASET_YEAR) else 366 * 24
            if existing == expected and not force:
                self._ensure_state(session)
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
            replay = self._dashboard_bundle(session, state, observation)
            session.commit()
        return {
            "weather": _weather_payload(observation),
            "forecast": self._weather_forecast(state.cursor_at),
            "grid": _grid_payload(observation),
            "generation_units": _generation_units(observation),
            "replay": replay,
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
                state.cursor_at = state.replay_start
                state.is_playing = False
                state.last_wallclock_at = None
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

    def _weather_forecast(self, cursor_at: datetime) -> list[dict[str, object]]:
        with self.session_factory() as session:
            rows = list(
                session.scalars(
                    select(DemoObservation)
                    .where(
                        DemoObservation.timestamp > cursor_at,
                        DemoObservation.timestamp <= cursor_at + timedelta(hours=24),
                    )
                    .order_by(DemoObservation.timestamp)
                )
            )
        return [_forecast_payload(row) for row in rows]

    def _dashboard_bundle(
        self,
        session,
        state: DemoReplayState,
        observation: DemoObservation,
    ) -> ReplayDashboardResponse:
        history_start = state.cursor_at - timedelta(hours=47)
        history = list(
            session.scalars(
                select(DemoObservation)
                .where(
                    DemoObservation.timestamp >= history_start,
                    DemoObservation.timestamp <= state.cursor_at,
                )
                .order_by(DemoObservation.timestamp)
            )
        )
        forecast = self._full_day_forecast(session, state)
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

    def _full_day_forecast(self, session, state: DemoReplayState) -> list[LoadForecastPointResponse]:
        day_start = state.cursor_at.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(hours=23)
        prior_start = state.cursor_at - timedelta(days=84)
        history = list(
            session.scalars(
                select(DemoObservation).where(
                    DemoObservation.timestamp >= prior_start,
                    DemoObservation.timestamp < state.cursor_at,
                )
            )
        )
        day_rows = {
            row.timestamp: row
            for row in session.scalars(
                select(DemoObservation).where(
                    DemoObservation.timestamp >= day_start,
                    DemoObservation.timestamp <= day_end,
                )
            )
        }
        by_hour: dict[int, list[DemoObservation]] = defaultdict(list)
        for row in history:
            by_hour[row.timestamp.hour].append(row)
        points: list[LoadForecastPointResponse] = []
        for hour in range(24):
            target = day_start + timedelta(hours=hour)
            target_weather = day_rows[target]
            candidates = by_hour.get(hour) or history
            baseline = sum(row.demand_mw for row in candidates) / len(candidates)
            average_temp = sum(row.temperature_c for row in candidates) / len(candidates)
            average_humidity = sum(row.humidity_percent for row in candidates) / len(candidates)
            weather_adjustment = (
                (target_weather.temperature_c - average_temp) * 10.5
                + (target_weather.humidity_percent - average_humidity) * 0.8
                - min(22.0, target_weather.rainfall_mm_hr * 4.0)
            )
            estimate = max(650.0, baseline + weather_adjustment)
            spread = max(12.0, 18.0 + abs(weather_adjustment) * 0.35)
            points.append(
                LoadForecastPointResponse(
                    timestamp=target,
                    forecast_demand_mw=round(estimate, 2),
                    historical_average_mw=round(baseline, 2),
                    actual_demand_mw=(
                        target_weather.demand_mw if target <= state.cursor_at else None
                    ),
                    uncertainty_mw=round(spread, 2),
                )
            )
        return points

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

    @staticmethod
    def _ensure_state(session) -> DemoReplayState:
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
            is_playing=False,
            step_minutes=60,
            speed_multiplier=600.0,
        )
        session.add(state)
        return state


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


def _weather_payload(row: DemoObservation) -> dict[str, object]:
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
        "provider_name": "Simulated Live · Historical Weather Replay",
    }


def _forecast_payload(row: DemoObservation) -> dict[str, object]:
    payload = _weather_payload(row)
    return {
        "forecast_timestamp": row.timestamp,
        **{key: value for key, value in payload.items() if key not in {"timestamp", "provider_name"}},
        "precipitation_probability_percent": min(100.0, round(15 + row.cloud_cover_percent * 0.65 + row.rainfall_mm_hr * 8, 1)),
        "confidence_score": 0.86,
        "provider_name": "Demo Forecast · Weather-informed replay",
        "source_count": 1,
        "source_names": ["WGDSS historical weather demonstration"],
    }


def _grid_payload(row: DemoObservation) -> dict[str, object]:
    margin = _reserve_margin_percent(row)
    return {
        "timestamp": row.timestamp,
        "current_demand_mw": row.demand_mw,
        "current_generation_mw": row.generation_mw,
        "total_available_capacity_mw": row.available_capacity_mw,
        "reserve_margin_percent": margin,
        "grid_status": "NORMAL" if margin >= 20 else ("WATCH" if margin >= 10 else "CRITICAL"),
        "demand_period": _demand_period(row.timestamp.hour),
        "source_provider": "SimulatedLiveScadaReplay",
        "quality_status": "GOOD",
        "missing_fields": [],
    }


def _generation_units(row: DemoObservation) -> list[dict[str, object]]:
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
            "quality_status": "GOOD",
            "source_tag": "DEMO_REPLAY",
        }
        for station, unit, share in stations
    ]


def _reserve_margin_percent(row: DemoObservation) -> float:
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


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
