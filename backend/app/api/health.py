# app/api/health.py

from fastapi import APIRouter
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
)
async def health_check():
    return HealthResponse(status="healthy")