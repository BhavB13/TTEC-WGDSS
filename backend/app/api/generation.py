from fastapi import APIRouter

from app.schemas.generation import GridStatusResponse
from app.services.grid_service import GridService

router = APIRouter()

grid_service = GridService()


@router.get(
    "/grid/status",
    response_model=GridStatusResponse,
)
async def get_grid_status() -> GridStatusResponse:

    status = await grid_service.get_grid_status()

    return GridStatusResponse(**status)
