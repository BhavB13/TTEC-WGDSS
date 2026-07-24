# API and Database Reference

## HTTP Conventions

- Versioned API prefix: `/api/v1`
- Interactive OpenAPI documentation: `/docs`
- JSON request/response schemas: Pydantic models in `backend/app/schemas/`
- Current frontend base URL: `VITE_API_BASE_URL`, or same-origin `/api`
- Current frontend request timeout: 20 seconds
- API responses receive `Cache-Control: no-store`
- Requests receive/return an `X-Request-ID`

Only dashboard and storm routes have hidden backward-compatible `/api/...`
aliases. New integrations should use `/api/v1`.

No endpoint currently requires authentication. This is a production-blocking
gap, not an invitation to expose the API.

## Endpoint Inventory

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Basic application/version status |
| `GET` | `/api/v1/health` | Database, provider, quota, calibration, and grid-provider health |
| `GET` | `/api/v1/dashboard/snapshot` | Complete dashboard DTO |
| `GET` | `/api/v1/weather/current` | Current normalized/weighted weather |
| `GET` | `/api/v1/weather/forecast` | Normalized forecast periods |
| `GET` | `/api/v1/grid/status` | Current selected grid-provider status |
| `GET` | `/api/v1/recommendations` | Recommendation derived through dashboard orchestration |
| `GET` | `/api/v1/storm/tracking` | Cached NHC public storm data |
| `GET` | `/api/v1/replay/status` | Replay cursor and state |
| `POST` | `/api/v1/replay/control` | Play, pause, reset, step, or configure replay |
| `POST` | `/api/v1/capacity-plan/evaluate` | Stateless-looking, app-local advisory what-if evaluation |
| `GET` | `/api/v1/experiments/live-scada-snapshot/status` | July experiment configuration/status |
| `GET` | `/api/v1/experiments/live-scada-snapshot/sessions/latest` | Latest isolated experiment session |
| `POST` | `/api/v1/experiments/live-scada-snapshot/sessions/run` | Run configured immutable snapshot experiment |

## Dashboard Snapshot

Request:

```http
GET /api/v1/dashboard/snapshot?selected_date=2026-06-20&days=7&force_refresh=false
```

Query parameters:

| Parameter | Default | Constraints |
|---|---:|---|
| `latitude` | configured Piarco latitude | -90 to 90 |
| `longitude` | configured Piarco longitude | -180 to 180 |
| `days` | 7 | 1 to 14 |
| `force_refresh` | false | bypass applicable service caches |
| `selected_date` | active replay day | must be an available June date not after active day |

Top-level response:

```json
{
  "snapshot_id": "generated-id",
  "weather": {},
  "grid": {},
  "forecast": {"items": []},
  "probability": {},
  "recommendation": {},
  "calibration": {},
  "data_quality": {},
  "demand_forecast": {},
  "model_status": {},
  "scada_status": {},
  "replay": {},
  "capacity_plan": {},
  "time_context": {}
}
```

Some sections are optional for persisted legacy/internal snapshots, but
`DashboardService` supplies `time_context` on the public endpoint.

### Time Context

The response includes:

- selected and active dates;
- displayed timestamp;
- source and value classification;
- available date list and bounds;
- record count and completeness;
- active/previous-day indicator;
- hourly series with demand, TRA, spin, available capacity, temperature, and
  quality.

## Replay Control

Example:

```json
{
  "action": "step",
  "step_minutes": 60
}
```

Allowed actions are `play`, `pause`, `reset`, `step`, and `configure`.
`step_minutes` is constrained to 15-1440 and `speed_multiplier` to 1-86400.

## Capacity What-If

Example:

```json
{
  "snapshot_id": "<snapshot-id-from-dashboard>",
  "actions": [
    {
      "block_id": "small-fast-start",
      "count": 1,
      "start_at": null
    }
  ]
}
```

The endpoint:

- cannot communicate with SCADA;
- calculates a hypothetical post-plan profile;
- rejects missing, expired, or invalid snapshot contexts;
- uses an in-process context cache, which is not multi-worker safe;
- does not persist an operator instruction.

## July Experiment

The experiment run endpoint requires `LIVE_SCADA_SNAPSHOT_PATH`. A session
contains:

- source hash, audit summary, range, latest valid timestamp, and missing tags;
- frozen model metadata and leakage checks;
- exact weather snapshot and response hash;
- model inputs, model forecasts or persistence references;
- generation-need outputs where inputs are sufficient;
- artifact paths and warnings.

The source path returned through status is a local configuration value. Do not
expose a production filesystem layout through a public API without review.

## Error Behavior

Examples:

- `422`: invalid date, malformed source, or invalid capacity action;
- `404`: no experiment session or capacity context;
- `409`: experiment source not configured or capacity context expired;
- `503`: requested June archive is empty.

The frontend displays the API `detail` field when present.

## Database Engines

Local default:

```text
sqlite:///./wgdss.db
```

Configured PostgreSQL form:

```text
postgresql+psycopg2://<user>:<password>@<host>:<port>/<database>
```

SQLAlchemy enables connection pre-ping. PostgreSQL connections use configured
pool size, overflow, and recycle values. SQLite uses
`check_same_thread=False`.

PostgreSQL support is implemented at the driver/ORM/migration level, but no
production PostgreSQL instance or data transfer has been verified by this
handover.

## Table Inventory

| Group | Tables | Purpose |
|---|---|---|
| Weather | `weather_observations`, `forecasts` | Current/forecast weather and provider metadata |
| Grid snapshot | `grid_data`, `generation_units` | Persisted dashboard grid and demonstration unit evidence |
| Decision output | `probability_results`, `recommendations` | Snapshot risk/recommendation audit |
| Calibration | `calibration_import_runs`, `calibration_scenario_profiles`, `scada_temperature_samples` | Imported scenario curves and temperature calibration |
| Raw SCADA | `scada_archive_import_runs`, `scada_import_runs`, `scada_raw_measurements` | File/row provenance, raw intervals, hashes, quality, anomalies |
| Aligned SCADA | `scada_grid_snapshots` | Hourly overlap-weighted grid snapshots and availability |
| Forecasting | `forecast_training_rows`, `demand_forecast_results`, `scada_replay_forecast_results` | Leakage-gated features, evaluated forecasts, exact-cursor replay artifacts |
| Replay | `demo_observations`, `demo_replay_state` | Deterministic archive and persistent replay cursor |
| Analytics | `historical_analysis` | JSON-backed analysis records |
| Identity placeholder | `users` | User fields exist; no authentication/RBAC workflow uses them |

## Migration Chain

Alembic contains a single chain from initial revision `87c46bdfdad4` to current
head `4e1f2a3b5c84`.

Normal commands:

```powershell
cd backend
venv\Scripts\python.exe -m alembic current
venv\Scripts\python.exe -m alembic heads
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe -m alembic check
```

Use migrations rather than `DATABASE_AUTO_CREATE=true` for a managed
environment.

## Data Retention

No automated retention, archival, partitioning, or deletion policy is
implemented. The application can replace forecast result tables during a
supervised refresh. T&TEC must approve retention separately for:

- raw SCADA intervals and source files;
- normalized snapshots;
- weather responses;
- model inputs and results;
- risk/recommendation audit;
- user/security audit;
- experimental session files.

