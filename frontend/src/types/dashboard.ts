export interface GenerationUnit {
  station_name: string;
  unit_name: string;
  fuel_type: string;
  available_capacity_mw: number;
  current_output_mw: number;
  status: string;
  is_dispatchable: boolean;
}

export interface WeatherData {
  timestamp: string | null;
  temperature_c: number;
  humidity_percent: number;
  rainfall_mm_hr: number;
  cloud_cover_percent: number;
  wind_speed_kmh: number;
  weather_condition: string;
  heat_index_c: number;
  rain_severity: string;
  wind_direction_deg?: number | null;
  pressure_hpa?: number | null;
  provider_name: string;
}

export interface ForecastData {
  forecast_timestamp: string;
  temperature_c: number;
  humidity_percent: number;
  rainfall_mm_hr: number;
  cloud_cover_percent: number;
  wind_speed_kmh: number;
  weather_condition: string;
  heat_index_c: number;
  precipitation_probability_percent: number;
  confidence_score: number;
  rain_severity: string;
  provider_name: string;
}

export interface ForecastBundle {
  items: ForecastData[];
}

export interface GridStatus {
  timestamp?: string | null;
  current_demand_mw: number;
  current_generation_mw: number;
  total_available_capacity_mw: number;
  reserve_margin_percent: number;
  grid_status: string;
  demand_period: string;
  source_provider: string;
  generation_units: GenerationUnit[];
}

export interface ProbabilityData {
  probability_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  forecast_demand_30m: number;
  forecast_demand_60m: number;
  factors: string[];
  reason: string;
}

export interface RecommendationData extends ProbabilityData {
  recommendation: "NO ACTION REQUIRED" | "MONITOR CONDITIONS" | "START ADDITIONAL TURBINE" | string;
}

export interface DashboardSnapshot {
  weather: WeatherData;
  grid: GridStatus;
  forecast: ForecastBundle;
  probability: ProbabilityData;
  recommendation: RecommendationData;
}

// Backwards-compatible aliases for existing component imports.
export type WeatherSnapshot = WeatherData;
export type ForecastSnapshot = ForecastData;
export type GridSnapshot = GridStatus;
export type RecommendationSnapshot = RecommendationData;
