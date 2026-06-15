from datetime import datetime
from pydantic import BaseModel


class ForecastResponse(BaseModel):
    forecast_timestamp: datetime
    temperature_c: float
    wind_speed_kph: float
    precipitation_probability_percent: float
    confidence_score: float