from datetime import datetime
from types import SimpleNamespace

from app.services.operational_forecast_orchestrator import _risk_horizon


def test_generation_need_rises_when_current_tra_falls():
    forecast = SimpleNamespace(
        horizon_hours=1,
        forecast_timestamp=datetime(2026, 6, 20, 3),
        forecast_demand_mw=1100.0,
        forecast_uncertainty_mw=25.0,
    )

    high_tra = _risk_horizon(forecast, 1250.0)
    low_tra = _risk_horizon(forecast, 1120.0)

    assert high_tra.generation_need_probability < low_tra.generation_need_probability
    assert high_tra.current_tra_held_mw == 1250.0
    assert low_tra.current_tra_held_mw == 1120.0
