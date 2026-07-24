from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.demand_forecast import ForecastTrainingRow
from app.services.as_of_forecast_feature_service import AsOfForecastFeatureService


def _row(issue: datetime, horizon: int = 1) -> ForecastTrainingRow:
    return ForecastTrainingRow(
        feature_timestamp=issue,
        feature_available_at=issue,
        horizon_hours=horizon,
        target_timestamp=issue + timedelta(hours=horizon),
        target_demand_mw=1010.0,
        current_demand_mw=1000.0,
        hour_of_day=issue.hour,
        day_of_week=issue.weekday(),
        forecast_weather_issued_at=issue,
        source_quality_status="GOOD",
    )


def test_as_of_features_are_deterministic_and_provenanced():
    issue = datetime(2026, 6, 20, 2)
    row = _row(issue)
    service = AsOfForecastFeatureService()
    service.dataset_service = SimpleNamespace(
        build_evaluation_dataset=lambda _issue: SimpleNamespace(
            rows=[row],
            inference_rows={1: row},
            source_snapshots=42,
        )
    )

    first = service.build(
        issue,
        source_provider="SCADA_ARCHIVE",
        data_mode="HISTORICAL_REPLAY",
    )
    second = service.build(
        issue,
        source_provider="SCADA_ARCHIVE",
        data_mode="HISTORICAL_REPLAY",
    )

    assert first.diagnostics.status == "READY"
    assert first.diagnostics.feature_fingerprint == second.diagnostics.feature_fingerprint
    assert first.diagnostics.inference_horizons == (1,)
    assert first.diagnostics.source_provider == "SCADA_ARCHIVE"


def test_as_of_features_reject_future_available_data():
    issue = datetime(2026, 6, 20, 2)
    row = _row(issue)
    row.feature_available_at = issue + timedelta(minutes=1)
    service = AsOfForecastFeatureService()
    service.dataset_service = SimpleNamespace(
        build_evaluation_dataset=lambda _issue: SimpleNamespace(
            rows=[],
            inference_rows={1: row},
            source_snapshots=1,
        )
    )

    with pytest.raises(ValueError, match="not available"):
        service.build(
            issue,
            source_provider="SCADA_ARCHIVE",
            data_mode="HISTORICAL_REPLAY",
        )
