from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.database.session import SessionLocal
from app.models.calibration import CalibrationScenarioProfile, ScadaTemperatureSample
from app.providers.open_meteo_provider import OpenMeteoProvider
from app.providers.weatherapi_provider import WeatherAPIProvider
from app.services.provider_health import get_provider_state


class ComponentHealth(BaseModel):
    status: str
    detail: str


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    database: ComponentHealth
    weather_primary: ComponentHealth
    weather_consensus: ComponentHealth
    weather_consensus_secondary: ComponentHealth
    weather_fallback: ComponentHealth
    open_meteo_usage: ComponentHealth
    weatherapi_usage: ComponentHealth
    api_cost_mode: ComponentHealth
    calibration: ComponentHealth
    grid_provider: ComponentHealth


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    database = ComponentHealth(status="healthy", detail="Database connection available")
    calibration = ComponentHealth(status="not_loaded", detail="No calibration profiles loaded")

    try:
        with SessionLocal() as session:
            session.execute(select(1))
            profile_count = session.scalar(select(func.count(CalibrationScenarioProfile.id))) or 0
            sample_count = session.scalar(select(func.count(ScadaTemperatureSample.id))) or 0
            if profile_count and sample_count:
                calibration = ComponentHealth(
                    status="healthy",
                    detail=f"{profile_count} scenario rows and {sample_count} SCADA samples loaded",
                )
    except SQLAlchemyError as exc:
        database = ComponentHealth(status="unhealthy", detail=type(exc).__name__)
        calibration = ComponentHealth(
            status="unknown",
            detail="Calibration status unavailable while database is offline",
        )

    fallback_detail = (
        "WeatherAPI configured"
        if settings.ENABLE_WEATHERAPI_FALLBACK and settings.WEATHER_API_KEY
        else "Open-Meteo GFS fallback configured"
    )
    overall = "healthy" if database.status == "healthy" else "degraded"
    primary_state = get_provider_state("weather_primary")
    fallback_state = get_provider_state("weather_fallback")
    consensus_state = get_provider_state("weather_consensus")
    secondary_consensus_state = get_provider_state("weather_consensus_2")
    grid_provider_state = get_provider_state("grid_provider")
    primary_health = ComponentHealth(
        status=primary_state["status"] if primary_state else "configured",
        detail=(
            f"{primary_state['provider']} last succeeded at {primary_state['last_success']}"
            if primary_state and primary_state["status"] == "operational"
            else f"Open-Meteo model endpoint: {settings.OPEN_METEO_BASE_URL}"
        ),
    )
    fallback_health = ComponentHealth(
        status=fallback_state["status"] if fallback_state else "configured",
        detail=(
            f"{fallback_state['provider']} last succeeded at {fallback_state['last_success']}"
            if fallback_state and fallback_state["status"] == "operational"
            else fallback_detail
        ),
    )
    consensus_health = ComponentHealth(
        status=consensus_state["status"] if consensus_state else "configured",
        detail=(
            f"{consensus_state['provider']} last succeeded at "
            f"{consensus_state['last_success']}"
            if consensus_state and consensus_state["status"] == "operational"
            else f"MET Norway endpoint: {settings.MET_NORWAY_BASE_URL}"
        ),
    )
    secondary_consensus_health = ComponentHealth(
        status=(
            secondary_consensus_state["status"]
            if secondary_consensus_state
            else "configured"
        ),
        detail=(
            f"{secondary_consensus_state['provider']} last succeeded at "
            f"{secondary_consensus_state['last_success']}"
            if secondary_consensus_state
            and secondary_consensus_state["status"] == "operational"
            else "NOAA GFS cross-check through the Open-Meteo model endpoint"
        ),
    )
    usage = OpenMeteoProvider.usage_state()
    usage_health = ComponentHealth(
        status=(
            "healthy"
            if int(usage["count"]) < int(usage["limit"])
            else "limit_reached"
        ),
        detail=(
            f"{usage['count']} of {usage['limit']} permitted requests used "
            f"on {usage['date']} UTC"
        ),
    )
    if usage_health.status != "healthy":
        overall = "degraded"
    weatherapi_usage = WeatherAPIProvider.usage_state()
    weatherapi_usage_health = ComponentHealth(
        status=(
            "disabled"
            if not settings.ENABLE_WEATHERAPI_FALLBACK
            else (
                "healthy"
                if int(weatherapi_usage["count"]) < int(weatherapi_usage["limit"])
                else "limit_reached"
            )
        ),
        detail=(
            "Optional WeatherAPI fallback is disabled"
            if not settings.ENABLE_WEATHERAPI_FALLBACK
            else (
                f"{weatherapi_usage['count']} of {weatherapi_usage['limit']} "
                f"permitted requests used in {weatherapi_usage['month']}"
            )
        ),
    )
    if weatherapi_usage_health.status == "limit_reached":
        overall = "degraded"
    paid_endpoint_configured = "customer-api.open-meteo.com" in settings.OPEN_METEO_BASE_URL
    external_account_enabled = settings.ENABLE_WEATHERAPI_FALLBACK
    cost_health = ComponentHealth(
        status=(
            "review_required"
            if paid_endpoint_configured or external_account_enabled
            else "zero_cost"
        ),
        detail=(
            "Review configured provider account and billing plan"
            if paid_endpoint_configured or external_account_enabled
            else "No metered API credential or paid endpoint is enabled"
        ),
    )
    if cost_health.status != "zero_cost":
        overall = "degraded"
    grid_provider_health = ComponentHealth(
        status=(
            grid_provider_state["status"]
            if grid_provider_state
            else "configured"
        ),
        detail=(
            f"{grid_provider_state['provider']} last succeeded at "
            f"{grid_provider_state['last_success']}"
            if grid_provider_state
            and grid_provider_state["status"] == "operational"
            else (
                f"Configured grid provider: {settings.GRID_PROVIDER}"
                if not grid_provider_state
                else (
                    f"{grid_provider_state['provider']} failure: "
                    f"{grid_provider_state['last_error']}"
                )
            )
        ),
    )
    if grid_provider_health.status == "degraded":
        overall = "degraded"

    return HealthResponse(
        status=overall,
        timestamp=datetime.now(timezone.utc),
        database=database,
        weather_primary=primary_health,
        weather_consensus=consensus_health,
        weather_consensus_secondary=secondary_consensus_health,
        weather_fallback=fallback_health,
        open_meteo_usage=usage_health,
        weatherapi_usage=weatherapi_usage_health,
        api_cost_mode=cost_health,
        calibration=calibration,
        grid_provider=grid_provider_health,
    )
