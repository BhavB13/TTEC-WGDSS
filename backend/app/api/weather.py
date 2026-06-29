from fastapi import APIRouter, Query

from app.core.config import settings
from app.schemas.forecast import ForecastResponse
from app.schemas.weather import CurrentWeatherResponse
from app.services.weather_service import WeatherService

router = APIRouter()

weather_service = WeatherService()


@router.get(
    "/weather/current",
    response_model=CurrentWeatherResponse,
)
async def get_current_weather(
    latitude: float = Query(default=settings.DEFAULT_LATITUDE, ge=-90, le=90),
    longitude: float = Query(default=settings.DEFAULT_LONGITUDE, ge=-180, le=180),
) -> CurrentWeatherResponse:

    weather = await weather_service.get_current_weather(
        latitude=latitude,
        longitude=longitude,
    )

    return CurrentWeatherResponse(**weather)


@router.get(
    "/weather/forecast",
    response_model=list[ForecastResponse],
)
async def get_forecast(
    latitude: float = Query(default=settings.DEFAULT_LATITUDE, ge=-90, le=90),
    longitude: float = Query(default=settings.DEFAULT_LONGITUDE, ge=-180, le=180),
    days: int = Query(default=7, ge=1, le=14),
) -> list[ForecastResponse]:

    forecast = await weather_service.get_forecast(
        latitude=latitude,
        longitude=longitude,
        days=days,
    )

    return [ForecastResponse(**item) for item in forecast]
