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
