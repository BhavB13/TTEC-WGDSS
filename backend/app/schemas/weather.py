from pydantic import BaseModel


class CurrentWeatherResponse(BaseModel):
    temperature_c: float
    humidity_percent: float
    wind_speed_kph: float
    wind_direction_deg: float
    pressure_hpa: float
    precipitation_mm: float
    provider_name: str