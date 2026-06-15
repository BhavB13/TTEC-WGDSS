from fastapi import APIRouter

from app.providers.open_meteo_provider import OpenMeteoProvider
from app.schemas.forecast import ForecastResponse
from app.schemas.weather import CurrentWeatherResponse
from app.services.weather_service import WeatherService

router = APIRouter()

weather_service = WeatherService(OpenMeteoProvider())


@router.get(
    "/weather/current",
    response_model=CurrentWeatherResponse,
)
async def get_current_weather() -> CurrentWeatherResponse:

    weather = await weather_service.get_current_weather(
        latitude=10.6918,
        longitude=-61.2225,
    )

    return CurrentWeatherResponse(**weather)


@router.get(
    "/weather/forecast",
    response_model=list[ForecastResponse],
)
async def get_forecast() -> list[ForecastResponse]:

    forecast = await weather_service.get_forecast(
        latitude=10.6918,
        longitude=-61.2225,
    )

    return [ForecastResponse(**item) for item in forecast]