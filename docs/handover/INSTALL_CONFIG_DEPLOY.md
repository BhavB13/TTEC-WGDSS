# Installation, Configuration, and Deployment

## Supported Development Path

The repository is currently validated as a Windows development/demo
application. CI uses Ubuntu, Python 3.12, and Node 22, but no Linux production
service definition is included.

Prerequisites:

- Git
- Python 3.12 recommended
- Node.js 22 LTS recommended
- npm
- PostgreSQL only when choosing the configured PostgreSQL path

## Local Installation

From a PowerShell repository root:

```powershell
cd "C:\path\to\TTEC-WGDSS"
py -3 -m venv backend\venv
backend\venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
cd frontend
npm ci
cd ..
```

Create local configuration from examples:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

Never commit populated environment files.

## Local Launch

One command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-WGDSS.ps1
```

Optional:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-WGDSS.ps1 -NoBrowser
```

Manual backend:

```powershell
cd backend
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Manual frontend in a second terminal:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

Using `python.exe -m uvicorn` avoids stale virtual-environment launcher paths.

## Environment Variables

### Application and Database

| Variable | Default in code | Operational note |
|---|---|---|
| `DATABASE_URL` | SQLite local file | Use PostgreSQL DSN for managed deployment |
| `DATABASE_AUTO_CREATE` | true | Set false and run Alembic in managed environments |
| `DB_ECHO` | false | Avoid SQL/value leakage in production logs |
| `DB_POOL_SIZE` | 5 | PostgreSQL only; size from measured workload |
| `DB_MAX_OVERFLOW` | 10 | PostgreSQL only |
| `DB_POOL_RECYCLE_SECONDS` | 1800 | PostgreSQL only |
| `DEBUG` | false | Keep false outside local debugging |
| `LOG_LEVEL` | INFO | Structured logger level |
| `LOG_JSON` | true | JSON logging toggle |
| `CORS_ALLOWED_ORIGINS` | local Vite origins | Must be explicit; wildcard is filtered out |

### Weather

| Variable | Purpose |
|---|---|
| `OPEN_METEO_BASE_URL` | Open-Meteo current/forecast endpoint |
| `OPEN_METEO_ARCHIVE_URL` | Historical observed endpoint |
| `OPEN_METEO_SINGLE_RUNS_URL` | Archived model-run endpoint |
| `REPLAY_WEATHER_MODELS` | Replay model list |
| `REPLAY_WEATHER_RUN_AVAILABILITY_LAG_HOURS` | Cutoff protection for model-run availability |
| `MET_NORWAY_BASE_URL` | Consensus endpoint |
| `MET_NORWAY_USER_AGENT` | Required identifiable client string |
| `WEATHER_API_KEY` | Optional fallback credential |
| `ENABLE_WEATHERAPI_FALLBACK` | Opt-in fallback switch |
| `WEATHER_*_SECONDS` | Timeouts, retry, cache settings |
| `OPEN_METEO_DAILY_REQUEST_LIMIT` | Process-local safety ceiling |
| `WEATHER_API_MONTHLY_REQUEST_LIMIT` | Process-local safety ceiling |
| `DEFAULT_LATITUDE/LONGITUDE` | Representative Piarco query default |
| `TEMPERATURE_AGGREGATION_*` | Weighted geographic aggregation policy |

Provider usage counters are application safeguards, not an authoritative
provider billing record or distributed quota service.

### Replay and Forecasting

| Variable | Purpose |
|---|---|
| `GRID_PROVIDER` | Currently only `mock` is normal-dashboard ready |
| `DEMO_REPLAY_ENABLED` | Enable replay mode |
| `DEMO_REPLAY_AUTO_SEED` | Seed deterministic archive at startup |
| `MODEL_TRAINING_START_DATE/END_DATE` | October-May training boundary |
| `SIMULATED_LIVE_START_DATE/END_DATE` | June inference/replay boundary |
| `JUNE_REPLAY_ARCHIVE_START_DATE/END_DATE` | Selectable June archive bounds |
| `SCADA_REPLAY_ARCHIVE_PATH` | Optional historical export source |
| `SCADA_HISTORICAL_WEATHER_BACKFILL` | Optional historical weather backfill |
| `FORECAST_EXTRA_HOLIDAY_DATES` | Approved additional `YYYY-MM-DD` dates |

### SCADA Import and Policy

| Variable | Purpose/status |
|---|---|
| `SCADA_STRICT_QUALITY_VALUES` | Provisional accepted quality list |
| `SCADA_CONDITIONAL_QUALITY_VALUES` | Provisional warning quality list |
| `SCADA_MIN/MAX_HOURLY_COVERAGE` | Alignment quality bounds |
| `SCADA_EXPECTED_REPORTING_START/END` | Optional explicit source window |
| `OPERATING_POLICY_STATUS` | Must remain unconfirmed until approved |
| `CAPACITY_RISK_*` | Prototype reserve and probability bands |
| `CAPACITY_PLAN_*` | Prototype aggregate block roster and lead times |

### July Experiment

| Variable | Purpose |
|---|---|
| `LIVE_SCADA_SNAPSHOT_PATH` | Immutable source package |
| `LIVE_SCADA_SESSION_ROOT` | Isolated generated session directory |
| `LIVE_SCADA_MODEL_ARTIFACT_PATH` | Optional approved frozen joblib artifact |

### Frontend

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | API origin for a separately hosted backend; blank uses Vite proxy |

Vite variables are compiled into browser code. Never place SCADA credentials,
database credentials, or private server details in a `VITE_*` value.

## Configuration Template

This is a template, not a production credential set:

```dotenv
DATABASE_URL=postgresql+psycopg2://<user>:<password>@<host>:<port>/<database>
DATABASE_AUTO_CREATE=false
DEBUG=false
LOG_LEVEL=INFO
LOG_JSON=true
CORS_ALLOWED_ORIGINS=https://<approved-dashboard-origin>

GRID_PROVIDER=mock
DEMO_REPLAY_ENABLED=true
DEMO_REPLAY_AUTO_SEED=true

MODEL_TRAINING_START_DATE=2025-10-01
MODEL_TRAINING_END_DATE=2026-05-31
SIMULATED_LIVE_START_DATE=2026-06-01
SIMULATED_LIVE_END_DATE=2026-06-30

ENABLE_WEATHERAPI_FALLBACK=false
WEATHER_API_KEY=

OPERATING_POLICY_STATUS=PROTOTYPE_UNCONFIRMED
CAPACITY_RISK_REQUIRED_RESERVE_MW=30
CAPACITY_PLAN_HEAVY_BLOCKS_MW=
```

## PostgreSQL Migration Procedure

This is a controlled procedure template. It has not been executed against a
production WGDSS database.

1. Freeze application writes and record deployed commit/migration revision.
2. Back up the source database.
3. Create a new PostgreSQL database using approved names, owners, storage, and
   access controls.
4. Set `DATABASE_URL` in the runtime secret/configuration mechanism.
5. Apply schema migrations:

   ```powershell
   cd backend
   $env:DATABASE_URL = "postgresql+psycopg2://<user>:<password>@<host>:<port>/<database>"
   venv\Scripts\python.exe -m alembic upgrade head
   venv\Scripts\python.exe -m alembic check
   ```

6. Transfer data with a reviewed one-time ETL/export-import procedure. No
   SQLite-to-PostgreSQL transfer utility exists in the repository.
7. Reconcile row counts, hashes, timestamps, nulls, quality, and key forecast
   artifacts table by table.
8. Run backend tests and API smoke tests against a non-production clone.
9. Perform operator acceptance before cutover.
10. Retain the source backup until the approved rollback window closes.

Do not point production code at PostgreSQL merely because migrations succeed;
data transfer, query performance, time-zone behavior, backup, and restore must
also be proven.

## Backup Templates

### PostgreSQL

Use the utility-approved secret mechanism. The following placeholders illustrate
the command shape:

```powershell
pg_dump --format=custom --file "<backup-path>\wgdss-<timestamp>.dump" `
  --host "<host>" --port "<port>" --username "<user>" "<database>"
```

Verify:

```powershell
pg_restore --list "<backup-path>\wgdss-<timestamp>.dump"
```

Restore into an isolated database first:

```powershell
createdb --host "<host>" --port "<port>" --username "<user>" "<restore-test-db>"
pg_restore --clean --if-exists --no-owner `
  --dbname "<restore-test-db>" "<backup-path>\wgdss-<timestamp>.dump"
```

Schedule, retention, encryption, off-host storage, and restore-test ownership
are not implemented and require infrastructure/security approval.

### Local SQLite

Stop backend processes before copying the database:

```powershell
Copy-Item backend\wgdss.db "<backup-path>\wgdss-local-<timestamp>.db"
```

This is for local recovery only.

## Production Deployment Status

There are no Dockerfiles, Compose files, Nginx configuration, service units,
or infrastructure-as-code assets in the current repository.

The documented target is:

```text
TLS reverse proxy/load balancer
  -> built static frontend
  -> authenticated FastAPI service
  -> PostgreSQL
  -> approved read-only OT/IT data interface
```

Before implementing that target, approve:

- host/platform, DNS, and TLS ownership;
- authentication/identity integration;
- secret storage;
- PostgreSQL service and backup location;
- logging, monitoring, alerting, and retention;
- read-only SCADA/historian network boundary;
- availability, recovery-time, and recovery-point objectives.

## Logging and Monitoring

Implemented:

- JSON/plain structured application logging;
- request ID, method, path, status, and duration;
- provider success/failure state;
- `/api/v1/health`;
- import hashes, quality, and model metadata in domain records.

Not implemented:

- centralized log shipping;
- Prometheus/OpenTelemetry metrics;
- dashboards, uptime checks, or alert routing;
- scheduled job monitoring;
- security audit events;
- backup/restore monitoring;
- multi-instance provider-health/quota coordination.

Do not treat a healthy HTTP response alone as production observability.

