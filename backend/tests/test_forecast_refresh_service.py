from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.scada import ScadaGridSnapshot
from app.services.forecast_refresh_service import ForecastRefreshService


def _session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'forecast_refresh.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_refresh_skips_without_good_scada_snapshots(tmp_path):
    result = ForecastRefreshService(session_factory=_session_factory(tmp_path)).refresh()

    assert result.refreshed is False
    assert result.good_snapshot_count == 0
    assert result.reason == "No Good-quality SCADA snapshots are available"


def test_refresh_skips_when_history_is_below_supervised_threshold(tmp_path):
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        now = datetime.now(timezone.utc)
        for hour in range(4):
            session.add(
                ScadaGridSnapshot(
                    timestamp=now + timedelta(hours=hour),
                    current_demand_mw=900,
                    temperature_c=28,
                    spinning_reserve_mw=100,
                    available_capacity_mw=1200,
                    online_capacity_mw=1100,
                    reserve_margin_mw=300,
                    reserve_margin_percent=33.3,
                    online_spare_mw=200,
                    quality_status="GOOD",
                    missing_fields="",
                    source="test.csv",
                )
            )
        session.commit()

    result = ForecastRefreshService(session_factory=session_factory).refresh(
        minimum_good_snapshots=8
    )

    assert result.refreshed is False
    assert result.good_snapshot_count == 4
    assert "Insufficient Good-quality SCADA history" in result.reason


def test_refresh_rejects_invalid_minimum_snapshot_threshold(tmp_path):
    service = ForecastRefreshService(session_factory=_session_factory(tmp_path))

    with pytest.raises(ValueError, match="at least 3"):
        service.refresh(minimum_good_snapshots=2)
