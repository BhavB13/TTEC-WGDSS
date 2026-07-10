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
    "model_version": "demand-forecast-v1.3",
    "mode": "BASELINE_ACTIVE",
    "trained_through": "2026-06-30T09:00:00Z",
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
    "quality_status": "GOOD",
    "missing_fields": ""
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

Each hourly forecast item includes `source_count`, `source_names`,
`temperature_spread_c`, and `cloud_cover_spread_percent`. The normal operating
path reconciles Open-Meteo Best Match, MET Norway Locationforecast, and NOAA GFS
by timestamp. `confidence_score` is reduced when the sources disagree or fewer
than two sources are available. Imported SCADA temperature remains calibration
metadata; it does not replace a live weather observation.

`demand_forecast`, `model_status`, and `scada_status` are optional. They appear
after historical SCADA CSVs have been imported, normalized into grid snapshots,
converted into forecast training rows, and evaluated by the demand-forecast
service. If these model outputs are unavailable, existing weather/grid/mock
dashboard behavior remains unchanged.

When a latest 1-hour demand forecast and latest SCADA grid snapshot are present,
the probability/recommendation block may be produced by the operating-risk
engine. That engine compares forecast demand and uncertainty against safe online
capacity. It is still a historical-export modeling foundation, not a live SCADA
stream.

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
