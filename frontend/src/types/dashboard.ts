export interface WeatherData {
  temperature_c: number;
  humidity_percent: number;
  wind_speed_kph: number;
  wind_direction_deg: number;
  pressure_hpa: number;
  precipitation_mm: number;
  provider_name: string;
}

export interface ForecastData {
  forecast_timestamp: string;
  temperature_c: number;
  wind_speed_kph: number;
  precipitation_probability_percent: number;
  confidence_score: number;
}

export interface GridStatus {
  total_available_capacity_mw: number;
  total_generation_mw: number;
  reserve_margin_percent: number;
  grid_status: string;
}

export interface Recommendation {
  probability_score: number;
  recommendation: string;
  reason: string;
}
