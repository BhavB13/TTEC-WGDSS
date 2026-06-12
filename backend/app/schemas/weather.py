from pydantic import BaseModel


class CurrentWeatherResponse(BaseModel):
    temperature_c: float
    humidity_percent: float


class ForecastResponse(BaseModel):
    wind_speed_kph: float
    