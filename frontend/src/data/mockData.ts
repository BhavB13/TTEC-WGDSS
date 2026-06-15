import {
  WeatherData,
  ForecastData,
  GridStatus,
  Recommendation,
} from "../types/dashboard";

export const mockWeather: WeatherData = {
  temperature_c: 30.5,
  humidity_percent: 75,
  wind_speed_kph: 22,
  wind_direction_deg: 120,
  pressure_hpa: 1012,
  precipitation_mm: 0,
  provider_name: "Open-Meteo",
};

export const mockForecast: ForecastData[] = [
  {
    forecast_timestamp: "2026-06-15T12:00:00Z",
    temperature_c: 31,
    wind_speed_kph: 25,
    precipitation_probability_percent: 45,
    confidence_score: 0.88,
  },
];

export const mockGridStatus: GridStatus = {
  total_available_capacity_mw: 1200,
  total_generation_mw: 950,
  reserve_margin_percent: 26.3,
  grid_status: "NORMAL",
};

export const mockRecommendation: Recommendation = {
  probability_score: 0.82,
  recommendation: "START",
  reason: "Reserve margin below operating threshold.",
};

export const mockRecommendationHistory = [
  {
    timestamp: "2026-06-15T08:00:00Z",
    recommendation: "MONITOR",
    confidence: 0.65,
  },
  {
    timestamp: "2026-06-15T10:00:00Z",
    recommendation: "START",
    confidence: 0.82,
  },
];