from datetime import datetime, timezone

import pytest

from app.providers.grid_provider_factory import create_grid_provider
from app.schemas.grid import GridStatusResponse
from app.services.grid_service import GridDataValidationError, GridService


def test_reserve_margin_uses_available_capacity_and_demand():
    assert GridService._calculate_reserve_margin(1200, 800) == 50.0


def test_grid_normalization_rejects_missing_and_negative_critical_values():
    service = GridService(provider=create_grid_provider("mock"))

    with pytest.raises(GridDataValidationError, match="omitted critical telemetry"):
        service._normalize_grid_status(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "current_demand_mw": 800,
                "current_generation_mw": 900,
            }
        )

    with pytest.raises(GridDataValidationError, match="cannot be negative"):
        service._normalize_grid_status(
            {
                "current_demand_mw": -1,
                "current_generation_mw": 900,
                "total_available_capacity_mw": 1200,
            }
        )


def test_grid_normalization_keeps_provider_quality_metadata():
    service = GridService(provider=create_grid_provider("mock"))
    timestamp = datetime.now(timezone.utc)
    normalized = service._normalize_grid_status(
        GridStatusResponse(
            timestamp=timestamp,
            current_demand_mw=800,
            current_generation_mw=900,
            total_available_capacity_mw=1200,
            reserve_margin_percent=50,
            spinning_reserve_mw=75,
            spinning_reserve_source="SCADA_CORRECTED_SPIN",
            grid_status="NORMAL",
            demand_period="MORNING",
            source_provider="TestScadaProvider",
            quality_status="UNCERTAIN",
            missing_fields=[],
        )
    )

    assert normalized["quality_status"] == "UNCERTAIN"
    assert normalized["spinning_reserve_mw"] == 75
    assert normalized["spinning_reserve_source"] == "SCADA_CORRECTED_SPIN"
    normalized_timestamp = datetime.fromisoformat(
        normalized["timestamp"].replace("Z", "+00:00")
    )
    assert normalized_timestamp == timestamp


def test_grid_normalization_recalculates_inconsistent_derived_reserve_margin():
    service = GridService(provider=create_grid_provider("mock"))

    normalized = service._normalize_grid_status(
        {
            "current_demand_mw": 800,
            "current_generation_mw": 900,
            "total_available_capacity_mw": 1200,
            "reserve_margin_percent": 1,
        }
    )

    assert normalized["reserve_margin_percent"] == 50
    assert normalized["spinning_reserve_mw"] is None
    assert (
        normalized["spinning_reserve_source"]
        == "UNAVAILABLE_NOT_DERIVED"
    )
    assert "spinning_reserve_mw" in normalized["missing_fields"]


def test_unconfigured_live_provider_fails_closed():
    with pytest.raises(RuntimeError, match="no live connector is configured"):
        create_grid_provider("scada")
