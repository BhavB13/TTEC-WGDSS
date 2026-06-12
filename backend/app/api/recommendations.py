from fastapi import APIRouter

from app.schemas.recommendation import RecommendationResponse
from app.services.recommendation_engine import RecommendationEngine

router = APIRouter()

engine = RecommendationEngine()


@router.get(
    "/recommendations",
    response_model=RecommendationResponse,
)
async def get_recommendation() -> RecommendationResponse:
    """
    Generate a recommendation using mock data.

    This endpoint will later retrieve data from weather
    and grid providers instead of using hardcoded values.
    """

    weather = {
        "temperature_c": 30,
        "humidity_percent": 75,
    }

    forecast = {
        "wind_speed_kph": 25,
    }

    grid_status = {
        "reserve_margin_percent": 15,
    }

    result = engine.evaluate(
        weather=weather,
        forecast=forecast,
        grid_status=grid_status,
    )

    return RecommendationResponse(**result)