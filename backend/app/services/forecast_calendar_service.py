from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math


@dataclass(frozen=True)
class ForecastCalendarContext:
    day_type: str
    holiday_name: str | None
    season: str
    month: int
    day_of_year: int


def calendar_context(
    timestamp: datetime,
    extra_holiday_dates: str = "",
) -> ForecastCalendarContext:
    target_date = timestamp.date()
    holidays = trinidad_and_tobago_holidays(timestamp.year)
    for value in extra_holiday_dates.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            holidays[date.fromisoformat(value)] = "Configured holiday"
        except ValueError:
            continue

    holiday_name = holidays.get(target_date)
    if holiday_name is not None:
        day_type = "HOLIDAY"
    elif timestamp.weekday() >= 5:
        day_type = "WEEKEND"
    else:
        day_type = "WEEKDAY"
    return ForecastCalendarContext(
        day_type=day_type,
        holiday_name=holiday_name,
        season="DRY" if timestamp.month <= 5 else "WET",
        month=timestamp.month,
        day_of_year=timestamp.timetuple().tm_yday,
    )


def calendar_feature_vector(
    timestamp: datetime,
    extra_holiday_dates: str = "",
) -> tuple[float, ...]:
    context = calendar_context(timestamp, extra_holiday_dates)
    month_angle = 2.0 * math.pi * (context.month - 1) / 12.0
    year_angle = 2.0 * math.pi * (context.day_of_year - 1) / 365.25
    return (
        math.sin(month_angle),
        math.cos(month_angle),
        math.sin(year_angle),
        math.cos(year_angle),
        1.0 if context.day_type == "WEEKDAY" else 0.0,
        1.0 if context.day_type == "WEEKEND" else 0.0,
        1.0 if context.day_type == "HOLIDAY" else 0.0,
        1.0 if context.season == "DRY" else 0.0,
        1.0 if context.season == "WET" else 0.0,
    )


def trinidad_and_tobago_holidays(year: int) -> dict[date, str]:
    easter = _easter_sunday(year)
    return {
        date(year, 1, 1): "New Year's Day",
        easter - timedelta(days=48): "Carnival Monday",
        easter - timedelta(days=47): "Carnival Tuesday",
        date(year, 3, 30): "Spiritual Baptist Liberation Day",
        easter - timedelta(days=2): "Good Friday",
        easter + timedelta(days=1): "Easter Monday",
        date(year, 5, 30): "Indian Arrival Day",
        easter + timedelta(days=60): "Corpus Christi",
        date(year, 6, 19): "Labour Day",
        date(year, 8, 1): "Emancipation Day",
        date(year, 8, 31): "Independence Day",
        date(year, 9, 24): "Republic Day",
        date(year, 12, 25): "Christmas Day",
        date(year, 12, 26): "Boxing Day",
    }


def _easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = (h + ell - 7 * m + 114) % 31 + 1
    return date(year, month, day)
