# API Contract

All Version 1 service routes use the `/api/v1` prefix. The dashboard and storm
routes remain exposed under `/api` as hidden backward-compatible aliases.

## Dashboard snapshot

`GET /api/v1/dashboard/snapshot`

Query parameters:

- `latitude` and `longitude`: weather location, defaulting to Trinidad.
- `days`: forecast horizon from 1 to 14 days.
- `force_refresh`: bypasses the five-minute in-memory weather cache.

The response contains:

```json
{
  "snapshot_id": "7f104020-5ba7-4f94-b828-2332c1929a2e",
  "weather": {},
  "grid": {
    "current_demand_mw": 1229.5,
    "current_generation_mw": 1386.0,
    "total_available_capacity_mw": 1698.5,
    "spinning_reserve_mw": 122.3,
    "spinning_reserve_source": "GSYS SYSTEM_CORRECTED_SPIN_TOTAL",
    "reserve_margin_percent": 38.1
  },
  "forecast": { "items": [] },
  "probability": {
    "probability_score": 0.567,
    "capacity_risk_percent": 56.7,
    "risk_level": "HIGH",
    "capacity_status": "Prepare Generation",
    "probability_method": "NORMAL_RESIDUAL_EXCEEDANCE",
    "aggregation_method": "MAX_HORIZON_PROBABILITY",
    "capacity_basis": "FORECAST_TRA_MINUS_FORECAST_DEMAND",
    "formula_version": "wgdss-capacity-risk-v5",
    "peak_risk_horizon_minutes": 20,
    "peak_risk_timestamp": "2026-06-16T12:20:00",
    "forecast_demand_mw": 1215.3,
    "forecast_uncertainty_mw": 31.4,
    "forecast_tra_mw": 1240.0,
    "projected_reserve_mw": 24.7,
    "required_reserve_mw": 30.0,
    "reserve_surplus_mw": -5.3,
    "reserve_deficit_mw": 5.3,
    "reserve_insufficient_horizon_minutes": 20,
    "reserve_insufficient_at": "2026-06-16T12:20:00",
    "uncertainty_source": "CALIBRATED_HISTORICAL_RESIDUALS",
    "tra_projection_basis": "CURRENT_TRA_HELD_SCENARIO_NO_DISPATCH_PLAN",
    "expected_shortfall_mw": 26.3,
    "projected_shortfall_mw": 67.3,
    "decision_deadline_at": "2026-06-16T11:20:00",
    "severity_level": "HEAVY_START",
    "urgency": "ACTION_DUE",
    "risk_profile": [
      {
        "horizon_minutes": 20,
        "probability": 0.567,
        "capacity_risk_percent": 56.7,
        "capacity_status": "Prepare Generation",
        "forecast_demand_mw": 1215.3,
        "forecast_uncertainty_mw": 31.4,
        "forecast_lower_mw": 1163.7,
        "forecast_upper_mw": 1266.9,
        "forecast_tra_mw": 1240.0,
        "projected_reserve_mw": 24.7,
        "required_reserve_mw": 30.0,
        "reserve_surplus_mw": -5.3,
        "reserve_deficit_mw": 5.3,
        "safe_online_capacity_mw": 1210.0,
        "reserve_adjusted_headroom_mw": -5.3,
        "expected_shortfall_mw": 26.3,
        "conservative_shortfall_mw": 56.9,
        "reserve_expected_insufficient": true,
        "uncertainty_source": "CALIBRATED_HISTORICAL_RESIDUALS",
        "tra_projection_basis": "CURRENT_TRA_HELD_SCENARIO_NO_DISPATCH_PLAN"
      }
    ],
    "drivers": [
      {
        "label": "Projected reserve is 24.7 MW, 5.3 MW below the 30 MW target",
        "direction": "INCREASES_RISK",
        "category": "CAPACITY"
      }
    ],
    "policy_status": "PROTOTYPE_UNCONFIRMED"
  },
  "recommendation": {},
  "capacity_plan": {
    "snapshot_id": "7f104020-5ba7-4f94-b828-2332c1929a2e",
    "status": "AVAILABLE",
    "action_source": "SYSTEM_RECOMMENDED",
    "advisory_only": true,
    "advisory_notice": "ADVISORY ONLY - MANUAL OPERATOR ACTION REQUIRED",
    "system_suggestion": "REVIEW START OF 1 X SMALL FAST-START SET (15.0 MW TOTAL)",
    "system_suggestion_basis": [
      "No-action peak risk is 56.7% against the 20.0% Watch threshold",
      "The selected configured plan adds 15.0 MW after its lead time"
    ],
    "current_tra_mw": 1240.0,
    "current_tra_observed_at": "2026-06-16T12:00:00-04:00",
    "current_tra_source": "GSYS SYSTEM_ONLN_TOTAL via HistoricalScadaReplay",
    "current_tra_quality_status": "GOOD",
    "required_reserve_mw": 30.0,
    "target_risk_probability": 0.2,
    "baseline_peak_risk_percent": 56.7,
    "post_plan_peak_risk_percent": 18.4,
    "risk_reduction_percentage_points": 38.3,
    "block_definitions": [],
    "recommended_actions": [],
    "evaluated_actions": [],
    "profile": [],
    "warnings": []
  },
  "demand_forecast": {
    "horizons": [
      {
        "horizon_hours": 6,
        "forecast_demand_mw": 1274.4,
        "forecast_uncertainty_mw": 30.9,
        "confidence_lower_mw": 1223.6,
        "confidence_upper_mw": 1325.2,
        "confidence_level": 0.8,
        "model_name": "ExtraTreesRegressor+SimilarPeriods",
        "model_version": "demand-forecast-v5.0",
        "mae": 17.9,
        "rmse": 23.1,
        "mape": 1.5,
        "temperature_load_correlation": -0.1,
        "similar_period_forecast_mw": 1261.0,
        "similar_examples": [],
        "contributing_factors": []
      }
    ]
  },
  "model_status": {
    "active_model": "persistence",
    "model_version": "demand-forecast-v5.0",
    "mode": "BASELINE_ACTIVE",
    "trained_through": "2026-06-30T09:00:00Z",
    "feature_profile": "demand_weather_grid_state_v5",
    "validation_status": "PROTOTYPE",
    "training_span_hours": 550,
    "train_row_count": 440,
    "test_row_count": 110,
    "candidate_metrics": {},
    "metrics": {
      "mae": 10,
      "rmse": 12,
      "mape": 1.2,
      "peak_error_mw": 18.4,
      "residual_std": 30
    },
    "baseline_comparison": {
      "best_baseline": "persistence",
      "ml_beats_baseline": false
    }
  },
  "scada_status": {
    "mode": "historical_replay",
    "source": "historical_csv",
    "source_system": "AspenTech OSI trend export",
    "source_provider": "csv_trend_export",
    "aggregation": "interval_overlap_hourly",
    "latest_snapshot": "2026-06-30T08:00:00Z",
    "available_at": "2026-06-30T09:00:00Z",
    "quality_status": "GOOD",
    "missing_fields": "",
    "coverage_percent": 100.0,
    "anomaly_flags": [],
    "field_provenance": {},
    "formula_version": "wgdss-headroom-v1"
  },
  "replay": {
    "status": {
      "mode": "historical_replay",
      "cursor_at": "2025-06-01T08:00:00",
      "is_playing": false,
      "step_minutes": 60,
      "speed_multiplier": 600,
      "progress_percent": 1.1
    },
    "operational_history": [],
    "full_day_load_forecast": [],
    "monthly_history": [],
    "summary": {}
  },
  "calibration": {
    "selected_scenario_key": "rainy",
    "selection_confidence": 0.64,
    "scenario_scores": {
      "hot": 0.21,
      "typical": 0.37,
      "rainy": 0.51
    },
    "scenarios": []
  },
  "data_quality": {
    "overall_status": "GOOD",
    "weather_status": "LIVE",
    "grid_status": "SIMULATED",
    "calibration_status": "CALIBRATED",
    "weather_source": "Open-Meteo",
    "grid_source": "MockGridProvider",
    "age_seconds": 900,
    "is_stale": false,
    "fallback_used": false,
    "notes": []
  }
}
```

Weather status values are `LIVE`, `CALIBRATED`, `FALLBACK`, and `STALE`.
Grid status identifies the Version 1 mock source as `SIMULATED`.
Demonstration replay snapshots identify grid/weather status as
`SIMULATED_REPLAY` and decision status as `SIMULATION`.

For historical SCADA replay, the compatibility field `current_demand_mw` uses
`PTL132 GENERATION TOTALS` as an explicitly unconfirmed demand proxy;
`current_generation_mw` is the current project interpretation of Total Running
Availability (TRA), and `spinning_reserve_mw` is sourced directly from `GSYS
SYSTEM_CORRECTED_SPIN_TOTAL`. The UI presents that corrected MW value as
**System Spin**. The retained `reserve_margin_percent` field is the legacy
TA-minus-demand available-capacity margin; it is not the operator-facing spin
value. `TRA - demand` is exposed only as a diagnostic gap and can differ from
corrected spin. Tag meanings and units require the approvals listed in
`docs/SCADA_OSI_CONFIRMATION_REGISTER.md`.

## Replay controls

- `GET /api/v1/replay/status`
- `POST /api/v1/replay/control`

Control actions are `play`, `pause`, `reset`, `step`, and `configure`.
`step_minutes` accepts 15 through 1,440 minutes and `speed_multiplier` accepts 1
through 86,400 simulated seconds per real second.

After the replay-clock migration, the initial `cursor_at` maps the current
Trinidad day/hour into June, `clock_aligned` is true, and playback starts at
real-time speed. `reset` is presented as **Sync Now** and repeats this mapping.

Each normal/live hourly forecast item includes `source_count`, `source_names`,
`temperature_spread_c`, and `cloud_cover_spread_percent`. The normal operating
path reconciles Open-Meteo Best Match, MET Norway Locationforecast, and NOAA GFS
by timestamp. `source_sync_status` is `COMPLETE` only when all three sources are
present for that hour, and `field_source_counts` shows per-field coverage.
`confidence_score` is reduced when sources disagree or are unavailable.
Historical SCADA replay first requests the exact archived Open-Meteo model run
that would have been available at the source cursor. ECMWF IFS, NOAA GFS, and
DWD ICON are reconciled by valid hour, then mapped by lead time onto the display
clock. That ensemble drives the weather-sensitive replay demand forecast and
operating-risk calculation. If the archived run is unavailable, replay falls
back to the one-source, past-only weather baseline and exact-cursor persisted
demand artifacts. Imported SCADA temperature remains the measured replay
temperature. None of these replay rules replace live weather outside replay.

Probability and recommendation objects retain compatibility fields and expose
raw, unrounded capacity-risk evidence. For every valid horizon through six
hours, `risk_profile` reports forecast demand, current TRA held, projected reserve,
the 30 MW target, surplus or deficit, uncertainty, probability, status, and
provenance. The top-level evidence comes from the same maximum-risk horizon.
`reserve_insufficient_at` identifies the earliest horizon whose mean projected
reserve is 30 MW or less. Generator guidance remains read-only and does not
execute dispatch. Compatibility probability and recommendation fields always
describe the no-action baseline; hypothetical starts are confined to
`capacity_plan`.

## Capacity-plan what-if evaluation

`POST /api/v1/capacity-plan/evaluate`

Request:

```json
{
  "snapshot_id": "7f104020-5ba7-4f94-b828-2332c1929a2e",
  "actions": [
    {
      "block_id": "small-fast-start",
      "count": 2
    }
  ]
}
```

The endpoint recalculates a hypothetical post-plan TRA/reserve/risk profile
against the immutable no-action context registered for that dashboard
snapshot. An omitted `start_at` means an immediate hypothetical start at
evaluation time (or at the replay cursor in replay mode). A supplied
`start_at` must be an ISO-8601 timestamp.

- `404`: unknown snapshot ID; refresh the dashboard.
- `409`: snapshot context expired; refresh the dashboard.
- `422`: unknown/disabled block, excessive block count, duplicate block, or
  proposed capacity above current TA-minus-TRA headroom.

The endpoint has no write path to SCADA, generation equipment, or the database.
The app-local context cache is bounded and expires after 15 minutes by default;
a production multi-worker deployment must replace it with a shared expiring
context store.

`demand_forecast`, `model_status`, and `scada_status` remain optional for normal
provider mode. Replay returns cursor-consistent status and forecast values. If
an offline 1h/2h/6h artifact matches the historical source cursor exactly, the
API exposes that artifact and its audit metadata; otherwise it uses the
cutoff-safe replay forecast and never substitutes a later historical model.

Each demand horizon may include a calibrated 90% confidence interval,
horizon-specific MAE/RMSE/MAPE/residual standard deviation, adjusted
temperature/load correlation, the similarity-only estimate, comparable
historical periods, and major forecast factors. Similar examples are selected
only from targets already observable at forecast issuance time.

When a coherent forecast generation cohort and latest SCADA grid snapshot are present,
the probability/recommendation block may be produced by the operating-risk
engine. It calculates `projected reserve = current TRA - forecast demand` and
then evaluates `P(current TRA - actual demand < 30 MW)` using calibrated demand
forecast error. Corrected System Spin remains separate observed context. TA is
only used to bound verified startable capacity. Current TRA is held as the
explicit no-action baseline. Proposed aggregate starts produce a separate
post-plan profile only after their lead time. The headline probability remains
the maximum no-action horizon probability, avoiding a false independence
assumption across correlated horizons. This remains a historical-export
modeling foundation, not a live SCADA stream.

## Health

`GET /api/v1/health`

Returns database connectivity, primary, consensus, and fallback weather-provider
configuration, Open-Meteo daily request usage, and calibration row/sample
availability.

## Supporting routes

- `GET /api/v1/weather/current`
- `GET /api/v1/weather/forecast`
- `GET /api/v1/grid/status`
- `GET /api/v1/recommendations`

The OpenAPI schema and interactive documentation are available at `/docs`.
# Present Timeline and Selected Day

`GET /api/v1/dashboard/snapshot` accepts the optional
`selected_date=YYYY-MM-DD` parameter. Omitting it follows the active June
simulated-present cursor. An explicit date loads an available previous June day
without creating a second dashboard mode. The response includes `time_context`
with active and selected dates, source, classification, completeness, and
cutoff-safe hourly observations. The former `mode`, date-range, and granularity
parameters have been removed. See `docs/PRESENT_TIME_NAVIGATION.md`.
