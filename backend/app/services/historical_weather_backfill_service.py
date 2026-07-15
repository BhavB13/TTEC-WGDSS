from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import requests
from sqlalchemy import delete, func, select

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.scada import ScadaGridSnapshot
from app.models.weather import Weather


logger = logging.getLogger(__name__)
PROVIDER_NAME = "Open-Meteo Historical Weather"
MAX_BACKFILL_DAYS = 400


@dataclass(frozen=True)
class HistoricalWeatherBackfillResult:
    start_date: date
    end_date: date
    rows_received: int
    rows_stored: int
    provider_name: str = PROVIDER_NAME


class HistoricalWeatherBackfillService:
    """Backfill feature-time weather without pretending observations were forecasts."""

    def __init__(
        self,
        session_factory=SessionLocal,
        base_url: str | None = None,
        session: requests.Session | None = None,
        timeout_seconds: float | None = None,
        retry_attempts: int | None = None,
        backoff_seconds: float | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.base_url = base_url or settings.OPEN_METEO_ARCHIVE_URL
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds or settings.WEATHER_TIMEOUT_SECONDS
        self.retry_attempts = retry_attempts or settings.WEATHER_RETRY_ATTEMPTS
        self.backoff_seconds = (
            backoff_seconds
            if backoff_seconds is not None
            else settings.WEATHER_RETRY_BACKOFF_SECONDS
        )

    def backfill_scada_range(self) -> HistoricalWeatherBackfillResult:
        with self.session_factory() as session:
            start_at, end_at = session.execute(
                select(
                    func.min(ScadaGridSnapshot.timestamp),
                    func.max(ScadaGridSnapshot.timestamp),
                )
            ).one()
        if start_at is None or end_at is None:
            raise ValueError("No SCADA snapshots are available for weather backfill")
        return self.backfill(start_at.date(), end_at.date())

    def backfill(
        self,
        start_date: date,
        end_date: date,
        latitude: float = settings.DEFAULT_LATITUDE,
        longitude: float = settings.DEFAULT_LONGITUDE,
    ) -> HistoricalWeatherBackfillResult:
        if end_date < start_date:
            raise ValueError("Historical weather end date precedes start date")
        if (end_date - start_date).days + 1 > MAX_BACKFILL_DAYS:
            raise ValueError(
                f"Historical weather backfill is limited to {MAX_BACKFILL_DAYS} days per run"
            )
        payload = self._request_json(
            {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "hourly": ",".join(
                    (
                        "temperature_2m",
                        "relative_humidity_2m",
                        "rain",
                        "cloud_cover",
                        "wind_speed_10m",
                        "wind_direction_10m",
                        "surface_pressure",
                    )
                ),
                "timezone": "America/Port_of_Spain",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                "cell_selection": "nearest",
                "elevation": settings.WEATHER_SITE_ALTITUDE_METERS,
            }
        )
        rows = self._parse_rows(payload)
        if not rows:
            raise RuntimeError("Open-Meteo historical weather response contained no usable rows")

        first_timestamp = rows[0].timestamp
        last_timestamp = rows[-1].timestamp
        with self.session_factory() as session:
            session.execute(
                delete(Weather).where(
                    Weather.provider_name == PROVIDER_NAME,
                    Weather.timestamp >= first_timestamp,
                    Weather.timestamp <= last_timestamp,
                )
            )
            session.add_all(rows)
            session.commit()
        logger.info(
            "Stored %s historical weather rows for %s through %s",
            len(rows),
            start_date,
            end_date,
        )
        return HistoricalWeatherBackfillResult(
            start_date=start_date,
            end_date=end_date,
            rows_received=len(payload.get("hourly", {}).get("time", [])),
            rows_stored=len(rows),
        )

    def _request_json(self, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = self.session.get(
                    self.base_url,
                    params=params,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("error"):
                    raise RuntimeError(str(payload.get("reason") or "Open-Meteo error"))
                return payload
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt < self.retry_attempts:
                    time.sleep(self.backoff_seconds * attempt)
        raise RuntimeError("Historical weather backfill failed") from last_error

    @staticmethod
    def _parse_rows(payload: dict[str, Any]) -> list[Weather]:
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        rows: list[Weather] = []
        for index, value in enumerate(times):
            try:
                timestamp = datetime.fromisoformat(str(value))
                temperature = _number_at(hourly, "temperature_2m", index)
                humidity = _number_at(hourly, "relative_humidity_2m", index)
                rainfall = _number_at(hourly, "rain", index, 0.0)
                cloud = _number_at(hourly, "cloud_cover", index, 0.0)
                wind = _number_at(hourly, "wind_speed_10m", index, 0.0)
            except (TypeError, ValueError):
                continue
            if temperature is None or humidity is None:
                continue
            pressure = _number_at(hourly, "surface_pressure", index)
            wind_direction = _number_at(hourly, "wind_direction_10m", index)
            rows.append(
                Weather(
                    timestamp=timestamp,
                    temperature_c=temperature,
                    humidity_percent=humidity,
                    wind_speed_kph=wind or 0.0,
                    wind_direction_deg=wind_direction,
                    pressure_hpa=pressure,
                    precipitation_mm=rainfall,
                    rainfall_mm_hr=rainfall or 0.0,
                    cloud_cover_percent=cloud or 0.0,
                    weather_condition=_condition(rainfall or 0.0, cloud or 0.0),
                    heat_index_c=round(temperature + 0.033 * humidity - 0.70, 2),
                    rain_severity=_rain_severity(rainfall or 0.0),
                    provider_name=PROVIDER_NAME,
                    created_at=timestamp,
                )
            )
        return rows


def _number_at(
    hourly: dict[str, Any],
    field_name: str,
    index: int,
    default: float | None = None,
) -> float | None:
    values = hourly.get(field_name) or []
    if index >= len(values) or values[index] is None:
        return default
    return float(values[index])


def _condition(rainfall: float, cloud: float) -> str:
    if rainfall >= 8:
        return "Heavy rain"
    if rainfall >= 2:
        return "Rain"
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
