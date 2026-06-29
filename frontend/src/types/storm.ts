export interface StormAdvisoryLink {
  advisory_number?: string | null;
  issuance?: string | null;
  url?: string | null;
}

export interface StormSystem {
  id: string;
  bin_number?: string | null;
  name?: string | null;
  basin?: string | null;
  classification?: string | null;
  classification_label?: string | null;
  intensity_knots?: number | null;
  pressure_mb?: number | null;
  latitude?: string | null;
  longitude?: string | null;
  latitude_numeric?: number | null;
  longitude_numeric?: number | null;
  movement_direction_deg?: number | null;
  movement_speed_mph?: number | null;
  last_update?: string | null;
  public_advisory?: StormAdvisoryLink | null;
  forecast_advisory?: StormAdvisoryLink | null;
  forecast_discussion?: StormAdvisoryLink | null;
  forecast_graphics?: StormAdvisoryLink | null;
  forecast_track_kmz_url?: string | null;
  wind_speed_probabilities_url?: string | null;
}

export interface StormTrackingSnapshot {
  source_url: string;
  status: "available" | "unavailable";
  fetched_at?: string | null;
  message?: string | null;
  active_storms: StormSystem[];
}
