export interface GenerationUnit {
  station_name: string;
  unit_name: string;
  fuel_type: string;
  available_capacity_mw: number;
  current_output_mw: number;
  status: string;
  is_dispatchable: boolean;
}

export interface TemperatureSample {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  location_type: string;
  notes: string;
  demand_weight: number;
  effective_weight_percent: number;
  temperature_c: number;
  humidity_percent?: number | null;
  rainfall_mm_hr?: number | null;
  cloud_cover_percent?: number | null;
  wind_speed_kmh?: number | null;
  wind_direction_deg?: number | null;
  pressure_hpa?: number | null;
  precipitation_probability_percent?: number | null;
  timestamp: string | null;
  provider_name: string;
  status: string;
}

export interface TemperatureAggregation {
  label: string;
  method: string;
  policy_version: string;
  policy_status: string;
  status: string;
  source_name: string;
  weighted_average_c: number;
  weighted_humidity_percent?: number | null;
  weighted_rainfall_mm_hr?: number | null;
  weighted_cloud_cover_percent?: number | null;
  weighted_wind_speed_kmh?: number | null;
  weighted_wind_direction_deg?: number | null;
  weighted_pressure_hpa?: number | null;
  weighted_precipitation_probability_percent?: number | null;
  minimum_c: number;
  maximum_c: number;
  spread_c: number;
  sample_count: number;
  expected_sample_count: number;
  weight_coverage_percent: number;
  field_weight_coverage_percent?: Record<string, number>;
  samples: TemperatureSample[];
}

export interface WeatherData {
  timestamp: string | null;
  temperature_c: number;
  humidity_percent: number;
  rainfall_mm_hr: number;
  cloud_cover_percent: number;
  wind_speed_kmh: number;
  wind_direction_deg?: number | null;
  pressure_hpa?: number | null;
  weather_condition: string;
  heat_index_c: number;
  rain_severity: string;
  provider_name: string;
  temperature_aggregation?: TemperatureAggregation | null;
  weather_aggregation?: TemperatureAggregation | null;
}

export interface ForecastData {
  forecast_timestamp: string;
  temperature_c: number;
  humidity_percent: number;
  rainfall_mm_hr: number;
  cloud_cover_percent: number;
  wind_speed_kmh: number;
  wind_direction_deg?: number | null;
  pressure_hpa?: number | null;
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
  source_sync_status?: "COMPLETE" | "DEGRADED";
  field_source_counts?: Record<string, number>;
  temperature_aggregation?: TemperatureAggregation | null;
  weather_aggregation?: TemperatureAggregation | null;
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
  feature_timestamp?: string | null;
  generated_at?: string | null;
  feature_profile?: string | null;
  validation_status?: string | null;
  training_rows?: number | null;
  confidence_lower_mw?: number | null;
  confidence_upper_mw?: number | null;
  confidence_level?: number | null;
  p10_demand_mw?: number | null;
  p50_demand_mw?: number | null;
  p90_demand_mw?: number | null;
  training_start_at?: string | null;
  training_end_at?: string | null;
  feature_importance?: Record<string, number>;
  fallback_reason?: string | null;
  temperature_load_correlation?: number | null;
  similar_period_forecast_mw?: number | null;
  similar_examples?: Array<{
    feature_timestamp: string;
    target_timestamp: string;
    target_demand_mw: number;
    temperature_c?: number | null;
    forecast_temperature_c?: number | null;
    day_type: string;
    distance: number;
  }>;
  contributing_factors?: string[];
  mae?: number | null;
  rmse?: number | null;
  mape?: number | null;
  residual_std?: number | null;
}

export interface DemandForecastBundle {
  horizons: DemandForecastHorizon[];
}

export interface ModelStatus {
  active_model?: string | null;
  model_version?: string | null;
  mode: string;
  trained_through?: string | null;
  generated_at?: string | null;
  feature_profile?: string | null;
  validation_status?: string | null;
  training_span_hours?: number | null;
  train_row_count?: number | null;
  test_row_count?: number | null;
  candidate_metrics?: Record<string, unknown>;
  feature_importance?: Record<string, number>;
  fallback_reason?: string | null;
  training_start_at?: string | null;
  training_end_at?: string | null;
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
  mode: "historical_replay" | "simulation" | "live_read_only" | "unavailable";
  source: string;
  source_system?: string;
  source_provider?: string;
  aggregation?: string;
  observation_time_basis?: string;
  latest_snapshot?: string | null;
  available_at?: string | null;
  quality_status: string;
  missing_fields: string;
  coverage_percent?: number | null;
  quality_notes?: string;
  anomaly_flags?: string[];
  field_provenance?: Record<string, unknown>;
  formula_version?: string | null;
  archive_source?: string | null;
  archive_import_status?: string | null;
  archive_validation_status?: string | null;
  archive_data_start_at?: string | null;
  archive_data_end_at?: string | null;
  period_reports?: Array<{
    period: string;
    validation_status: string;
    missing_tags: string[];
    clean_row_count: number;
    out_of_period_rows: number;
  }>;
  known_data_gaps?: string[];
  alignment_validation_status?: string | null;
  alignment_selected_method?: string | null;
  alignment_mismatch_count?: number | null;
  alignment_method_metrics?: Array<Record<string, unknown>>;
}

export interface ReplayStatus {
  mode: "historical_replay" | "simulation" | "live_read_only";
  dataset_label: string;
  dataset_start: string;
  dataset_end: string;
  replay_start: string;
  replay_end: string;
  cursor_at: string;
  is_playing: boolean;
  step_minutes: number;
  speed_multiplier: number;
  progress_percent: number;
  revealed_records: number;
  total_replay_records: number;
  source: string;
  clock_aligned: boolean;
}

export interface OperationalTrendPoint {
  timestamp: string;
  demand_mw: number;
  generation_mw: number;
  spinning_reserve_mw: number;
  available_capacity_mw: number;
  reserve_margin_percent: number;
  temperature_c: number;
  rainfall_mm_hr: number;
  data_phase: "HISTORICAL_SOURCE" | "REPLAY_REVEALED";
}

export interface LoadForecastPoint {
  timestamp: string;
  forecast_demand_mw: number;
  historical_average_mw: number;
  actual_demand_mw?: number | null;
  actual_temperature_c?: number | null;
  forecast_temperature_c?: number | null;
  uncertainty_mw: number;
  weather_impact_mw: number;
  weather_confidence: number;
  weather_source_count: number;
}

export interface ReplayDashboard {
  status: ReplayStatus;
  operational_history: OperationalTrendPoint[];
  full_day_load_forecast: LoadForecastPoint[];
  monthly_history: Array<{
    month: string;
    average_demand_mw: number;
    peak_demand_mw: number;
    average_temperature_c: number;
    rainfall_total_mm: number;
    data_phase: "HISTORICAL" | "REPLAY_SOURCE";
  }>;
  summary: {
    historical_months: number;
    historical_record_count: number;
    historical_average_demand_mw: number;
    historical_peak_demand_mw: number;
    replay_month_label: string;
    current_day_peak_forecast_mw: number;
    forecast_model: string;
    forecast_mode: string;
    forecast_mae_mw: number;
    baseline_mae_mw: number;
    residual_std_mw: number;
    training_rows: number;
    forecast_trained_through?: string | null;
    weather_features: string[];
  };
}

export interface DaySeriesPoint {
  timestamp: string;
  demand_mw?: number | null;
  generation_tra_mw?: number | null;
  spinning_reserve_mw?: number | null;
  available_capacity_mw?: number | null;
  temperature_c?: number | null;
  quality_status: string;
  completeness_percent: number;
  data_phase: "JUNE_OBSERVED";
}

export interface DashboardTimeContext {
  selected_date: string;
  active_date: string;
  is_active_day: boolean;
  displayed_at: string;
  granularity: "hourly";
  source: string;
  value_classification: string;
  available_start: string;
  available_end: string;
  available_dates: string[];
  completeness_percent: number;
  record_count: number;
  is_complete: boolean;
  notice?: string | null;
  series: DaySeriesPoint[];
}

export interface GridStatus {
  timestamp?: string | null;
  current_demand_mw: number;
  current_generation_mw: number;
  total_available_capacity_mw: number;
  reserve_margin_percent: number;
  spinning_reserve_mw?: number | null;
  spinning_reserve_source?: string | null;
  grid_status: string;
  demand_period: string;
  source_provider: string;
  generation_units: GenerationUnit[];
}

export interface RiskDriver {
  label: string;
  direction: "INCREASES_RISK" | "REDUCES_RISK" | "QUALITY_WARNING" | "CONTEXT" | string;
  category: string;
}

export interface RiskHorizon {
  horizon_minutes: number;
  forecast_timestamp?: string | null;
  probability: number;
  forecast_demand_mw: number;
  forecast_uncertainty_mw: number;
  forecast_lower_mw: number;
  forecast_upper_mw: number;
  confidence_level: number;
  immediate_online_capacity_mw: number;
  safe_online_capacity_mw: number;
  required_reserve_mw: number;
  online_headroom_mw: number;
  reserve_adjusted_headroom_mw: number;
  expected_shortfall_mw: number;
  conservative_shortfall_mw: number;
  expected_load_rise_mw: number;
  weather_effect_mw: number;
  forecast_confidence: number;
  startup_lead_time_minutes: number;
  decision_deadline_minutes?: number | null;
  decision_deadline_at?: string | null;
  urgency: string;
  expected_online_capacity_mw?: number;
  expected_available_capacity_mw?: number | null;
  expected_spinning_reserve_mw?: number | null;
  demand_ramp_mw_per_hour?: number;
  capacity_projection_basis?: string;
  capacity_risk_percent: number;
  forecast_tra_mw: number;
  projected_reserve_mw: number;
  reserve_surplus_mw: number;
  reserve_deficit_mw: number;
  capacity_status: CapacityStatus;
  reserve_expected_insufficient: boolean;
  uncertainty_source: string;
  tra_projection_basis: string;
}

export type CapacityStatus =
  | "Normal"
  | "Watch"
  | "Prepare Generation"
  | "Add Generation"
  | "Unavailable"
  | string;

export interface ProbabilityData {
  engine_version?: string;
  policy_status?: string;
  probability_score: number;
  capacity_risk_percent: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "UNAVAILABLE";
  capacity_status: CapacityStatus;
  forecast_demand_30m: number;
  forecast_demand_60m: number;
  factors: string[];
  reason: string;
  decision_action?: string;
  generator_set?: string;
  recommended_capacity_mw?: number;
  projected_shortfall_mw?: number;
  expected_shortfall_mw?: number;
  expected_load_rise_mw?: number;
  expected_rise_minutes?: number;
  startup_time_minutes?: number;
  decision_confidence?: number;
  weather_effect_mw?: number;
  available_start_capacity_mw?: number | null;
  residual_shortfall_mw?: number;
  risk_profile?: RiskHorizon[];
  peak_risk_horizon_minutes?: number | null;
  peak_risk_timestamp?: string | null;
  forecast_lower_mw?: number;
  forecast_upper_mw?: number;
  immediate_online_capacity_mw?: number;
  safe_online_capacity_mw?: number;
  required_reserve_mw?: number;
  online_headroom_mw?: number;
  reserve_adjusted_headroom_mw?: number;
  severity_level?: string;
  urgency?: string;
  decision_deadline_minutes?: number | null;
  decision_deadline_at?: string | null;
  drivers?: RiskDriver[];
  increasing_factors?: string[];
  reducing_factors?: string[];
  quality_warnings?: string[];
  probability_method?: string;
  aggregation_method?: string;
  capacity_basis?: string;
  expected_online_capacity_mw?: number;
  expected_available_capacity_mw?: number | null;
  expected_spinning_reserve_mw?: number | null;
  demand_ramp_mw_per_hour?: number;
  capacity_projection_basis?: string;
  forecast_demand_mw: number;
  forecast_uncertainty_mw: number;
  forecast_tra_mw: number;
  projected_reserve_mw: number;
  reserve_surplus_mw: number;
  reserve_deficit_mw: number;
  reserve_insufficient_horizon_minutes?: number | null;
  reserve_insufficient_at?: string | null;
  uncertainty_source: string;
  tra_projection_basis: string;
  risk_components?: Record<string, number | string | boolean | null>;
  formula_version?: string;
}

export interface RecommendationData extends ProbabilityData {
  recommendation: "NO ACTION REQUIRED" | "MONITOR CONDITIONS" | "START ADDITIONAL TURBINE" | string;
}

export interface GenerationBlockDefinition {
  block_id: string;
  label: string;
  block_class: "SMALL" | "HEAVY" | string;
  unit_capacity_mw?: number | null;
  startable_count: number;
  startup_lead_time_minutes: number;
  enabled: boolean;
  provenance: string;
  verification_status: string;
}

export interface CapacityStartActionInput {
  block_id: string;
  count: number;
  start_at?: string | null;
}

export interface CapacityStartAction {
  block_id: string;
  block_label: string;
  block_class: string;
  count: number;
  unit_capacity_mw: number;
  total_capacity_mw: number;
  startup_lead_time_minutes: number;
  start_at: string;
  start_by?: string | null;
  expected_online_at: string;
  verification_status: string;
  action_status: "PROPOSED" | "VERIFICATION_REQUIRED" | string;
  applied_to_projection: boolean;
}

export interface CapacityPlanHorizon {
  horizon_minutes: number;
  forecast_timestamp?: string | null;
  forecast_demand_mw: number;
  forecast_uncertainty_mw: number;
  baseline_tra_mw: number;
  baseline_reserve_mw: number;
  baseline_capacity_risk_percent: number;
  baseline_capacity_status: CapacityStatus;
  planned_tra_mw: number;
  applied_start_capacity_mw: number;
  planned_reserve_mw: number;
  planned_reserve_surplus_mw: number;
  planned_reserve_deficit_mw: number;
  planned_capacity_risk_percent: number;
  planned_capacity_status: CapacityStatus;
  required_reserve_mw: number;
}

export interface CapacityPlan {
  snapshot_id: string;
  status: "AVAILABLE" | "UNAVAILABLE" | "STALE_SNAPSHOT" | string;
  action_source: "NONE" | "SYSTEM_RECOMMENDED" | "OPERATOR_WHAT_IF" | string;
  advisory_only: boolean;
  advisory_notice: string;
  system_suggestion?: string;
  system_suggestion_basis?: string[];
  issue_time?: string | null;
  current_tra_mw?: number | null;
  current_tra_observed_at?: string | null;
  current_tra_age_seconds?: number | null;
  current_tra_source: string;
  current_tra_quality_status: string;
  current_tra_projection_basis: string;
  required_reserve_mw: number;
  target_risk_probability: number;
  baseline_peak_risk_percent: number;
  post_plan_peak_risk_percent: number;
  risk_reduction_percentage_points: number;
  first_unprotected_horizon_minutes?: number | null;
  first_unprotected_at?: string | null;
  interim_unmitigated_risk: boolean;
  unresolved_capacity_mw: number;
  block_definitions: GenerationBlockDefinition[];
  recommended_actions: CapacityStartAction[];
  evaluated_actions: CapacityStartAction[];
  profile: CapacityPlanHorizon[];
  configuration_status: string;
  warnings: string[];
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
  replay?: ReplayDashboard | null;
  capacity_plan?: CapacityPlan | null;
  time_context: DashboardTimeContext;
}

// Backwards-compatible aliases for existing component imports.
export type WeatherSnapshot = WeatherData;
export type ForecastSnapshot = ForecastData;
export type GridSnapshot = GridStatus;
export type RecommendationSnapshot = RecommendationData;
