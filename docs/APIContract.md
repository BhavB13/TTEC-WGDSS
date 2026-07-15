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
  "weather": {},
  "grid": {},
  "forecast": { "items": [] },
  "probability": {},
  "recommendation": {},
  "demand_forecast": {
    "horizons": []
  },
  "model_status": {
    "active_model": "persistence",
    "model_version": "demand-forecast-v2.1",
    "mode": "BASELINE_ACTIVE",
    "trained_through": "2026-06-30T09:00:00Z",
    "feature_profile": "demand_weather_v2_1",
    "validation_status": "PROTOTYPE",
    "training_span_hours": 550,
    "train_row_count": 440,
    "test_row_count": 110,
    "candidate_metrics": {},
    "metrics": {
      "mae": 10,
      "rmse": 12,
      "mape": 1.2,
      "residual_std": 30
    },
    "baseline_comparison": {
      "best_baseline": "persistence",
      "ml_beats_baseline": false
    }
  },
  "scada_status": {
    "source": "historical_csv",
    "latest_snapshot": "2026-06-30T08:00:00Z",
    "available_at": "2026-06-30T09:00:00Z",
    "quality_status": "GOOD",
    "missing_fields": ""
  },
  "replay": {
    "status": {
      "mode": "SIMULATED_LIVE",
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
Historical SCADA replay instead exposes a one-source, past-only weather baseline
and uses imported SCADA temperature as the measured replay temperature. It does
not replace a live weather observation outside replay.

Probability and recommendation objects retain their original fields and also
expose `decision_action`, `generator_set`, `recommended_capacity_mw`,
`projected_shortfall_mw`, `expected_shortfall_mw`, `expected_load_rise_mw`,
`expected_rise_minutes`, `startup_time_minutes`, `decision_confidence`, and
`weather_effect_mw`. These fields explain generator startup guidance; they do
not execute dispatch.

`demand_forecast`, `model_status`, and `scada_status` remain optional for normal
provider mode. Replay returns cursor-consistent status and forecast values. If
an offline 1h/2h/6h artifact matches the historical source cursor exactly, the
API exposes that artifact and its audit metadata; otherwise it uses the
cutoff-safe replay forecast and never substitutes a later historical model.

When a coherent forecast generation cohort and latest SCADA grid snapshot are present,
the probability/recommendation block may be produced by the operating-risk
engine. That engine compares forecast demand and uncertainty against safe online
capacity across all valid 1h/2h/6h horizons. It is still a historical-export
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
