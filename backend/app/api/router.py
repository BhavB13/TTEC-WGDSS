from fastapi import APIRouter

from app.api.capacity_plan import router as capacity_plan_router
from app.api.dashboard import router as dashboard_router
from app.api.generation import router as generation_router
from app.api.health import router as health_router
from app.api.live_scada_experiment import router as live_scada_experiment_router
from app.api.recommendations import router as recommendations_router
from app.api.replay import router as replay_router
from app.api.storm import router as storm_router
from app.api.weather import router as weather_router

api_router = APIRouter()

api_router.include_router(
    capacity_plan_router,
    tags=["capacity-plan"],
)

api_router.include_router(
    live_scada_experiment_router,
    tags=["live-scada-experiment"],
)

api_router.include_router(
    health_router,
    tags=["health"],
)

api_router.include_router(
    recommendations_router,
    tags=["recommendations"],
)

api_router.include_router(
    dashboard_router,
    tags=["dashboard"],
)

api_router.include_router(
    weather_router,
    tags=["weather"],
)

api_router.include_router(
    generation_router,
    tags=["grid"],
)

api_router.include_router(
    storm_router,
    tags=["storm"],
)

api_router.include_router(
    replay_router,
    tags=["replay"],
)
