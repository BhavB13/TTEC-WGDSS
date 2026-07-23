from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.demand_forecast import ForecastTrainingRow
from app.models.scada import ScadaGridSnapshot
from app.services.data_period_policy import DataPeriodPolicy
from app.services.forecast_dataset_service import ForecastDatasetService
from app.services.present_day_service import PresentDayService
from app.main import app


def _session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'period-policy.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _snapshot(timestamp: datetime, demand: float = 1000.0) -> ScadaGridSnapshot:
    return ScadaGridSnapshot(
        timestamp=timestamp,
        available_at=timestamp,
        current_demand_mw=demand,
        temperature_c=28.0,
        spinning_reserve_mw=100.0,
        available_capacity_mw=1300.0,
        online_capacity_mw=1200.0,
        reserve_margin_mw=300.0,
        reserve_margin_percent=30.0,
        online_spare_mw=200.0,
        quality_status="GOOD",
        missing_fields="",
        coverage_percent=100.0,
        source="period-policy-test",
    )


def test_configured_periods_do_not_overlap():
    policy = DataPeriodPolicy.from_settings()
    assert policy.training_start == date(2025, 10, 1)
    assert policy.training_end == date(2026, 5, 31)
    assert policy.simulated_live_start == date(2026, 6, 1)
    assert policy.training_end < policy.simulated_live_start
    assert policy.replay_archive_start == date(2026, 6, 1)
    assert policy.replay_archive_end == date(2026, 6, 30)


def test_training_builder_excludes_june_features_and_targets(tmp_path):
    session_factory = _session_factory(tmp_path)
    start = datetime(2026, 5, 31, 20)
    with session_factory() as session:
        for offset in range(8):
            session.add(_snapshot(start + timedelta(hours=offset), 1000 + offset))
        session.commit()

    ForecastDatasetService(
        session_factory=session_factory,
        enforce_period_policy=True,
    ).build_training_rows(horizons_hours=(1,))

    with session_factory() as session:
        rows = list(session.scalars(select(ForecastTrainingRow)))
    assert rows
    assert all(row.feature_timestamp.month == 5 for row in rows)
    assert all(row.target_timestamp.month == 5 for row in rows)


def test_previous_june_day_is_available_without_changing_training_policy(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        for hour in range(23):
            session.add(_snapshot(datetime(2026, 6, 20, hour)))
        session.commit()
    service = PresentDayService(session_factory=session_factory)

    context = service.context(
        selected_date=date(2026, 6, 20),
        present_at=datetime(2026, 6, 21, 12),
        present_source="test",
    )
    assert context.selected_date == date(2026, 6, 20)
    assert context.active_date == date(2026, 6, 21)
    assert not context.is_active_day
    assert context.record_count == 23
    assert not context.is_complete
    assert context.notice is not None
    assert "incomplete" in context.notice
    assert "23 of 24" in context.notice
    assert context.available_start == date(2026, 6, 20)
    assert context.available_end == date(2026, 6, 20)

    with pytest.raises(HTTPException, match="selected_date must be an available June date"):
        service.context(
            selected_date=date(2026, 5, 31),
            present_at=datetime(2026, 6, 21, 12),
            present_source="test",
        )


def test_active_day_is_cut_off_at_present_time(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        for hour in range(24):
            session.add(_snapshot(datetime(2026, 6, 21, hour)))
        session.commit()

    context = PresentDayService(session_factory=session_factory).context(
        selected_date=None,
        present_at=datetime(2026, 6, 21, 8, 30),
        present_source="June replay",
    )

    assert context.is_active_day
    assert context.selected_date == date(2026, 6, 21)
    assert context.record_count == 9
    assert context.series[-1].timestamp == datetime(2026, 6, 21, 8)
    assert context.value_classification == "SIMULATED_LIVE"


def test_dashboard_openapi_exposes_only_selected_day_navigation():
    operation = app.openapi()["paths"]["/api/v1/dashboard/snapshot"]["get"]
    parameters = {item["name"] for item in operation["parameters"]}

    assert "selected_date" in parameters
    assert "mode" not in parameters
    assert "start_date" not in parameters
    assert "end_date" not in parameters
    assert "granularity" not in parameters
