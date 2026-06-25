from fastapi import APIRouter

from app.api.dashboard import router as dashboard_router
from app.api.generation import router as generation_router
from app.api.health import router as health_router
from app.api.recommendations import router as recommendations_router
from app.api.weather import router as weather_router

api_router = APIRouter()

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
