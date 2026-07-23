from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.database.session import SessionLocal
from app.models.scada import ScadaGridSnapshot
from app.models.weather import Weather
from app.schemas.dashboard_time import (
    DashboardTimeContextResponse,
    DaySeriesPointResponse,
)
from app.services.data_period_policy import DataPeriodPolicy


class PresentDayService:
    """Resolve one June day against the active simulated-present cursor."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory
        self.policy = DataPeriodPolicy.from_settings()

    def context(
        self,
        *,
        selected_date: date | None,
        present_at: datetime,
        present_source: str,
    ) -> DashboardTimeContextResponse:
        present_at = present_at.replace(tzinfo=None)
        active_date = present_at.date()
        available_dates = [
            item for item in self._available_dates() if item <= active_date
        ]
        selected = selected_date or active_date
        if selected_date is not None and selected not in available_dates:
            if not available_dates:
                raise HTTPException(
                    status_code=503,
                    detail="June SCADA replay archive is empty",
                )
            raise HTTPException(
                status_code=422,
                detail=(
                    f"selected_date must be an available June date between "
                    f"{available_dates[0]} and {available_dates[-1]}"
                ),
            )

        is_active_day = selected == active_date
        rows = self._rows(selected, selected) if selected in available_dates else []
        if is_active_day:
            rows = [row for row in rows if row.timestamp <= present_at]
        expected = min(24, present_at.hour + 1) if is_active_day else 24
        external_active_source = is_active_day and selected not in available_dates
        completeness = (
            100.0
            if external_active_source
            else min(100.0, len(rows) / expected * 100.0)
            if expected
            else 0.0
        )
        incomplete = (
            not external_active_source
            and (
                len(rows) < expected
                or any(
                    row.quality_status not in {"GOOD", "USABLE_WITH_WARNING"}
                    or bool(row.missing_fields.strip())
                    for row in rows
                )
            )
        )
        displayed_at = present_at if is_active_day else (
            rows[-1].timestamp if rows else datetime.combine(selected, time.min)
        )
        return DashboardTimeContextResponse(
            selected_date=selected,
            active_date=active_date,
            is_active_day=is_active_day,
            displayed_at=displayed_at,
            source=present_source if is_active_day else "AspenTech OSI June 2026 trend exports",
            value_classification=(
                "SIMULATED_LIVE" if is_active_day else "SIMULATED_REPLAY_DAY"
            ),
            available_start=(
                available_dates[0]
                if available_dates
                else self.policy.replay_archive_start
            ),
            available_end=(
                available_dates[-1]
                if available_dates
                else self.policy.replay_archive_end
            ),
            available_dates=available_dates,
            completeness_percent=round(completeness, 1),
            record_count=len(rows) if rows else 1 if external_active_source else 0,
            is_complete=not incomplete,
            notice=(
                "Active June SCADA export replay; read-only simulated-present data."
                if is_active_day
                else (
                    "Previous June day replay is incomplete; "
                    f"showing {len(rows)} of 24 expected hourly records."
                    if incomplete
                    else "Previous June day replay; showing completed archived observations."
                )
            ),
            series=self._series(rows),
        )

    def _available_dates(self) -> list[date]:
        with self.session_factory() as session:
            timestamps = session.scalars(
                select(ScadaGridSnapshot.timestamp)
                .where(
                    ScadaGridSnapshot.timestamp
                    >= self.policy.replay_archive_start_at,
                    ScadaGridSnapshot.timestamp
                    < self.policy.replay_archive_end_exclusive,
                )
                .order_by(ScadaGridSnapshot.timestamp)
            )
            return sorted({value.date() for value in timestamps})

    def weather_at(self, timestamp: datetime) -> Weather | None:
        hour = timestamp.replace(minute=0, second=0, microsecond=0, tzinfo=None)
        with self.session_factory() as session:
            return session.scalar(
                select(Weather)
                .where(
                    Weather.timestamp >= hour,
                    Weather.timestamp < hour + timedelta(hours=1),
                )
                .order_by(Weather.created_at.desc())
            )

    def _rows(self, start: date, end: date) -> list[ScadaGridSnapshot]:
        start_at = datetime.combine(start, time.min)
        end_at = datetime.combine(end + timedelta(days=1), time.min)
        with self.session_factory() as session:
            return list(
                session.scalars(
                    select(ScadaGridSnapshot)
                    .where(
                        ScadaGridSnapshot.timestamp >= start_at,
                        ScadaGridSnapshot.timestamp < end_at,
                    )
                    .order_by(ScadaGridSnapshot.timestamp)
                )
            )

    @staticmethod
    def _series(rows: list[ScadaGridSnapshot]) -> list[DaySeriesPointResponse]:
        return [
            DaySeriesPointResponse(
                timestamp=row.timestamp,
                demand_mw=row.current_demand_mw,
                generation_tra_mw=row.online_capacity_mw,
                spinning_reserve_mw=row.spinning_reserve_mw,
                available_capacity_mw=row.available_capacity_mw,
                temperature_c=row.temperature_c,
                quality_status=row.quality_status,
                completeness_percent=row.coverage_percent,
            )
            for row in rows
        ]
