from fastapi import APIRouter

from app.providers.mock_grid_provider import MockGridProvider
from app.providers.open_meteo_provider import OpenMeteoProvider
from app.schemas.recommendation import RecommendationResponse
from app.services.grid_service import GridService
from app.services.recommendation_engine import RecommendationEngine
from app.services.weather_service import WeatherService

router = APIRouter()

weather_service = WeatherService(OpenMeteoProvider())
grid_service = GridService(MockGridProvider())
recommendation_engine = RecommendationEngine()


@router.get(
    "/recommendations",
    response_model=RecommendationResponse,
)
async def get_recommendation() -> RecommendationResponse:
    """
    Generate a recommendation using provider and service layers.
    """

    weather = await weather_service.get_current_weather(
        latitude=10.6918,
        longitude=-61.2225,
    )

    forecast_data = await weather_service.get_forecast(
        latitude=10.6918,
        longitude=-61.2225,
    )

    forecast = forecast_data[0]

    grid_status = await grid_service.get_grid_status()

    result = recommendation_engine.evaluate(
        weather=weather,
        forecast=forecast,
        grid_status=grid_status,
    )

    return RecommendationResponse(**result) 