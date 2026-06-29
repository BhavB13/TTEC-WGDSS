from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from app.schemas.storm import StormTrackingResponse
from app.services.storm_tracking_service import StormTrackingService

router = APIRouter()
storm_tracking_service = StormTrackingService()


@router.get(
    "/storm/tracking",
    response_model=StormTrackingResponse,
)
async def get_storm_tracking(
    force_refresh: bool = Query(default=False),
) -> StormTrackingResponse:
    return await asyncio.to_thread(
        storm_tracking_service.get_storm_tracking,
        force_refresh,
    )
