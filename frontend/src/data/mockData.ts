import type {
  ForecastData,
  GridStatus,
  RecommendationData,
  WeatherData,
} from "../types/dashboard";

export const mockWeather: WeatherData = {
  timestamp: "2026-06-15T12:00:00Z",
  temperature_c: 30.5,
  humidity_percent: 75,
  rainfall_mm_hr: 0,
  cloud_cover_percent: 42,
  wind_speed_kmh: 22,
  weather_condition: "Partly cloudy",
  heat_index_c: 33.1,
  rain_severity: "DRY",
  wind_direction_deg: 120,
  pressure_hpa: 1012,
  provider_name: "Open-Meteo",
};

export const mockForecast: ForecastData[] = [
  {
    forecast_timestamp: "2026-06-15T12:00:00Z",
    temperature_c: 31,
    humidity_percent: 76,
    rainfall_mm_hr: 0.2,
    cloud_cover_percent: 48,
    wind_speed_kmh: 25,
    weather_condition: "Partly cloudy",
    heat_index_c: 34,
    precipitation_probability_percent: 45,
    confidence_score: 0.88,
    rain_severity: "DRY",
    provider_name: "Open-Meteo",
  },
];

export const mockGridStatus: GridStatus = {
  timestamp: "2026-06-15T12:00:00Z",
  current_demand_mw: 950,
  current_generation_mw: 930,
  total_available_capacity_mw: 1200,
  reserve_margin_percent: 28.8,
  grid_status: "NORMAL",
  demand_period: "AFTERNOON",
  source_provider: "MockGridProvider",
  generation_units: [],
};

export const mockRecommendation: RecommendationData = {
  probability_score: 0.82,
  risk_level: "HIGH",
  forecast_demand_30m: 980,
  forecast_demand_60m: 1005,
  factors: [
    "High temperature increased expected demand",
    "Reserve margin below threshold",
  ],
  reason: "Reserve margin below threshold",
  recommendation: "START ADDITIONAL TURBINE",
};

export const mockRecommendationHistory = [
  {
    timestamp: "2026-06-15T08:00:00Z",
    recommendation: "MONITOR CONDITIONS",
    confidence: 0.65,
  },
  {
    timestamp: "2026-06-15T10:00:00Z",
    recommendation: "START ADDITIONAL TURBINE",
    confidence: 0.82,
  },
];
