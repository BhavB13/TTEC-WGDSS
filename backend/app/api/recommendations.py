from fastapi import APIRouter, Query

from app.core.config import settings
from app.schemas.recommendation import RecommendationResponse
from app.services.dashboard_service import DashboardService

router = APIRouter()

dashboard_service = DashboardService()


@router.get(
    "/recommendations",
    response_model=RecommendationResponse,
)
async def get_recommendation(
    latitude: float = Query(default=settings.DEFAULT_LATITUDE),
    longitude: float = Query(default=settings.DEFAULT_LONGITUDE),
) -> RecommendationResponse:
    """
    Generate a recommendation using provider and service layers.
    """

    snapshot = await dashboard_service.get_snapshot(
        latitude=latitude,
        longitude=longitude,
    )
    return snapshot.recommendation
