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
  source_count?: number;
  source_names?: string[];
  temperature_spread_c?: number;
  cloud_cover_spread_percent?: number;
}

export interface ForecastBundle {
  items: ForecastData[];
}

export interface CalibrationPoint {
  hour: number;
  demand_mw?: number | null;
  spin_mw?: number | null;
  temperature_c?: number | null;
  quality_status?: string | null;
}

export interface CalibrationScenario {
  scenario_key: string;
  scenario_label: string;
  operating_regime: string;
  source_workbook: string;
  source_sheet: string;
  demand_curve: CalibrationPoint[];
  scada_temperature_trace: CalibrationPoint[];
}

export interface CalibrationSnapshot {
  source_archive?: string | null;
  imported_at?: string | null;
  selected_scenario_key?: string | null;
  selected_scenario_label?: string | null;
  selected_hour?: number | null;
  selected_temperature_c?: number | null;
  selected_demand_mw?: number | null;
  selected_next_demand_mw?: number | null;
  selected_spin_mw?: number | null;
  selected_next_spin_mw?: number | null;
  selection_reason?: string | null;
  selection_confidence?: number | null;
  scenario_scores: Record<string, number>;
  scenarios: CalibrationScenario[];
}

export interface DataQuality {
  overall_status: "GOOD" | "DEGRADED" | string;
  weather_status: "LIVE" | "CALIBRATED" | "STALE" | "FALLBACK" | string;
  grid_status: "LIVE" | "SIMULATED" | string;
  calibration_status: "CALIBRATED" | "UNAVAILABLE" | string;
  weather_source: string;
  grid_source: string;
  observed_at?: string | null;
  age_seconds?: number | null;
  is_stale: boolean;
  fallback_used: boolean;
  grid_observed_at?: string | null;
  grid_age_seconds?: number | null;
  grid_is_stale?: boolean;
  grid_fallback_used?: boolean;
  decision_status?: string;
  notes: string[];
}

export interface DemandForecastHorizon {
  horizon_hours: number;
  forecast_timestamp: string;
  forecast_demand_mw: number;
  forecast_uncertainty_mw: number;
  model_name: string;
  model_version: string;
  baseline_name: string;
  baseline_forecast_mw: number;
  quality_status: string;
}

export interface DemandForecastBundle {
  horizons: DemandForecastHorizon[];
}

export interface ModelStatus {
  active_model?: string | null;
  model_version?: string | null;
  mode: string;
  trained_through?: string | null;
  metrics: {
    mae?: number | null;
    rmse?: number | null;
    mape?: number | null;
    residual_std?: number | null;
  };
  baseline_comparison: {
    best_baseline?: string | null;
    ml_beats_baseline?: boolean | null;
  };
}

export interface ScadaStatus {
  source: string;
  latest_snapshot?: string | null;
  quality_status: string;
  missing_fields: string;
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
  engine_version?: string;
  probability_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "UNAVAILABLE";
  forecast_demand_30m: number;
  forecast_demand_60m: number;
  factors: string[];
  reason: string;
}

export interface RecommendationData extends ProbabilityData {
  recommendation: "NO ACTION REQUIRED" | "MONITOR CONDITIONS" | "START ADDITIONAL TURBINE" | string;
}

export interface DashboardSnapshot {
  snapshot_id?: string;
  weather: WeatherData;
  grid: GridStatus;
  forecast: ForecastBundle;
  probability: ProbabilityData;
  recommendation: RecommendationData;
  calibration?: CalibrationSnapshot | null;
  data_quality: DataQuality;
  demand_forecast?: DemandForecastBundle | null;
  model_status?: ModelStatus | null;
  scada_status?: ScadaStatus | null;
}

// Backwards-compatible aliases for existing component imports.
export type WeatherSnapshot = WeatherData;
export type ForecastSnapshot = ForecastData;
export type GridSnapshot = GridStatus;
export type RecommendationSnapshot = RecommendationData;
