from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.demo_replay import DemoObservation, DemoReplayState
from app.schemas.replay import ReplayControlRequest
from app.services.demo_replay_service import DemoReplayService


@pytest.fixture(scope="module")
def replay_service(tmp_path_factory):
    database = tmp_path_factory.mktemp("demo-replay") / "replay.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return DemoReplayService(session_factory=session_factory), session_factory


def test_demo_seed_separates_year_archive_from_june_replay(replay_service):
    service, session_factory = replay_service

    assert service.ensure_seeded() == 8760
    status = service.get_status()

    assert status.dataset_start == datetime(2025, 1, 1)
    assert status.dataset_end == datetime(2025, 12, 31, 23)
    assert status.replay_start == datetime(2025, 6, 1)
    assert status.replay_end == datetime(2025, 6, 30, 23)
    assert status.total_replay_records == 720
    assert status.revealed_records == 1
    with session_factory() as session:
        assert session.scalar(select(func.count(DemoObservation.id))) == 8760


def test_replay_dashboard_exposes_history_forecast_and_no_future_actuals(replay_service):
    service, _ = replay_service
    service.control(ReplayControlRequest(action="reset"))

    context = service.get_dashboard_context()
    assert context is not None
    replay = context["replay"]

    assert replay.summary.historical_months == 11
    assert replay.summary.historical_record_count == 8040
    assert len(replay.operational_history) == 48
    assert len(replay.full_day_load_forecast) == 24
    assert replay.full_day_load_forecast[0].actual_demand_mw is not None
    assert all(
        point.actual_demand_mw is None
        for point in replay.full_day_load_forecast[1:]
    )
    assert len(context["forecast"]) == 24
    assert context["grid"]["source_provider"] == "SimulatedLiveScadaReplay"


def test_replay_control_steps_configures_and_resets_cursor(replay_service):
    service, session_factory = replay_service
    service.control(
        ReplayControlRequest(action="configure", step_minutes=1440, speed_multiplier=86400)
    )
    stepped = service.control(ReplayControlRequest(action="step"))
    assert stepped.cursor_at == datetime(2025, 6, 2)
    assert stepped.revealed_records == 25

    with session_factory() as session:
        state = session.get(DemoReplayState, 1)
        assert state is not None
        state.is_playing = True
        state.last_wallclock_at = (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=2)
        )
        session.commit()

    advanced = service.get_status()
    assert advanced.cursor_at >= datetime(2025, 6, 3)
    reset = service.control(ReplayControlRequest(action="reset"))
    assert reset.cursor_at == datetime(2025, 6, 1)
    assert reset.is_playing is False
