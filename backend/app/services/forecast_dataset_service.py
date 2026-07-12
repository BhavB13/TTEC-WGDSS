from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.demand_forecast import ForecastTrainingRow
from app.models.forecast import Forecast
from app.models.scada import ScadaGridSnapshot
from app.models.weather import Weather

FORECAST_HORIZONS_HOURS = (1, 2, 6)


@dataclass(frozen=True)
class ForecastDatasetBuildResult:
    rows_created: int
    source_snapshots: int
    skipped_rows: int


class ForecastDatasetService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def build_training_rows(
        self,
        horizons_hours: tuple[int, ...] = FORECAST_HORIZONS_HOURS,
        replace_existing: bool = True,
    ) -> ForecastDatasetBuildResult:
        if self.session_factory is SessionLocal:
            initialize_database()

        with self.session_factory() as session:
            snapshots = list(
                session.scalars(
                    select(ScadaGridSnapshot).order_by(ScadaGridSnapshot.timestamp)
                )
            )
            weather_by_hour = {
                _hour_key(row.timestamp): row
                for row in session.scalars(select(Weather).order_by(Weather.timestamp))
            }
            forecasts_by_hour: dict[datetime, list[Forecast]] = defaultdict(list)
            for row in session.scalars(
                select(Forecast).order_by(
                    Forecast.forecast_timestamp,
                    Forecast.created_at,
                )
            ):
                forecasts_by_hour[_hour_key(row.forecast_timestamp)].append(row)

            rows, skipped = self._build_rows(
                snapshots=snapshots,
                weather_by_hour=weather_by_hour,
                forecasts_by_hour=forecasts_by_hour,
                horizons_hours=horizons_hours,
            )

            if replace_existing:
                session.execute(delete(ForecastTrainingRow))
                session.flush()

            session.add_all(rows)
            session.commit()

        return ForecastDatasetBuildResult(
            rows_created=len(rows),
            source_snapshots=len(snapshots),
            skipped_rows=skipped,
        )

    def build_inference_rows(
        self,
        horizons_hours: tuple[int, ...] = FORECAST_HORIZONS_HOURS,
        as_of: datetime | None = None,
    ) -> dict[int, ForecastTrainingRow]:
        if self.session_factory is SessionLocal:
            initialize_database()

        with self.session_factory() as session:
            snapshots = list(
                session.scalars(
                    select(ScadaGridSnapshot).order_by(ScadaGridSnapshot.timestamp)
                )
            )
            weather_by_hour = {
                _hour_key(row.timestamp): row
                for row in session.scalars(
                    select(Weather).order_by(Weather.timestamp, Weather.created_at)
                )
            }
            forecasts_by_hour: dict[datetime, list[Forecast]] = defaultdict(list)
            for row in session.scalars(
                select(Forecast).order_by(
                    Forecast.forecast_timestamp,
                    Forecast.created_at,
                )
            ):
                forecasts_by_hour[_hour_key(row.forecast_timestamp)].append(row)

        if not snapshots:
            return {}
        latest_snapshot = snapshots[-1]
        if (
            latest_snapshot.current_demand_mw is None
            or latest_snapshot.quality_status != "GOOD"
            or bool(latest_snapshot.missing_fields.strip())
        ):
            return {}

        feature_timestamp = _hour_key(latest_snapshot.timestamp)
        snapshot_by_hour = {
            _hour_key(snapshot.timestamp): snapshot for snapshot in snapshots
        }
        weather = weather_by_hour.get(feature_timestamp)
        available_at = _naive_utc(as_of or datetime.now(timezone.utc))
        rows: dict[int, ForecastTrainingRow] = {}
        for horizon_hours in horizons_hours:
            target_timestamp = feature_timestamp + timedelta(hours=horizon_hours)
            forecast = self._forecast_available_at(
                forecasts_by_hour.get(target_timestamp, []),
                available_at,
            )
            rows[horizon_hours] = self._inference_row(
                snapshot=latest_snapshot,
                feature_timestamp=feature_timestamp,
                target_timestamp=target_timestamp,
                horizon_hours=horizon_hours,
                snapshot_by_hour=snapshot_by_hour,
                weather=weather,
                forecast=forecast,
            )
        return rows

    def _build_rows(
        self,
        snapshots: list[ScadaGridSnapshot],
        weather_by_hour: dict[datetime, Weather],
        forecasts_by_hour: dict[datetime, list[Forecast]],
        horizons_hours: tuple[int, ...],
    ) -> tuple[list[ForecastTrainingRow], int]:
        snapshot_by_hour = {_hour_key(snapshot.timestamp): snapshot for snapshot in snapshots}
        rows: list[ForecastTrainingRow] = []
        skipped = 0

        for snapshot in snapshots:
            feature_timestamp = _hour_key(snapshot.timestamp)
            if snapshot.current_demand_mw is None:
                skipped += len(horizons_hours)
                continue

            for horizon_hours in horizons_hours:
                target_timestamp = feature_timestamp + timedelta(hours=horizon_hours)
                target_snapshot = snapshot_by_hour.get(target_timestamp)
                if (
                    target_snapshot is None
                    or target_snapshot.current_demand_mw is None
                    or target_timestamp <= feature_timestamp
                ):
                    skipped += 1
                    continue

                weather = weather_by_hour.get(feature_timestamp)
                forecast = self._forecast_available_at(
                    forecasts_by_hour.get(target_timestamp, []),
                    feature_timestamp,
                )
                rows.append(
                    self._training_row(
                        snapshot=snapshot,
                        feature_timestamp=feature_timestamp,
                        target_snapshot=target_snapshot,
                        target_timestamp=target_timestamp,
                        horizon_hours=horizon_hours,
                        snapshot_by_hour=snapshot_by_hour,
                        weather=weather,
                        forecast=forecast,
                    )
                )

        return rows, skipped

    def _training_row(
        self,
        snapshot: ScadaGridSnapshot,
        feature_timestamp: datetime,
        target_snapshot: ScadaGridSnapshot,
        target_timestamp: datetime,
        horizon_hours: int,
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        weather: Weather | None,
        forecast: Forecast | None,
    ) -> ForecastTrainingRow:
        return ForecastTrainingRow(
            feature_timestamp=feature_timestamp,
            horizon_hours=horizon_hours,
            target_timestamp=target_timestamp,
            target_demand_mw=target_snapshot.current_demand_mw,
            current_demand_mw=snapshot.current_demand_mw,
            lag_1h_demand_mw=self._lag_demand(snapshot_by_hour, feature_timestamp, 1),
            lag_2h_demand_mw=self._lag_demand(snapshot_by_hour, feature_timestamp, 2),
            lag_24h_demand_mw=self._lag_demand(snapshot_by_hour, feature_timestamp, 24),
            rolling_3h_demand_mw=self._rolling_average(snapshot_by_hour, feature_timestamp, 3),
            rolling_6h_demand_mw=self._rolling_average(snapshot_by_hour, feature_timestamp, 6),
            spinning_reserve_mw=snapshot.spinning_reserve_mw,
            available_capacity_mw=snapshot.available_capacity_mw,
            online_capacity_mw=snapshot.online_capacity_mw,
            reserve_margin_mw=snapshot.reserve_margin_mw,
            online_spare_mw=snapshot.online_spare_mw,
            hour_of_day=feature_timestamp.hour,
            day_of_week=feature_timestamp.weekday(),
            temperature_c=(
                weather.temperature_c
                if weather is not None
                else snapshot.temperature_c
            ),
            humidity_percent=weather.humidity_percent if weather is not None else None,
            rainfall_mm_hr=weather.rainfall_mm_hr if weather is not None else None,
            cloud_cover_percent=(
                weather.cloud_cover_percent if weather is not None else None
            ),
            wind_speed_kmh=weather.wind_speed_kph if weather is not None else None,
            pressure_hpa=weather.pressure_hpa if weather is not None else None,
            forecast_temperature_c=(
                forecast.temperature_c if forecast is not None else None
            ),
            forecast_humidity_percent=(
                forecast.humidity_percent if forecast is not None else None
            ),
            forecast_rainfall_mm_hr=(
                forecast.rainfall_mm_hr if forecast is not None else None
            ),
            forecast_cloud_cover_percent=(
                forecast.cloud_cover_percent if forecast is not None else None
            ),
            forecast_wind_speed_kmh=(
                forecast.wind_speed_kph if forecast is not None else None
            ),
            forecast_precipitation_probability_percent=(
                forecast.precipitation_probability_percent
                if forecast is not None
                else None
            ),
            source_quality_status=self._source_quality(
                snapshot,
                target_snapshot,
                weather,
                forecast,
            ),
        )

    def _inference_row(
        self,
        snapshot: ScadaGridSnapshot,
        feature_timestamp: datetime,
        target_timestamp: datetime,
        horizon_hours: int,
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        weather: Weather | None,
        forecast: Forecast | None,
    ) -> ForecastTrainingRow:
        assert snapshot.current_demand_mw is not None
        return ForecastTrainingRow(
            feature_timestamp=feature_timestamp,
            horizon_hours=horizon_hours,
            target_timestamp=target_timestamp,
            target_demand_mw=snapshot.current_demand_mw,
            current_demand_mw=snapshot.current_demand_mw,
            lag_1h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                feature_timestamp,
                1,
            ),
            lag_2h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                feature_timestamp,
                2,
            ),
            lag_24h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                feature_timestamp,
                24,
            ),
            rolling_3h_demand_mw=self._rolling_average(
                snapshot_by_hour,
                feature_timestamp,
                3,
            ),
            rolling_6h_demand_mw=self._rolling_average(
                snapshot_by_hour,
                feature_timestamp,
                6,
            ),
            spinning_reserve_mw=snapshot.spinning_reserve_mw,
            available_capacity_mw=snapshot.available_capacity_mw,
            online_capacity_mw=snapshot.online_capacity_mw,
            reserve_margin_mw=snapshot.reserve_margin_mw,
            online_spare_mw=snapshot.online_spare_mw,
            hour_of_day=feature_timestamp.hour,
            day_of_week=feature_timestamp.weekday(),
            temperature_c=(
                weather.temperature_c if weather is not None else snapshot.temperature_c
            ),
            humidity_percent=weather.humidity_percent if weather is not None else None,
            rainfall_mm_hr=weather.rainfall_mm_hr if weather is not None else None,
            cloud_cover_percent=(
                weather.cloud_cover_percent if weather is not None else None
            ),
            wind_speed_kmh=weather.wind_speed_kph if weather is not None else None,
            pressure_hpa=weather.pressure_hpa if weather is not None else None,
            forecast_temperature_c=(
                forecast.temperature_c if forecast is not None else None
            ),
            forecast_humidity_percent=(
                forecast.humidity_percent if forecast is not None else None
            ),
            forecast_rainfall_mm_hr=(
                forecast.rainfall_mm_hr if forecast is not None else None
            ),
            forecast_cloud_cover_percent=(
                forecast.cloud_cover_percent if forecast is not None else None
            ),
            forecast_wind_speed_kmh=(
                forecast.wind_speed_kph if forecast is not None else None
            ),
            forecast_precipitation_probability_percent=(
                forecast.precipitation_probability_percent
                if forecast is not None
                else None
            ),
            source_quality_status=(
                "GOOD" if weather is not None and forecast is not None else "WEATHER_DEGRADED"
            ),
        )

    @staticmethod
    def _forecast_available_at(
        forecasts: list[Forecast],
        feature_timestamp: datetime,
    ) -> Forecast | None:
        available = [
            forecast
            for forecast in forecasts
            if _naive_utc(forecast.created_at) <= feature_timestamp
        ]
        if not available:
            return None
        return max(available, key=lambda row: _naive_utc(row.created_at))

    @staticmethod
    def _lag_demand(
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        timestamp: datetime,
        lag_hours: int,
    ) -> float | None:
        lagged = snapshot_by_hour.get(timestamp - timedelta(hours=lag_hours))
        return lagged.current_demand_mw if lagged is not None else None

    @staticmethod
    def _rolling_average(
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        timestamp: datetime,
        window_hours: int,
    ) -> float | None:
        values: list[float] = []
        for offset in range(window_hours):
            row = snapshot_by_hour.get(timestamp - timedelta(hours=offset))
            if row is not None and row.current_demand_mw is not None:
                values.append(row.current_demand_mw)
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    @staticmethod
    def _source_quality(
        snapshot: ScadaGridSnapshot,
        target_snapshot: ScadaGridSnapshot,
        weather: Weather | None,
        forecast: Forecast | None,
    ) -> str:
        if snapshot.quality_status != "GOOD" or target_snapshot.quality_status != "GOOD":
            return "SCADA_DEGRADED"
        if weather is None or forecast is None:
            return "WEATHER_DEGRADED"
        return "GOOD"


def _hour_key(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0, tzinfo=None)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
