from datetime import datetime

from app.services.forecast_calendar_service import (
    calendar_context,
    calendar_feature_vector,
)


def test_calendar_separates_weekdays_weekends_holidays_and_seasons():
    weekday = calendar_context(datetime(2026, 7, 15, 16))
    weekend = calendar_context(datetime(2026, 7, 18, 16))
    holiday = calendar_context(datetime(2026, 8, 31, 16))
    configured = calendar_context(
        datetime(2026, 11, 9, 16),
        "2026-11-09",
    )

    assert weekday.day_type == "WEEKDAY"
    assert weekday.season == "WET"
    assert weekend.day_type == "WEEKEND"
    assert holiday.day_type == "HOLIDAY"
    assert holiday.holiday_name == "Independence Day"
    assert configured.day_type == "HOLIDAY"
    assert configured.holiday_name == "Configured holiday"


def test_calendar_features_change_for_season_and_day_type():
    dry_weekday = calendar_feature_vector(datetime(2026, 4, 15, 16))
    wet_weekend = calendar_feature_vector(datetime(2026, 7, 18, 16))

    assert len(dry_weekday) == len(wet_weekend) == 9
    assert dry_weekday != wet_weekend
