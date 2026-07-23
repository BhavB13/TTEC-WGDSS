from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.database.init_db import initialize_database
from app.database.session import SessionLocal
from app.models.demand_forecast import ForecastTrainingRow
from app.models.forecast import Forecast
from app.models.scada import ScadaGridSnapshot
from app.models.weather import Weather
from app.services.data_period_policy import DataPeriodPolicy

FORECAST_HORIZONS_HOURS = (1, 2, 3, 4, 5, 6)
TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")


@dataclass(frozen=True)
class ForecastDatasetBuildResult:
    rows_created: int
    source_snapshots: int
    skipped_rows: int


@dataclass(frozen=True)
class ForecastEvaluationDataset:
    rows: list[ForecastTrainingRow]
    inference_rows: dict[int, ForecastTrainingRow]
    source_snapshots: int
    skipped_rows: int
    as_of: datetime


@dataclass(frozen=True)
class _HistoricalWeatherForecast:
    temperature_c: float
    humidity_percent: float
    rainfall_mm_hr: float
    cloud_cover_percent: float
    wind_speed_kph: float
    precipitation_probability_percent: float
    provider_name: str
    created_at: datetime


class ForecastDatasetService:
    def __init__(
        self,
        session_factory=SessionLocal,
        enforce_period_policy: bool | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.period_policy = DataPeriodPolicy.from_settings()
        self.enforce_period_policy = (
            session_factory is SessionLocal
            if enforce_period_policy is None
            else enforce_period_policy
        )

    def build_training_rows(
        self,
        horizons_hours: tuple[int, ...] = FORECAST_HORIZONS_HOURS,
        replace_existing: bool = True,
    ) -> ForecastDatasetBuildResult:
        if self.session_factory is SessionLocal:
            initialize_database()

        with self.session_factory() as session:
            query = select(ScadaGridSnapshot)
            if self.enforce_period_policy:
                query = query.where(
                    ScadaGridSnapshot.timestamp >= self.period_policy.training_start_at,
                    ScadaGridSnapshot.timestamp < self.period_policy.training_end_exclusive,
                )
            snapshots = list(
                session.scalars(query.order_by(ScadaGridSnapshot.timestamp))
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

        if as_of is not None:
            available_at = _local_naive(as_of)
        elif snapshots:
            # Offline training/replay must follow the data clock, not the wall
            # clock. Live callers can provide an explicit as_of cutoff.
            available_at = max(_snapshot_issue_time(snapshot) for snapshot in snapshots)
        else:
            available_at = _local_naive(datetime.now(timezone.utc))
        return self._inference_rows_from_collections(
            snapshots=snapshots,
            weather_by_hour=weather_by_hour,
            forecasts_by_hour=forecasts_by_hour,
            horizons_hours=horizons_hours,
            available_at=available_at,
        )

    def build_evaluation_dataset(
        self,
        as_of: datetime,
        horizons_hours: tuple[int, ...] = FORECAST_HORIZONS_HOURS,
    ) -> ForecastEvaluationDataset:
        """Build transient model rows using only intervals available by a replay cutoff."""
        cutoff = _local_naive(as_of)
        with self.session_factory() as session:
            snapshots = [
                snapshot
                for snapshot in session.scalars(
                    select(ScadaGridSnapshot).order_by(ScadaGridSnapshot.timestamp)
                )
                if _snapshot_available_at(snapshot) <= cutoff
                and _snapshot_issue_time(snapshot) <= cutoff
            ]
            weather_by_hour = {
                _hour_key(row.timestamp): row
                for row in session.scalars(select(Weather).order_by(Weather.timestamp))
                if _hour_key(row.timestamp) <= cutoff
            }
            forecasts_by_hour: dict[datetime, list[Forecast]] = defaultdict(list)
            for row in session.scalars(
                select(Forecast).order_by(
                    Forecast.forecast_timestamp,
                    Forecast.created_at,
                )
            ):
                forecasts_by_hour[_hour_key(row.forecast_timestamp)].append(row)

        training_snapshots = (
            [
                snapshot
                for snapshot in snapshots
                if self.period_policy.is_training_timestamp(snapshot.timestamp)
            ]
            if self.enforce_period_policy
            else snapshots
        )
        rows, skipped = self._build_rows(
            snapshots=training_snapshots,
            weather_by_hour=weather_by_hour,
            forecasts_by_hour=forecasts_by_hour,
            horizons_hours=horizons_hours,
        )
        inference_rows = self._inference_rows_from_collections(
            snapshots=snapshots,
            weather_by_hour=weather_by_hour,
            forecasts_by_hour=forecasts_by_hour,
            horizons_hours=horizons_hours,
            available_at=cutoff,
        )
        return ForecastEvaluationDataset(
            rows=rows,
            inference_rows=inference_rows,
            source_snapshots=len(snapshots),
            skipped_rows=skipped,
            as_of=cutoff,
        )

    def _inference_rows_from_collections(
        self,
        snapshots: list[ScadaGridSnapshot],
        weather_by_hour: dict[datetime, Weather],
        forecasts_by_hour: dict[datetime, list[Forecast]],
        horizons_hours: tuple[int, ...],
        available_at: datetime,
    ) -> dict[int, ForecastTrainingRow]:
        feature_timestamp = _hour_key(available_at)
        available = [
            snapshot
            for snapshot in snapshots
            if _snapshot_available_at(snapshot) <= feature_timestamp
        ]
        if not available:
            return {}
        latest_snapshot = max(
            available,
            key=lambda item: _snapshot_bucket_start(item),
        )
        if (
            latest_snapshot.current_demand_mw is None
            or _demand_snapshot_quality(latest_snapshot) == "UNUSABLE"
        ):
            return {}
        snapshot_by_hour = _snapshots_by_observation_hour(snapshots)
        observation_timestamp = _snapshot_bucket_start(latest_snapshot)
        weather = weather_by_hour.get(feature_timestamp)
        rows: dict[int, ForecastTrainingRow] = {}
        for horizon_hours in horizons_hours:
            target_timestamp = feature_timestamp + timedelta(hours=horizon_hours)
            forecast = self._forecast_available_at(
                forecasts_by_hour.get(target_timestamp, []),
                available_at,
            )
            forecast = forecast or self._historical_weather_forecast(
                weather_by_hour,
                target_timestamp,
                feature_timestamp,
            )
            rows[horizon_hours] = self._inference_row(
                snapshot=latest_snapshot,
                feature_timestamp=feature_timestamp,
                target_timestamp=target_timestamp,
                horizon_hours=horizon_hours,
                snapshot_by_hour=snapshot_by_hour,
                observation_timestamp=observation_timestamp,
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
        snapshot_by_hour = _snapshots_by_observation_hour(snapshots)
        snapshots_by_issue = _latest_snapshots_by_issue_hour(snapshots)
        rows: list[ForecastTrainingRow] = []
        skipped = 0

        for feature_timestamp, snapshot in sorted(snapshots_by_issue.items()):
            if snapshot.current_demand_mw is None:
                skipped += len(horizons_hours)
                continue
            observation_timestamp = _snapshot_bucket_start(snapshot)

            for horizon_hours in horizons_hours:
                target_timestamp = feature_timestamp + timedelta(hours=horizon_hours)
                target_snapshot = snapshot_by_hour.get(target_timestamp)
                if (
                    target_snapshot is None
                    or target_snapshot.current_demand_mw is None
                    or target_timestamp <= feature_timestamp
                    or _snapshot_available_at(target_snapshot) <= feature_timestamp
                ):
                    skipped += 1
                    continue

                weather = weather_by_hour.get(feature_timestamp)
                forecast = self._forecast_available_at(
                    forecasts_by_hour.get(target_timestamp, []),
                    feature_timestamp,
                )
                forecast = forecast or self._historical_weather_forecast(
                    weather_by_hour,
                    target_timestamp,
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
                        observation_timestamp=observation_timestamp,
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
        observation_timestamp: datetime,
        weather: Weather | None,
        forecast: Forecast | _HistoricalWeatherForecast | None,
    ) -> ForecastTrainingRow:
        return ForecastTrainingRow(
            feature_timestamp=feature_timestamp,
            feature_observation_time=_snapshot_observation_time(snapshot),
            feature_available_at=_snapshot_available_at(snapshot),
            horizon_hours=horizon_hours,
            target_timestamp=target_timestamp,
            target_observation_time=_snapshot_observation_time(target_snapshot),
            target_available_at=_snapshot_available_at(target_snapshot),
            target_demand_mw=target_snapshot.current_demand_mw,
            current_demand_mw=snapshot.current_demand_mw,
            lag_1h_demand_mw=self._lag_demand(snapshot_by_hour, observation_timestamp, 1),
            lag_2h_demand_mw=self._lag_demand(snapshot_by_hour, observation_timestamp, 2),
            lag_3h_demand_mw=self._lag_demand(snapshot_by_hour, observation_timestamp, 3),
            lag_6h_demand_mw=self._lag_demand(snapshot_by_hour, observation_timestamp, 6),
            lag_24h_demand_mw=self._lag_demand(snapshot_by_hour, observation_timestamp, 24),
            lag_48h_demand_mw=self._lag_demand(snapshot_by_hour, observation_timestamp, 48),
            lag_168h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                observation_timestamp,
                168,
            ),
            target_lag_24h_demand_mw=self._target_lag_demand(
                snapshot_by_hour,
                target_timestamp,
                feature_timestamp,
                24,
            ),
            target_lag_48h_demand_mw=self._target_lag_demand(
                snapshot_by_hour,
                target_timestamp,
                feature_timestamp,
                48,
            ),
            target_lag_168h_demand_mw=self._target_lag_demand(
                snapshot_by_hour,
                target_timestamp,
                feature_timestamp,
                168,
            ),
            rolling_3h_demand_mw=self._rolling_average(snapshot_by_hour, observation_timestamp, 3),
            rolling_6h_demand_mw=self._rolling_average(snapshot_by_hour, observation_timestamp, 6),
            rolling_12h_demand_mw=self._rolling_average(
                snapshot_by_hour,
                observation_timestamp,
                12,
            ),
            rolling_24h_demand_mw=self._rolling_average(
                snapshot_by_hour, observation_timestamp, 24
            ),
            rolling_168h_demand_mw=self._rolling_average(
                snapshot_by_hour,
                observation_timestamp,
                168,
            ),
            same_hour_7d_average_mw=self._same_hour_average(
                snapshot_by_hour,
                observation_timestamp,
                7,
            ),
            target_same_hour_7d_average_mw=self._target_same_hour_average(
                snapshot_by_hour,
                target_timestamp,
                feature_timestamp,
                7,
            ),
            demand_volatility_6h_mw=self._rolling_stddev(
                snapshot_by_hour,
                observation_timestamp,
                "current_demand_mw",
                6,
            ),
            demand_rate_1h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "current_demand_mw", 1
            ),
            demand_rate_3h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "current_demand_mw", 3
            ),
            demand_rate_6h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "current_demand_mw", 6
            ),
            spinning_reserve_mw=snapshot.spinning_reserve_mw,
            available_capacity_mw=snapshot.available_capacity_mw,
            online_capacity_mw=snapshot.online_capacity_mw,
            reserve_margin_mw=snapshot.reserve_margin_mw,
            online_spare_mw=snapshot.online_spare_mw,
            spinning_reserve_lag_1h_mw=self._lag_value(
                snapshot_by_hour, observation_timestamp, "spinning_reserve_mw", 1
            ),
            available_capacity_lag_1h_mw=self._lag_value(
                snapshot_by_hour, observation_timestamp, "available_capacity_mw", 1
            ),
            online_capacity_lag_1h_mw=self._lag_value(
                snapshot_by_hour, observation_timestamp, "online_capacity_mw", 1
            ),
            spinning_reserve_rate_1h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "spinning_reserve_mw", 1
            ),
            available_capacity_rate_1h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "available_capacity_mw", 1
            ),
            online_capacity_rate_1h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "online_capacity_mw", 1
            ),
            hour_of_day=feature_timestamp.hour,
            day_of_week=feature_timestamp.weekday(),
            temperature_c=(
                snapshot.temperature_c
                if snapshot.temperature_c is not None
                else weather.temperature_c
                if weather is not None
                else None
            ),
            scada_temperature_c=snapshot.temperature_c,
            temperature_lag_1h_c=self._lag_value(
                snapshot_by_hour, observation_timestamp, "temperature_c", 1
            ),
            rolling_3h_temperature_c=self._rolling_value(
                snapshot_by_hour, observation_timestamp, "temperature_c", 3
            ),
            temperature_rate_1h_c=self._rate(
                snapshot_by_hour, observation_timestamp, "temperature_c", 1
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
            forecast_weather_source=(forecast.provider_name if forecast is not None else None),
            forecast_weather_issued_at=(forecast.created_at if forecast is not None else None),
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
        observation_timestamp: datetime,
        weather: Weather | None,
        forecast: Forecast | _HistoricalWeatherForecast | None,
    ) -> ForecastTrainingRow:
        assert snapshot.current_demand_mw is not None
        return ForecastTrainingRow(
            feature_timestamp=feature_timestamp,
            feature_observation_time=_snapshot_observation_time(snapshot),
            feature_available_at=_snapshot_available_at(snapshot),
            horizon_hours=horizon_hours,
            target_timestamp=target_timestamp,
            target_observation_time=None,
            target_available_at=None,
            target_demand_mw=snapshot.current_demand_mw,
            current_demand_mw=snapshot.current_demand_mw,
            lag_1h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                observation_timestamp,
                1,
            ),
            lag_2h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                observation_timestamp,
                2,
            ),
            lag_3h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                observation_timestamp,
                3,
            ),
            lag_6h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                observation_timestamp,
                6,
            ),
            lag_24h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                observation_timestamp,
                24,
            ),
            lag_48h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                observation_timestamp,
                48,
            ),
            lag_168h_demand_mw=self._lag_demand(
                snapshot_by_hour,
                observation_timestamp,
                168,
            ),
            target_lag_24h_demand_mw=self._target_lag_demand(
                snapshot_by_hour,
                target_timestamp,
                feature_timestamp,
                24,
            ),
            target_lag_48h_demand_mw=self._target_lag_demand(
                snapshot_by_hour,
                target_timestamp,
                feature_timestamp,
                48,
            ),
            target_lag_168h_demand_mw=self._target_lag_demand(
                snapshot_by_hour,
                target_timestamp,
                feature_timestamp,
                168,
            ),
            rolling_3h_demand_mw=self._rolling_average(
                snapshot_by_hour,
                observation_timestamp,
                3,
            ),
            rolling_6h_demand_mw=self._rolling_average(
                snapshot_by_hour,
                observation_timestamp,
                6,
            ),
            rolling_12h_demand_mw=self._rolling_average(
                snapshot_by_hour,
                observation_timestamp,
                12,
            ),
            rolling_24h_demand_mw=self._rolling_average(
                snapshot_by_hour,
                observation_timestamp,
                24,
            ),
            rolling_168h_demand_mw=self._rolling_average(
                snapshot_by_hour,
                observation_timestamp,
                168,
            ),
            same_hour_7d_average_mw=self._same_hour_average(
                snapshot_by_hour,
                observation_timestamp,
                7,
            ),
            target_same_hour_7d_average_mw=self._target_same_hour_average(
                snapshot_by_hour,
                target_timestamp,
                feature_timestamp,
                7,
            ),
            demand_volatility_6h_mw=self._rolling_stddev(
                snapshot_by_hour,
                observation_timestamp,
                "current_demand_mw",
                6,
            ),
            demand_rate_1h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "current_demand_mw", 1
            ),
            demand_rate_3h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "current_demand_mw", 3
            ),
            demand_rate_6h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "current_demand_mw", 6
            ),
            spinning_reserve_mw=snapshot.spinning_reserve_mw,
            available_capacity_mw=snapshot.available_capacity_mw,
            online_capacity_mw=snapshot.online_capacity_mw,
            reserve_margin_mw=snapshot.reserve_margin_mw,
            online_spare_mw=snapshot.online_spare_mw,
            spinning_reserve_lag_1h_mw=self._lag_value(
                snapshot_by_hour, observation_timestamp, "spinning_reserve_mw", 1
            ),
            available_capacity_lag_1h_mw=self._lag_value(
                snapshot_by_hour, observation_timestamp, "available_capacity_mw", 1
            ),
            online_capacity_lag_1h_mw=self._lag_value(
                snapshot_by_hour, observation_timestamp, "online_capacity_mw", 1
            ),
            spinning_reserve_rate_1h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "spinning_reserve_mw", 1
            ),
            available_capacity_rate_1h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "available_capacity_mw", 1
            ),
            online_capacity_rate_1h_mw=self._rate(
                snapshot_by_hour, observation_timestamp, "online_capacity_mw", 1
            ),
            hour_of_day=feature_timestamp.hour,
            day_of_week=feature_timestamp.weekday(),
            temperature_c=(
                snapshot.temperature_c
                if snapshot.temperature_c is not None
                else weather.temperature_c
                if weather is not None
                else None
            ),
            scada_temperature_c=snapshot.temperature_c,
            temperature_lag_1h_c=self._lag_value(
                snapshot_by_hour, observation_timestamp, "temperature_c", 1
            ),
            rolling_3h_temperature_c=self._rolling_value(
                snapshot_by_hour, observation_timestamp, "temperature_c", 3
            ),
            temperature_rate_1h_c=self._rate(
                snapshot_by_hour, observation_timestamp, "temperature_c", 1
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
            forecast_weather_source=(forecast.provider_name if forecast is not None else None),
            forecast_weather_issued_at=(forecast.created_at if forecast is not None else None),
            source_quality_status=self._inference_quality(snapshot, weather, forecast),
        )

    @staticmethod
    def _forecast_available_at(
        forecasts: list[Forecast],
        feature_timestamp: datetime,
    ) -> Forecast | None:
        available = [
            forecast
            for forecast in forecasts
            if _local_naive(forecast.created_at) <= feature_timestamp
        ]
        if not available:
            return None
        return max(available, key=lambda row: _local_naive(row.created_at))

    @staticmethod
    def _historical_weather_forecast(
        weather_by_hour: dict[datetime, Weather],
        target_timestamp: datetime,
        feature_timestamp: datetime,
    ) -> _HistoricalWeatherForecast | None:
        available = [
            (timestamp, weather)
            for timestamp, weather in weather_by_hour.items()
            if timestamp <= feature_timestamp
        ]
        if not available:
            return None
        same_hour = [
            weather
            for timestamp, weather in available
            if timestamp.hour == target_timestamp.hour
        ][-21:]
        samples = same_hour or [weather for _, weather in available[-24:]]
        rainy_samples = sum(1 for weather in samples if weather.rainfall_mm_hr > 0)
        return _HistoricalWeatherForecast(
            temperature_c=round(mean(row.temperature_c for row in samples), 4),
            humidity_percent=round(mean(row.humidity_percent for row in samples), 4),
            rainfall_mm_hr=round(mean(row.rainfall_mm_hr for row in samples), 4),
            cloud_cover_percent=round(
                mean(row.cloud_cover_percent for row in samples),
                4,
            ),
            wind_speed_kph=round(mean(row.wind_speed_kph for row in samples), 4),
            precipitation_probability_percent=round(
                rainy_samples / len(samples) * 100.0,
                2,
            ),
            provider_name="Historical Weather Baseline (past observations only)",
            created_at=feature_timestamp,
        )

    @staticmethod
    def _lag_demand(
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        timestamp: datetime,
        lag_hours: int,
    ) -> float | None:
        lagged = snapshot_by_hour.get(timestamp - timedelta(hours=lag_hours))
        return lagged.current_demand_mw if lagged is not None else None

    @staticmethod
    def _target_lag_demand(
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        target_timestamp: datetime,
        feature_timestamp: datetime,
        lag_hours: int,
    ) -> float | None:
        lagged = snapshot_by_hour.get(target_timestamp - timedelta(hours=lag_hours))
        if (
            lagged is None
            or lagged.current_demand_mw is None
            or _snapshot_available_at(lagged) > feature_timestamp
        ):
            return None
        return float(lagged.current_demand_mw)

    @staticmethod
    def _lag_value(
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        timestamp: datetime,
        field_name: str,
        lag_hours: int,
    ) -> float | None:
        lagged = snapshot_by_hour.get(timestamp - timedelta(hours=lag_hours))
        if lagged is None:
            return None
        value = getattr(lagged, field_name, None)
        return float(value) if value is not None else None

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
    def _rolling_value(
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        timestamp: datetime,
        field_name: str,
        window_hours: int,
    ) -> float | None:
        values: list[float] = []
        for offset in range(window_hours):
            row = snapshot_by_hour.get(timestamp - timedelta(hours=offset))
            value = getattr(row, field_name, None) if row is not None else None
            if value is not None:
                values.append(float(value))
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    @staticmethod
    def _same_hour_average(
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        timestamp: datetime,
        day_count: int,
    ) -> float | None:
        values = [
            row.current_demand_mw
            for day_offset in range(1, day_count + 1)
            if (
                row := snapshot_by_hour.get(
                    timestamp - timedelta(hours=24 * day_offset)
                )
            )
            is not None
            and row.current_demand_mw is not None
        ]
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    @staticmethod
    def _target_same_hour_average(
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        target_timestamp: datetime,
        feature_timestamp: datetime,
        day_count: int,
    ) -> float | None:
        values: list[float] = []
        for day_offset in range(1, day_count + 1):
            row = snapshot_by_hour.get(
                target_timestamp - timedelta(hours=24 * day_offset)
            )
            if (
                row is not None
                and row.current_demand_mw is not None
                and _snapshot_available_at(row) <= feature_timestamp
            ):
                values.append(float(row.current_demand_mw))
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    @staticmethod
    def _rolling_stddev(
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        timestamp: datetime,
        field_name: str,
        window_hours: int,
    ) -> float | None:
        values: list[float] = []
        for offset in range(window_hours):
            row = snapshot_by_hour.get(timestamp - timedelta(hours=offset))
            value = getattr(row, field_name, None) if row is not None else None
            if value is not None:
                values.append(float(value))
        if not values:
            return None
        average = sum(values) / len(values)
        variance = sum((value - average) ** 2 for value in values) / len(values)
        return round(variance**0.5, 4)

    @classmethod
    def _rate(
        cls,
        snapshot_by_hour: dict[datetime, ScadaGridSnapshot],
        timestamp: datetime,
        field_name: str,
        lag_hours: int,
    ) -> float | None:
        current = snapshot_by_hour.get(timestamp)
        current_value = getattr(current, field_name, None) if current is not None else None
        lagged_value = cls._lag_value(
            snapshot_by_hour,
            timestamp,
            field_name,
            lag_hours,
        )
        if current_value is None or lagged_value is None:
            return None
        return round((float(current_value) - lagged_value) / lag_hours, 4)

    @staticmethod
    def _source_quality(
        snapshot: ScadaGridSnapshot,
        target_snapshot: ScadaGridSnapshot,
        weather: Weather | None,
        forecast: Forecast | _HistoricalWeatherForecast | None,
    ) -> str:
        feature_scada = _demand_snapshot_quality(snapshot)
        target_scada = _demand_snapshot_quality(target_snapshot)
        if "UNUSABLE" in {feature_scada, target_scada}:
            return "SCADA_DEGRADED"
        if "PARTIAL" in {feature_scada, target_scada}:
            if weather is None or forecast is None:
                return "SCADA_PARTIAL_WEATHER_DEGRADED"
            if isinstance(forecast, _HistoricalWeatherForecast):
                return "SCADA_PARTIAL_WEATHER_BASELINE"
            return "SCADA_PARTIAL"
        if (
            snapshot.quality_status == "USABLE_WITH_WARNING"
            or target_snapshot.quality_status == "USABLE_WITH_WARNING"
        ):
            if weather is None or forecast is None:
                return "SCADA_ACCEPTED_WEATHER_DEGRADED"
            if isinstance(forecast, _HistoricalWeatherForecast):
                return "SCADA_ACCEPTED_WEATHER_BASELINE"
            return "SCADA_ACCEPTED"
        if weather is None or forecast is None:
            return "WEATHER_DEGRADED"
        if isinstance(forecast, _HistoricalWeatherForecast):
            return "WEATHER_BASELINE"
        return "GOOD"

    @staticmethod
    def _inference_quality(
        snapshot: ScadaGridSnapshot,
        weather: Weather | None,
        forecast: Forecast | _HistoricalWeatherForecast | None,
    ) -> str:
        scada_quality = _demand_snapshot_quality(snapshot)
        if scada_quality == "PARTIAL":
            if weather is None or forecast is None:
                return "SCADA_PARTIAL_WEATHER_DEGRADED"
            if isinstance(forecast, _HistoricalWeatherForecast):
                return "SCADA_PARTIAL_WEATHER_BASELINE"
            return "SCADA_PARTIAL"
        if snapshot.quality_status == "USABLE_WITH_WARNING":
            if weather is None or forecast is None:
                return "SCADA_ACCEPTED_WEATHER_DEGRADED"
            if isinstance(forecast, _HistoricalWeatherForecast):
                return "SCADA_ACCEPTED_WEATHER_BASELINE"
            return "SCADA_ACCEPTED"
        if isinstance(forecast, _HistoricalWeatherForecast):
            return "WEATHER_BASELINE"
        return "GOOD" if weather is not None and forecast is not None else "WEATHER_DEGRADED"


def _hour_key(value: datetime) -> datetime:
    return _local_naive(value).replace(minute=0, second=0, microsecond=0)


def _demand_snapshot_quality(snapshot: ScadaGridSnapshot) -> str:
    if snapshot.current_demand_mw is None:
        return "UNUSABLE"
    if snapshot.quality_status in {"GOOD", "USABLE_WITH_WARNING"}:
        return snapshot.quality_status
    missing = {
        value.strip()
        for value in snapshot.missing_fields.split(",")
        if value.strip()
    }
    if (
        snapshot.quality_status == "DEGRADED"
        and "current_demand_mw" not in missing
        and missing
    ):
        return "PARTIAL"
    return "UNUSABLE"


def _local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(TRINIDAD_TZ).replace(tzinfo=None)


def _snapshot_available_at(snapshot: ScadaGridSnapshot) -> datetime:
    # Legacy snapshots predate explicit availability metadata and used
    # `timestamp` as their issue-time key. Preserve that interpretation while
    # all newly built interval snapshots carry an exact `available_at`.
    return _local_naive(snapshot.available_at or snapshot.timestamp)


def _snapshot_observation_time(snapshot: ScadaGridSnapshot) -> datetime:
    return _snapshot_bucket_start(snapshot)


def _snapshot_bucket_start(snapshot: ScadaGridSnapshot) -> datetime:
    return _hour_key(snapshot.timestamp)


def _snapshot_issue_time(snapshot: ScadaGridSnapshot) -> datetime:
    available_at = _snapshot_available_at(snapshot)
    floored = _hour_key(available_at)
    return floored if available_at == floored else floored + timedelta(hours=1)


def _snapshots_by_observation_hour(
    snapshots: list[ScadaGridSnapshot],
) -> dict[datetime, ScadaGridSnapshot]:
    return {
        _snapshot_bucket_start(snapshot): snapshot
        for snapshot in sorted(snapshots, key=_snapshot_bucket_start)
    }


def _latest_snapshots_by_issue_hour(
    snapshots: list[ScadaGridSnapshot],
) -> dict[datetime, ScadaGridSnapshot]:
    """Choose the newest observation available at each actual update hour.

    The issue-hour map is used only to decide when a new as-of feature state is
    available. Targets and lags remain keyed by their observation hours, so two
    irregular buckets finalized in the same hour cannot overwrite historical
    demand values.
    """

    result: dict[datetime, ScadaGridSnapshot] = {}
    for snapshot in sorted(
        snapshots,
        key=lambda item: (_snapshot_available_at(item), _snapshot_bucket_start(item)),
    ):
        issue_time = _snapshot_issue_time(snapshot)
        existing = result.get(issue_time)
        if existing is None or _snapshot_bucket_start(snapshot) > _snapshot_bucket_start(existing):
            result[issue_time] = snapshot
    return result
