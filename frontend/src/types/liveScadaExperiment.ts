export interface SnapshotFieldEvidence {
  field: string;
  source_tag?: string | null;
  timestamp?: string | null;
  cleaned_value?: number | null;
  engineering_unit?: string | null;
  status: string;
  warnings: string[];
}

export interface ExperimentalForecastPoint {
  horizon_hours: number;
  forecast_timestamp: string;
  forecast_demand_mw: number;
  uncertainty_mw: number;
  model_name: string;
  model_version: string;
  status: "MODEL_INFERENCE" | "REFERENCE_ONLY";
  reasons: string[];
}

export interface ExperimentalRiskPoint {
  horizon_hours: number;
  forecast_timestamp: string;
  generation_tra_mw?: number | null;
  forecast_demand_mw?: number | null;
  projected_tra_minus_demand_mw?: number | null;
  generation_need_probability?: number | null;
  risk_level: string;
  status: string;
}

export interface LiveScadaTestSession {
  session_id: string;
  experiment_label: string;
  advisory_notice: string;
  created_at: string;
  source: {
    source_filename: string;
    source_file_hash: string;
    source_timezone: string;
    imported_at: string;
    available_start?: string | null;
    available_end?: string | null;
    latest_valid_timestamp?: string | null;
    raw_record_count: number;
    cleaned_record_count: number;
    malformed_record_count: number;
    duplicate_record_count: number;
    future_record_count: number;
    missing_required_variables: string[];
    field_evidence: SnapshotFieldEvidence[];
    warnings: string[];
  };
  model: {
    status: string;
    model_name?: string | null;
    model_version?: string | null;
    training_start_at?: string | null;
    training_end_at?: string | null;
    training_policy: string;
    snapshot_used_for_training: boolean;
    preprocessing_refit: boolean;
    warnings: string[];
  };
  weather: {
    fetched_at: string;
    boundary_timestamp: string;
    post_boundary_weather_source?: string | null;
    response_hash: string;
    warnings: string[];
  };
  forecasts: ExperimentalForecastPoint[];
  reference_forecasts: ExperimentalForecastPoint[];
  risk: ExperimentalRiskPoint[];
  validation_warnings: string[];
  processing_metadata: {
    snapshot_age_seconds?: number;
    freshness_status?: string;
    [key: string]: unknown;
  };
}

export interface LiveScadaExperimentStatus {
  enabled: boolean;
  configured_source: boolean;
  source_path?: string | null;
  latest_session_id?: string | null;
  latest_available_timestamp?: string | null;
  message: string;
}
