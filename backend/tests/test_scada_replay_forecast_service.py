from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.demand_forecast import ScadaReplayForecastResult
from app.models.scada import ScadaGridSnapshot
from app.services.demand_forecast_model_service import (
    ForecastMetrics,
    HorizonModelResult,
)
from app.services.scada_replay_forecast_service import ScadaReplayForecastService


def test_replay_forecast_refresh_persists_exact_cursor_horizons_and_audit_metadata(
    monkeypatch,
    tmp_path,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'replay-forecast.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    start = datetime(2032, 6, 1)
    with session_factory() as session:
        for hour in range(15 * 24):
            timestamp = start + timedelta(hours=hour)
            session.add(
                ScadaGridSnapshot(
                    timestamp=timestamp,
                    available_at=timestamp + timedelta(hours=1),
                    current_demand_mw=1000 + hour % 24,
                    temperature_c=29,
                    spinning_reserve_mw=120,
                    available_capacity_mw=1450,
                    online_capacity_mw=1320,
                    reserve_margin_mw=450,
                    reserve_margin_percent=45,
                    online_spare_mw=320,
                    quality_status="USABLE_WITH_WARNING",
                    missing_fields="",
                    source="arbitrary-future-export.csv",
                )
            )
        session.commit()

    expected_cursor = datetime(2032, 6, 15, 10)
    captured: dict[str, object] = {}

    class FakeDatasetService:
        def __init__(self, session_factory):
            captured["session_factory"] = session_factory

        def build_evaluation_dataset(self, source_cursor):
            captured["source_cursor"] = source_cursor
            return SimpleNamespace(
                rows=[SimpleNamespace()] * 150,
                inference_rows={1: SimpleNamespace(feature_timestamp=source_cursor),
                                2: SimpleNamespace(feature_timestamp=source_cursor),
                                6: SimpleNamespace(feature_timestamp=source_cursor)},
                source_snapshots=346,
            )

    class FakeModelService:
        def __init__(self, session_factory):
            captured["model_factory"] = session_factory

        def evaluate_rows(self, rows, inference_rows):
            captured["row_count"] = len(rows)
            return [
                _result(expected_cursor, horizon)
                for horizon in (1, 2, 6)
            ]

    monkeypatch.setattr(
        "app.services.scada_replay_forecast_service.ForecastDatasetService",
        FakeDatasetService,
    )
    monkeypatch.setattr(
        "app.services.scada_replay_forecast_service.DemandForecastModelService",
        FakeModelService,
    )
    service = ScadaReplayForecastService(
        session_factory=session_factory,
        clock=lambda: datetime(
            2026,
            7,
            15,
            10,
            42,
            tzinfo=ZoneInfo("America/Port_of_Spain"),
        ),
    )

    refreshed = service.refresh_for_current_clock()

    assert refreshed.source_cursor_at == expected_cursor
    assert refreshed.rows_stored == 3
    assert refreshed.source_snapshots == 346
    assert refreshed.training_rows == 150
    assert captured["source_cursor"] == expected_cursor
    with session_factory() as session:
        rows = list(
            session.scalars(
                select(ScadaReplayForecastResult).order_by(
                    ScadaReplayForecastResult.horizon_hours
                )
            )
        )
    assert [row.horizon_hours for row in rows] == [1, 2, 6]
    assert all(row.feature_timestamp == expected_cursor for row in rows)
    assert all(
        row.forecast_timestamp
        == expected_cursor + timedelta(hours=row.horizon_hours)
        for row in rows
    )
    assert rows[0].baseline_mae == 20
    assert rows[0].feature_profile == "demand_weather_v2_1"
    assert rows[0].candidate_metrics.startswith('{"active"')
    assert [row.horizon_hours for row in service.forecasts_for_source_cursor(expected_cursor)] == [1, 2, 6]
    assert service.forecasts_for_source_cursor(expected_cursor + timedelta(hours=1)) == []


def _result(cursor: datetime, horizon: int) -> HorizonModelResult:
    metrics = ForecastMetrics(mae=10.0, rmse=14.0, mape=1.0, residual_std=12.0)
    return HorizonModelResult(
        horizon_hours=horizon,
        mode="ML_ACTIVE_DEGRADED",
        active_model="HistGradientBoostingRegressor",
        best_baseline="persistence",
        forecast_timestamp=cursor + timedelta(hours=horizon),
        forecast_demand_mw=1100 + horizon,
        forecast_uncertainty_mw=20 + horizon,
        baseline_forecast_mw=1080 + horizon,
        metrics=metrics,
        ml_metrics=metrics,
        ml_beats_baseline=True,
        train_rows=120,
        test_rows=30,
        validation_status="PROTOTYPE",
        training_span_hours=335,
        candidate_metrics={
            "active": {"model": "HistGradientBoostingRegressor", "mae": 10.0},
            "baseline": {"model": "persistence", "mae": 20.0},
        },
    )
