# Configuration Reference

## Loading Rules

Backend configuration is defined by `backend/app/core/config.py` using
case-sensitive Pydantic settings and `.env`. Start backend commands from the
`backend` directory so the intended local `.env` is found.

Frontend configuration is compiled by Vite. Values prefixed `VITE_` are visible
to the browser.

Code defaults support local demonstration. They are not production
recommendations.

## Application, Logging, and CORS

| Variable | Code default | Note |
|---|---|---|
| `APP_NAME` | `T&TEC Weather-Based Generation Decision Support System` | FastAPI title |
| `API_V1_PREFIX` | `/api/v1` | Versioned API prefix |
| `DEBUG` | `false` | Development diagnostic toggle |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `LOG_JSON` | `true` | JSON formatter toggle |
| `CORS_ALLOWED_ORIGINS` | local 5173 origins | Comma-separated explicit origins; `*` is filtered |

## Database

| Variable | Code default | Note |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./wgdss.db` | PostgreSQL DSN supported through psycopg2 |
| `DATABASE_AUTO_CREATE` | `true` | Set false and use Alembic for managed deployment |
| `DB_ECHO` | `false` | SQL logging |
| `DB_POOL_SIZE` | `5` | Non-SQLite pool |
| `DB_MAX_OVERFLOW` | `10` | Non-SQLite pool |
| `DB_POOL_RECYCLE_SECONDS` | `1800` | Non-SQLite connection recycle |
| `SNAPSHOT_PERSISTENCE_ENABLED` | `true` | Dashboard snapshot evidence persistence |

## Weather Providers

| Variable | Code default | Note |
|---|---|---|
| `OPEN_METEO_BASE_URL` | Open-Meteo forecast URL | Primary |
| `OPEN_METEO_ARCHIVE_URL` | Open-Meteo archive URL | Historical observed weather |
| `OPEN_METEO_SINGLE_RUNS_URL` | Open-Meteo single-runs URL | Replay issued/past-only handling |
| `REPLAY_WEATHER_MODELS` | `ecmwf_ifs025,gfs_global,icon_global` | Archived model candidates |
| `REPLAY_WEATHER_RUN_AVAILABILITY_LAG_HOURS` | `6` | Leakage guard; prototype provider timing |
| `REPLAY_WEATHER_CACHE_TTL_SECONDS` | `21600` | Six-hour replay weather cache |
| `MET_NORWAY_BASE_URL` | MET Norway compact URL | Consensus source |
| `MET_NORWAY_USER_AGENT` | WGDSS contact string | Must remain identifiable |
| `WEATHER_API_BASE_URL` | WeatherAPI v1 URL | Optional fallback |
| `WEATHER_API_KEY` | empty | Secret; backend only |
| `ENABLE_WEATHERAPI_FALLBACK` | `false` | Explicit opt-in |
| `WEATHER_TIMEOUT_SECONDS` | `10` | Provider timeout |
| `WEATHER_RETRY_ATTEMPTS` | `3` | Provider attempts |
| `WEATHER_RETRY_BACKOFF_SECONDS` | `0.75` | Retry backoff |
| `WEATHER_CACHE_TTL_SECONDS` | `300` | Current/forecast cache |
| `WEATHER_CONSENSUS_TIMEOUT_SECONDS` | `12` | Per-consensus fetch timeout |
| `OPEN_METEO_DAILY_REQUEST_LIMIT` | `9000` | Process-local safety ceiling |
| `WEATHER_API_MONTHLY_REQUEST_LIMIT` | `90000` | Process-local safety ceiling |

## Storm Provider and Default Location

| Variable | Code default | Note |
|---|---|---|
| `NHC_CURRENT_STORMS_URL` | NHC `CurrentStorms.json` | Public read-only storm source |
| `NHC_STORM_TRACKING_TIMEOUT_SECONDS` | `10` | HTTP timeout |
| `NHC_STORM_TRACKING_CACHE_TTL_SECONDS` | `900` | 15-minute cache |
| `NHC_USER_AGENT` | WGDSS contact string | Outbound identifier |
| `DEFAULT_LATITUDE` | `10.5953` | Piarco representative default |
| `DEFAULT_LONGITUDE` | `-61.3372` | Piarco representative default |
| `WEATHER_SITE_ALTITUDE_METERS` | `12` | Provider query altitude |

## Weighted Geographic Weather

| Variable | Code default | Note |
|---|---|---|
| `TEMPERATURE_AGGREGATION_ENABLED` | `true` | Applies weighted aggregation to supported weather fields |
| `TEMPERATURE_AGGREGATION_MIN_WEIGHT_COVERAGE_PERCENT` | `70` | Minimum prototype coverage |
| `TEMPERATURE_AGGREGATION_POLICY_STATUS` | `PROTOTYPE_UNCONFIRMED` | Requires engineering approval |

## Calibration, Staleness, and Grid Provider

| Variable | Code default | Note |
|---|---|---|
| `CALIBRATION_DATA_ZIP_PATH` | empty | Optional calibration archive |
| `CALIBRATION_AUTO_IMPORT` | `false` | Startup import switch |
| `DATA_STALE_AFTER_SECONDS` | `5400` | General stale threshold |
| `GRID_PROVIDER` | `mock` | Only mock is normal-dashboard implemented |
| `GRID_STALE_AFTER_SECONDS` | `30` | Grid freshness threshold |
| `MODEL_FORECAST_STALE_AFTER_SECONDS` | `7200` | Forecast freshness threshold |
| `FORECAST_EXTRA_HOLIDAY_DATES` | empty | Comma-separated approved dates |

## Replay and Period Policy

| Variable | Code default | Note |
|---|---|---|
| `DEMO_REPLAY_ENABLED` | `true` | Enable June simulated-present path |
| `DEMO_REPLAY_AUTO_SEED` | `true` | Seed deterministic archive at startup |
| `DEMO_DATASET_YEAR` | `2025` | Synthetic archive year |
| `DEMO_REPLAY_MONTH` | `6` | Replay month |
| `MODEL_TRAINING_START_DATE` | `2025-10-01` | Training boundary |
| `MODEL_TRAINING_END_DATE` | `2026-05-31` | Training boundary |
| `SIMULATED_LIVE_START_DATE` | `2026-06-01` | June exclusion/live boundary |
| `SIMULATED_LIVE_END_DATE` | `2026-06-30` | June exclusion/live boundary |
| `JUNE_REPLAY_ARCHIVE_START_DATE` | `2026-06-01` | Historical date-list boundary |
| `JUNE_REPLAY_ARCHIVE_END_DATE` | `2026-06-30` | Historical date-list boundary |
| `SCADA_REPLAY_ARCHIVE_PATH` | empty | Optional historical export |
| `SCADA_HISTORICAL_WEATHER_BACKFILL` | `false` | Replay weather backfill |

## Historical SCADA Quality and Reporting Window

| Variable | Code default | Note |
|---|---|---|
| `SCADA_STRICT_QUALITY_VALUES` | `Good` | Provisional accepted values |
| `SCADA_CONDITIONAL_QUALITY_VALUES` | `Other` | Provisional conditional values |
| `SCADA_MIN_HOURLY_COVERAGE` | `0.90` | Interval-overlap quality bound |
| `SCADA_MAX_HOURLY_COVERAGE` | `1.05` | Interval-overlap quality bound |
| `SCADA_EXPECTED_REPORTING_START` | empty | Optional ISO-8601 boundary |
| `SCADA_EXPECTED_REPORTING_END` | empty | Optional ISO-8601 boundary |

## Risk Policy and Legacy Dispatch Fields

All values in this section require T&TEC approval.

| Variable | Code default |
|---|---:|
| `OPERATING_POLICY_STATUS` | `PROTOTYPE_UNCONFIRMED` |
| `CAPACITY_RISK_REQUIRED_RESERVE_MW` | `30` |
| `CAPACITY_RISK_WATCH_PROBABILITY_THRESHOLD` | `0.20` |
| `CAPACITY_RISK_PREPARE_PROBABILITY_THRESHOLD` | `0.50` |
| `CAPACITY_RISK_ADD_GENERATION_PROBABILITY_THRESHOLD` | `0.80` |
| `FAST_START_UNIT_CAPACITY_MW` | `15` |
| `FAST_START_MAX_CAPACITY_MW` | `30` |
| `FAST_START_LEAD_TIME_MINUTES` | `20` |
| `HEAVY_START_MIN_CAPACITY_MW` | `60` |
| `HEAVY_START_MAX_CAPACITY_MW` | `120` |
| `HEAVY_START_LEAD_TIME_MINUTES` | `60` |

The legacy fast/heavy fields support current risk/recommendation compatibility.
The aggregate capacity planner below is the clearer what-if configuration.

## Aggregate Capacity Planner

| Variable | Code default | Note |
|---|---|---|
| `CAPACITY_PLAN_SMALL_BLOCK_ID` | `small-fast-start` | Aggregate block identifier |
| `CAPACITY_PLAN_SMALL_BLOCK_LABEL` | `Small fast-start set` | UI label |
| `CAPACITY_PLAN_SMALL_BLOCK_CAPACITY_MW` | `15` | Unconfirmed |
| `CAPACITY_PLAN_SMALL_STARTABLE_COUNT` | `3` | Unconfirmed |
| `CAPACITY_PLAN_SMALL_STARTUP_LEAD_MINUTES` | `20` | Unconfirmed |
| `CAPACITY_PLAN_SMALL_VERIFICATION_STATUS` | `UNCONFIRMED` | Must remain visible |
| `CAPACITY_PLAN_HEAVY_BLOCKS_MW` | empty | Empty disables MW-specific heavy guidance |
| `CAPACITY_PLAN_HEAVY_STARTUP_LEAD_MINUTES` | `60` | Lead only; capacity absent |
| `CAPACITY_PLAN_HEAVY_VERIFICATION_STATUS` | `UNCONFIGURED` | Must remain visible |
| `CAPACITY_PLAN_CONTEXT_TTL_SECONDS` | `900` | In-process what-if context |
| `CAPACITY_PLAN_MAX_CONTEXTS` | `128` | In-process cache bound |

## July Static Experiment

| Variable | Code default | Note |
|---|---|---|
| `LIVE_SCADA_SNAPSHOT_PATH` | empty | Immutable CSV/ZIP package |
| `LIVE_SCADA_SESSION_ROOT` | `var/live_scada_sessions` | Ignored generated artifacts |
| `LIVE_SCADA_MODEL_ARTIFACT_PATH` | empty | Optional frozen joblib artifact |

## Frontend

| Variable | Default | Note |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Blank uses the local `/api` Vite proxy |

## Configuration Change Control

Record for every managed change:

- requester and approver;
- previous/new value;
- environment;
- reason and risk;
- effective time;
- application commit and model artifact;
- validation result;
- rollback value.

Policy, quality, period, and tag changes can alter forecasts and generation
need. They require domain review, not only application deployment approval.

