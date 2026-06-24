from fastapi import APIRouter, Query

from app.core.config import settings
from app.schemas.dashboard import DashboardSnapshotResponse
from app.services.dashboard_service import DashboardService

router = APIRouter()
dashboard_service = DashboardService()


@router.get(
    "/dashboard/snapshot",
    response_model=DashboardSnapshotResponse,
)
async def get_dashboard_snapshot(
    latitude: float = Query(default=settings.DEFAULT_LATITUDE),
    longitude: float = Query(default=settings.DEFAULT_LONGITUDE),
    days: int = Query(default=7, ge=1, le=14),
    force_refresh: bool = Query(default=False),
) -> DashboardSnapshotResponse:
    return await dashboard_service.get_snapshot(
        latitude=latitude,
        longitude=longitude,
        days=days,
        force_refresh=force_refresh,
    )
