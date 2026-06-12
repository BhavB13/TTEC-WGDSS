API Contract
Health Endpoints
GET /health
Response:
{
  "status": "healthy"
}


Recommendation Endpoints
GET /recommendations
Response:
{
  "probability_score": 0.90,
  "recommendation": "START",
  "reason": "Reserve margin below operating threshold."
}


Future Weather Endpoints
GET /weather/current
Response:
{
  "temperature_c": 30.5,
  "humidity_percent": 75,
  "wind_speed_kph": 22,
  "wind_direction_deg": 120,
  "pressure_hpa": 1012,
  "precipitation_mm": 0,
  "provider_name": "Open-Meteo"
}

GET /weather/forecast
Response:
{
  "forecast_timestamp": "2026-06-13T12:00:00Z",
  "temperature_c": 31,
  "wind_speed_kph": 25,
  "precipitation_probability_percent": 45,
  "confidence_score": 0.88
}


Future Grid Endpoints
GET /grid/status
Response:
{
  "total_available_capacity_mw": 1200,
  "total_generation_mw": 950,
  "reserve_margin_percent": 26.3,
  "grid_status": "NORMAL"
}

