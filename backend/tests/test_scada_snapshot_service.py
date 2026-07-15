from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.scada import ScadaGridSnapshot, ScadaImportRun, ScadaRawMeasurement
from app.services.scada_snapshot_service import ScadaSnapshotService


TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")


def _session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, 30, hour, minute, tzinfo=TRINIDAD_TZ)


def _seed_import_run(session_factory) -> int:
    with session_factory() as session:
        import_run = ScadaImportRun(
            source_filename="scada.csv",
            source_path="/tmp/scada.csv",
            source_hash="hash-phase-2",
            row_count=0,
            import_status="IMPORTED",
            summary="test import",
        )
        session.add(import_run)
        session.commit()
        return import_run.id


def _add_measurement(
    session,
    import_run_id: int,
    tag_name: str,
    start_time: datetime,
    avg_value: float,
    quality: str = "Good",
    pen_index: int = 1,
) -> None:
    session.add(
        ScadaRawMeasurement(
            import_run_id=import_run_id,
            pen_index=pen_index,
            tag_name=tag_name,
            start_time=start_time,
            end_time=start_time,
            min_time=start_time,
            min_value=avg_value,
            max_time=start_time,
            max_value=avg_value,
            avg_value=avg_value,
            quality=quality,
            source_filename="scada.csv",
        )
    )


def _seed_complete_hour(session_factory, import_run_id: int, hour: int = 8) -> None:
    # Deliberately add tags out of row order. Snapshot alignment must use timestamps.
    with session_factory() as session:
        _add_measurement(
            session,
            import_run_id,
            "GSYS SYSTEM_AVAIL_TOTAL",
            _dt(hour, 20),
            1190,
            pen_index=4,
        )
        _add_measurement(
            session,
            import_run_id,
            "PTL132 GENERATION TOTALS",
            _dt(hour, 0),
            840,
            pen_index=1,
        )
        _add_measurement(
            session,
            import_run_id,
            "MHO132 AVERAGE AMBIENT TEMPERATURE",
            _dt(hour, 5),
            27.8,
            pen_index=2,
        )
        _add_measurement(
            session,
            import_run_id,
            "GSYS SYSTEM_ONLN_TOTAL",
            _dt(hour, 10),
            940,
            pen_index=5,
        )
        _add_measurement(
            session,
            import_run_id,
            "GSYS SYSTEM_CORRECTED_SPIN_TOTAL",
            _dt(hour, 0),
            148,
            pen_index=3,
        )
        _add_measurement(
            session,
            import_run_id,
            "PTL132 GENERATION TOTALS",
            _dt(hour, 30),
            860,
            pen_index=1,
        )
        session.commit()


def test_build_hourly_snapshot_aligns_by_timestamp_and_calculates_formulas(tmp_path):
    session_factory = _session_factory(tmp_path)
    import_run_id = _seed_import_run(session_factory)
    _seed_complete_hour(session_factory, import_run_id)

    result = ScadaSnapshotService(session_factory=session_factory).build_hourly_snapshots(
        import_run_id=import_run_id
    )

    assert result.snapshots_created == 1
    assert result.source_measurements == 6
    assert result.degraded_snapshots == 0

    with session_factory() as session:
        snapshot = session.scalar(select(ScadaGridSnapshot))

    assert snapshot is not None
    assert snapshot.timestamp == _dt(8).replace(tzinfo=None)
    assert snapshot.available_at == _dt(9).replace(tzinfo=None)
    assert snapshot.current_demand_mw == 850
    assert snapshot.temperature_c == 27.8
    assert snapshot.spinning_reserve_mw == 148
    assert snapshot.available_capacity_mw == 1190
    assert snapshot.online_capacity_mw == 940
    assert snapshot.reserve_margin_mw == 340
    assert snapshot.reserve_margin_percent == 40
    assert snapshot.online_spare_mw == 90
    assert snapshot.quality_status == "GOOD"
    assert snapshot.source == "scada.csv"


def test_build_hourly_snapshots_creates_separate_timestamp_buckets(tmp_path):
    session_factory = _session_factory(tmp_path)
    import_run_id = _seed_import_run(session_factory)
    _seed_complete_hour(session_factory, import_run_id, hour=8)
    _seed_complete_hour(session_factory, import_run_id, hour=9)

    result = ScadaSnapshotService(session_factory=session_factory).build_hourly_snapshots(
        import_run_id=import_run_id
    )

    assert result.snapshots_created == 2
    with session_factory() as session:
        timestamps = session.scalars(
            select(ScadaGridSnapshot.timestamp).order_by(ScadaGridSnapshot.timestamp)
        ).all()
    assert timestamps == [_dt(8).replace(tzinfo=None), _dt(9).replace(tzinfo=None)]


def test_build_hourly_snapshots_replaces_matching_timestamps(tmp_path):
    session_factory = _session_factory(tmp_path)
    import_run_id = _seed_import_run(session_factory)
    _seed_complete_hour(session_factory, import_run_id)
    service = ScadaSnapshotService(session_factory=session_factory)

    first = service.build_hourly_snapshots(import_run_id=import_run_id)
    second = service.build_hourly_snapshots(import_run_id=import_run_id)

    assert first.snapshots_created == 1
    assert second.snapshots_created == 1
    with session_factory() as session:
        assert session.scalar(select(func.count(ScadaGridSnapshot.id))) == 1


def test_missing_required_scada_tag_creates_degraded_snapshot(tmp_path):
    session_factory = _session_factory(tmp_path)
    import_run_id = _seed_import_run(session_factory)
    with session_factory() as session:
        _add_measurement(
            session,
            import_run_id,
            "PTL132 GENERATION TOTALS",
            _dt(8),
            850,
        )
        _add_measurement(
            session,
            import_run_id,
            "GSYS SYSTEM_AVAIL_TOTAL",
            _dt(8),
            1190,
        )
        session.commit()

    result = ScadaSnapshotService(session_factory=session_factory).build_hourly_snapshots(
        import_run_id=import_run_id
    )

    assert result.degraded_snapshots == 1
    with session_factory() as session:
        snapshot = session.scalar(select(ScadaGridSnapshot))

    assert snapshot is not None
    assert snapshot.quality_status == "DEGRADED"
    assert snapshot.current_demand_mw == 850
    assert snapshot.reserve_margin_mw == 340
    assert snapshot.reserve_margin_percent == 40
    assert snapshot.online_spare_mw is None
    assert snapshot.missing_fields == (
        "online_capacity_mw, spinning_reserve_mw, temperature_c"
    )


def test_non_good_quality_creates_degraded_snapshot(tmp_path):
    session_factory = _session_factory(tmp_path)
    import_run_id = _seed_import_run(session_factory)
    _seed_complete_hour(session_factory, import_run_id)
    with session_factory() as session:
        _add_measurement(
            session,
            import_run_id,
            "GSYS SYSTEM_ONLN_TOTAL",
            _dt(8, 45),
            940,
            quality="Inactive",
            pen_index=5,
        )
        session.commit()

    result = ScadaSnapshotService(session_factory=session_factory).build_hourly_snapshots(
        import_run_id=import_run_id
    )

    assert result.degraded_snapshots == 1
    with session_factory() as session:
        snapshot = session.scalar(select(ScadaGridSnapshot))
    assert snapshot is not None
    assert snapshot.quality_status == "DEGRADED"
