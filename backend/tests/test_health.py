from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.api import health
from app.services.provider_health import record_provider_failure, record_provider_success


class _HealthySession:
    def __enter__(self):
        self._count = 0
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement):
        return None

    def scalar(self, statement):
        self._count += 1
        return 3 if self._count == 1 else 120


class _BrokenSession:
    def __enter__(self):
        raise SQLAlchemyError("database unavailable")

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_health_endpoint_reports_database_weather_and_calibration(monkeypatch):
    record_provider_success("weather_primary", "Open-Meteo")
    record_provider_success("weather_consensus", "MET Norway")
    record_provider_failure("weather_fallback", "WeatherAPI", RuntimeError("down"))
    monkeypatch.setattr(health, "SessionLocal", lambda: _HealthySession())

    response = await health.health_check()

    assert response.status == "healthy"
    assert response.database.status == "healthy"
    assert response.weather_primary.status == "operational"
    assert response.weather_consensus.status == "operational"
    assert response.weather_consensus_secondary.status in {"configured", "operational"}
    assert response.weather_fallback.status == "degraded"
    assert response.open_meteo_usage.status in {"healthy", "limit_reached"}
    assert "permitted requests used" in response.open_meteo_usage.detail
    assert response.weatherapi_usage.status in {"disabled", "healthy", "limit_reached"}
    assert response.api_cost_mode.status == "zero_cost"
    assert response.calibration.status == "healthy"
    assert "scenario rows" in response.calibration.detail
    assert response.timestamp.tzinfo is not None


@pytest.mark.asyncio
async def test_health_endpoint_marks_database_unhealthy_when_connection_fails(monkeypatch):
    monkeypatch.setattr(health, "SessionLocal", lambda: _BrokenSession())

    response = await health.health_check()

    assert response.status == "degraded"
    assert response.database.status == "unhealthy"
    assert response.calibration.status == "unknown"
    assert response.calibration.detail.startswith("Calibration status unavailable")
