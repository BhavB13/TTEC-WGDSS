from datetime import datetime

from pydantic import BaseModel


class CurrentWeatherResponse(BaseModel):
    timestamp: datetime | None = None
    temperature_c: float
    humidity_percent: float
    rainfall_mm_hr: float
    cloud_cover_percent: float
    wind_speed_kmh: float
    weather_condition: str
    heat_index_c: float
    rain_severity: str
    wind_direction_deg: float | None = None
    pressure_hpa: float | None = None
    provider_name: str
