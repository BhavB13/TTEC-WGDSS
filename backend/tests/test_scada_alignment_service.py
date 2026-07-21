from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.scada import ScadaGridSnapshot
from app.services.scada_alignment_service import ScadaAlignmentService
from app.services.scada_replay_validation_service import ScadaReplayValidationService


def _measurement(
    start: datetime,
    end: datetime,
    value: float,
) -> dict[str, object]:
    return {
        "tag_name": "PTL132 GENERATION TOTALS",
        "start_time": start,
        "end_time": end,
        "min_time": start,
        "min_value": value,
        "max_time": end,
        "max_value": value,
        "avg_value": value,
        "quality": "Other",
        "anomaly_flags": "[]",
    }


def _snapshot(hour: int, demand: float) -> ScadaGridSnapshot:
    return ScadaGridSnapshot(
        timestamp=datetime(2026, 6, 20, hour),
        available_at=datetime(2026, 6, 20, 4, 17, 51),
        current_demand_mw=demand,
        quality_status="USABLE_WITH_WARNING",
        missing_fields="temperature_c, spinning_reserve_mw, available_capacity_mw, online_capacity_mw",
        coverage_percent=100,
        source="June Load demand 2026.csv",
    )


def test_june_20_0200_source_reconciliation_flags_shifted_replay_value():
    first = _measurement(
        datetime(2026, 6, 20, 1, 40, 29),
        datetime(2026, 6, 20, 2, 59, 10),
        1028.35,
    )
    second = _measurement(
        datetime(2026, 6, 20, 2, 59, 10),
        datetime(2026, 6, 20, 4, 17, 51),
        1000.70,
    )
    expected_0200 = (1028.35 * 3550 + 1000.70 * 50) / 3600
    snapshots = [
        _snapshot(1, 1028.35),
        _snapshot(2, 745.0),
        _snapshot(3, 1000.70),
        _snapshot(4, 1000.70),
    ]

    report = ScadaAlignmentService().validate(
        [first, first.copy(), second],
        snapshots,
    )

    assert report.selected_method == "interval_overlap_hourly"
    assert report.duplicate_intervals_removed == 1
    assert report.validation_status == "MISMATCH"
    mismatch = next(
        item for item in report.mismatches if item.timestamp == datetime(2026, 6, 20, 2)
    )
    assert mismatch.expected_demand_mw == round(expected_0200, 4)
    assert mismatch.stored_demand_mw == 745.0
    assert mismatch.absolute_difference_mw == round(expected_0200 - 745.0, 4)


def test_june_20_0200_overlap_weighted_value_reconciles_exactly():
    first = _measurement(
        datetime(2026, 6, 20, 1, 40, 29),
        datetime(2026, 6, 20, 2, 59, 10),
        1028.35,
    )
    second = _measurement(
        datetime(2026, 6, 20, 2, 59, 10),
        datetime(2026, 6, 20, 4, 17, 51),
        1000.70,
    )
    expected_0200 = (1028.35 * 3550 + 1000.70 * 50) / 3600

    report = ScadaAlignmentService().validate(
        [first, second],
        [
            _snapshot(1, 1028.35),
            _snapshot(2, expected_0200),
            _snapshot(3, 1000.70),
            _snapshot(4, 1000.70),
        ],
    )

    assert report.validation_status == "VALID_WITH_WARNING"
    assert report.mismatch_count == 0
    assert report.reconciled_hours == 4


def test_risk_readiness_uses_latest_snapshot_available_before_irregular_cursor(
    tmp_path,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'risk-alignment.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        session.add_all(
            [
                ScadaGridSnapshot(
                    timestamp=datetime(2026, 6, 20, 8),
                    available_at=datetime(2026, 6, 20, 8, 20),
                    current_demand_mw=1000,
                    spinning_reserve_mw=200,
                    available_capacity_mw=1500,
                    online_capacity_mw=1300,
                    reserve_margin_mw=500,
                    reserve_margin_percent=50,
                    online_spare_mw=300,
                    quality_status="GOOD",
                    missing_fields="",
                    source="test.csv",
                ),
                ScadaGridSnapshot(
                    timestamp=datetime(2026, 6, 20, 9),
                    available_at=datetime(2026, 6, 20, 10, 51, 16),
                    current_demand_mw=9999,
                    spinning_reserve_mw=0,
                    available_capacity_mw=0,
                    online_capacity_mw=0,
                    reserve_margin_mw=-9999,
                    reserve_margin_percent=-100,
                    online_spare_mw=-9999,
                    quality_status="GOOD",
                    missing_fields="",
                    source="future.csv",
                ),
            ]
        )
        session.commit()
        forecasts = [
            SimpleNamespace(
                horizon_hours=horizon,
                forecast_demand_mw=1050 + horizon,
                forecast_uncertainty_mw=25,
                quality_status="BASELINE_ACTIVE",
            )
            for horizon in range(1, 7)
        ]

        readiness = ScadaReplayValidationService._replay_risk_readiness(
            session,
            datetime(2026, 6, 20, 9),
            forecasts,
        )

    assert readiness.ready is True
    assert readiness.blockers == []
