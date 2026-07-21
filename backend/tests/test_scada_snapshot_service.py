from __future__ import annotations

from datetime import datetime, timedelta
import json
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
    end_time: datetime | None = None,
) -> None:
    interval_end = end_time or start_time + timedelta(hours=1)
    session.add(
        ScadaRawMeasurement(
            import_run_id=import_run_id,
            pen_index=pen_index,
            tag_name=tag_name,
            start_time=start_time,
            end_time=interval_end,
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
            _dt(hour),
            1190,
            pen_index=4,
            end_time=_dt(hour) + timedelta(hours=1),
        )
        _add_measurement(
            session,
            import_run_id,
            "PTL132 GENERATION TOTALS",
            _dt(hour, 0),
            840,
            pen_index=1,
            end_time=_dt(hour, 30),
        )
        _add_measurement(
            session,
            import_run_id,
            "MHO132 AVERAGE AMBIENT TEMPERATURE",
            _dt(hour),
            27.8,
            pen_index=2,
            end_time=_dt(hour) + timedelta(hours=1),
        )
        _add_measurement(
            session,
            import_run_id,
            "GSYS SYSTEM_ONLN_TOTAL",
            _dt(hour),
            940,
            pen_index=5,
            end_time=_dt(hour) + timedelta(hours=1),
        )
        _add_measurement(
            session,
            import_run_id,
            "GSYS SYSTEM_CORRECTED_SPIN_TOTAL",
            _dt(hour, 0),
            148,
            pen_index=3,
            end_time=_dt(hour) + timedelta(hours=1),
        )
        _add_measurement(
            session,
            import_run_id,
            "PTL132 GENERATION TOTALS",
            _dt(hour, 30),
            860,
            pen_index=1,
            end_time=_dt(hour) + timedelta(hours=1),
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
            end_time=_dt(9),
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


def test_interval_overlap_resampling_weights_irregular_exports_by_timestamp(tmp_path):
    session_factory = _session_factory(tmp_path)
    import_run_id = _seed_import_run(session_factory)
    with session_factory() as session:
        _add_measurement(
            session,
            import_run_id,
            "PTL132 GENERATION TOTALS",
            _dt(8, 30),
            800,
            end_time=_dt(9, 30),
        )
        _add_measurement(
            session,
            import_run_id,
            "PTL132 GENERATION TOTALS",
            _dt(9, 30),
            1000,
            end_time=_dt(10, 30),
            pen_index=2,
        )
        for pen_index, (tag, value) in enumerate(
            (
                ("MHO132 AVERAGE AMBIENT TEMPERATURE", 30),
                ("GSYS SYSTEM_CORRECTED_SPIN_TOTAL", 120),
                ("GSYS SYSTEM_AVAIL_TOTAL", 1500),
                ("GSYS SYSTEM_ONLN_TOTAL", 1250),
            ),
            start=3,
        ):
            _add_measurement(
                session,
                import_run_id,
                tag,
                _dt(9),
                value,
                end_time=_dt(9) + timedelta(hours=1),
                pen_index=pen_index,
            )
        session.commit()

    ScadaSnapshotService(session_factory=session_factory).build_hourly_snapshots(
        import_run_id=import_run_id
    )

    with session_factory() as session:
        snapshot = session.scalar(
            select(ScadaGridSnapshot).where(
                ScadaGridSnapshot.timestamp == _dt(9).replace(tzinfo=None)
            )
        )
    assert snapshot is not None
    assert snapshot.current_demand_mw == 900
    assert snapshot.quality_status == "GOOD"
    assert snapshot.coverage_percent == 100
    assert snapshot.resampling_method == "interval_overlap_hourly"
    assert snapshot.available_at == _dt(10, 30).replace(tzinfo=None)
    provenance = json.loads(snapshot.field_provenance)
    assert provenance["current_demand_mw"]["coverage_percent"] == 100
    assert len(provenance["current_demand_mw"]["source_intervals"]) == 2


def test_june_20_0200_irregular_demand_interval_is_overlap_weighted(tmp_path):
    session_factory = _session_factory(tmp_path)
    import_run_id = _seed_import_run(session_factory)
    hour = datetime(2026, 6, 20, 2, tzinfo=TRINIDAD_TZ)
    with session_factory() as session:
        _add_measurement(
            session,
            import_run_id,
            "PTL132 GENERATION TOTALS",
            datetime(2026, 6, 20, 1, 40, 29, tzinfo=TRINIDAD_TZ),
            1028.35,
            quality="Other",
            end_time=datetime(2026, 6, 20, 2, 59, 10, tzinfo=TRINIDAD_TZ),
        )
        _add_measurement(
            session,
            import_run_id,
            "PTL132 GENERATION TOTALS",
            datetime(2026, 6, 20, 2, 59, 10, tzinfo=TRINIDAD_TZ),
            1000.70,
            quality="Other",
            pen_index=2,
            end_time=datetime(2026, 6, 20, 4, 17, 51, tzinfo=TRINIDAD_TZ),
        )
        for pen_index, (tag, value) in enumerate(
            (
                ("MHO132 AVERAGE AMBIENT TEMPERATURE", 27.0),
                ("GSYS SYSTEM_CORRECTED_SPIN_TOTAL", 120.0),
                ("GSYS SYSTEM_AVAIL_TOTAL", 1500.0),
            ),
            start=3,
        ):
            _add_measurement(
                session,
                import_run_id,
                tag,
                hour,
                value,
                pen_index=pen_index,
                end_time=hour + timedelta(hours=1),
            )
        _add_measurement(
            session,
            import_run_id,
            "GSYS SYSTEM_ONLN_TOTAL",
            datetime(2026, 6, 20, 0, 59, tzinfo=TRINIDAD_TZ),
            1124.1,
            pen_index=6,
            end_time=datetime(2026, 6, 20, 2, 2, tzinfo=TRINIDAD_TZ),
        )
        _add_measurement(
            session,
            import_run_id,
            "GSYS SYSTEM_ONLN_TOTAL",
            datetime(2026, 6, 20, 2, 2, tzinfo=TRINIDAD_TZ),
            1106.0,
            pen_index=7,
            end_time=datetime(2026, 6, 20, 3, 5, tzinfo=TRINIDAD_TZ),
        )
        session.commit()

    ScadaSnapshotService(session_factory=session_factory).build_hourly_snapshots(
        import_run_id=import_run_id
    )

    with session_factory() as session:
        snapshot = session.scalar(
            select(ScadaGridSnapshot).where(
                ScadaGridSnapshot.timestamp == hour.replace(tzinfo=None)
            )
        )
    assert snapshot is not None
    assert snapshot.current_demand_mw == 1027.966
    assert snapshot.online_capacity_mw == 1106.6033
    assert snapshot.timestamp == datetime(2026, 6, 20, 2)
    assert snapshot.available_at == datetime(2026, 6, 20, 4, 17, 51)


def test_other_quality_is_preserved_as_conditionally_usable_not_good(tmp_path):
    session_factory = _session_factory(tmp_path)
    import_run_id = _seed_import_run(session_factory)
    values = (
        ("PTL132 GENERATION TOTALS", 900),
        ("MHO132 AVERAGE AMBIENT TEMPERATURE", 30),
        ("GSYS SYSTEM_CORRECTED_SPIN_TOTAL", 100),
        ("GSYS SYSTEM_AVAIL_TOTAL", 1450),
        ("GSYS SYSTEM_ONLN_TOTAL", 1250),
    )
    with session_factory() as session:
        for pen_index, (tag, value) in enumerate(values, start=1):
            _add_measurement(
                session,
                import_run_id,
                tag,
                _dt(9),
                value,
                quality="Other",
                pen_index=pen_index,
            )
        session.commit()

    result = ScadaSnapshotService(
        session_factory=session_factory
    ).build_hourly_snapshots(import_run_id=import_run_id)

    assert result.degraded_snapshots == 0
    assert result.conditional_snapshots == 1
    with session_factory() as session:
        snapshot = session.scalar(select(ScadaGridSnapshot))
    assert snapshot is not None
    assert snapshot.quality_status == "USABLE_WITH_WARNING"
    assert "Conditionally accepted 'Other' quality" in snapshot.quality_notes


def test_invalid_zero_duration_interval_is_flagged_and_not_used_as_point(tmp_path):
    session_factory = _session_factory(tmp_path)
    import_run_id = _seed_import_run(session_factory)
    with session_factory() as session:
        _add_measurement(
            session,
            import_run_id,
            "PTL132 GENERATION TOTALS",
            _dt(8),
            850,
            end_time=_dt(8),
        )
        session.commit()

    ScadaSnapshotService(session_factory=session_factory).build_hourly_snapshots(
        import_run_id=import_run_id
    )

    with session_factory() as session:
        snapshot = session.scalar(select(ScadaGridSnapshot))
    assert snapshot is not None
    assert snapshot.current_demand_mw is None
    assert snapshot.quality_status == "DEGRADED"
    assert "non_positive_interval" in json.loads(snapshot.anomaly_flags)


def test_soft_capacity_invariant_is_reported_without_repair(tmp_path):
    session_factory = _session_factory(tmp_path)
    import_run_id = _seed_import_run(session_factory)
    values = (
        ("PTL132 GENERATION TOTALS", 1000),
        ("MHO132 AVERAGE AMBIENT TEMPERATURE", 30),
        ("GSYS SYSTEM_CORRECTED_SPIN_TOTAL", 80),
        ("GSYS SYSTEM_AVAIL_TOTAL", 900),
        ("GSYS SYSTEM_ONLN_TOTAL", 950),
    )
    with session_factory() as session:
        for pen_index, (tag, value) in enumerate(values, start=1):
            _add_measurement(session, import_run_id, tag, _dt(8), value, pen_index=pen_index)
        session.commit()

    ScadaSnapshotService(session_factory=session_factory).build_hourly_snapshots(
        import_run_id=import_run_id
    )

    with session_factory() as session:
        snapshot = session.scalar(select(ScadaGridSnapshot))
    assert snapshot is not None
    assert snapshot.current_demand_mw == 1000
    assert snapshot.online_capacity_mw == 950
    assert snapshot.available_capacity_mw == 900
    assert snapshot.quality_status == "DEGRADED"
    assert set(json.loads(snapshot.anomaly_flags)) >= {
        "generation_proxy_exceeds_tra",
        "tra_exceeds_ta",
    }
