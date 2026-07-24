# Operations and Administration Runbook

## Start-of-Shift Operator Check

1. Open the dashboard and verify the mode label.
2. Confirm **simulated**, **replay**, **archived**, or **experimental** source
   classification. Do not infer live SCADA from current-looking timestamps.
3. Check the displayed timestamp, source observation timestamp, and freshness.
4. Open `http://localhost:8000/api/v1/health`.
5. Confirm database status and review weather/grid degradation.
6. Confirm current demand, TRA, TA, and corrected System Spin are separate.
7. Review the demand forecast model name, issue time, uncertainty, and data
   cutoff.
8. Review generation need and the highest-risk time.
9. Treat all guidance as advisory and verify any action independently through
   approved control-room systems.

## Replay Controls

The active June replay supports:

- Play/Pause
- Step
- Reset
- Step-size configuration
- Playback-rate configuration

The cursor is persisted in `demo_replay_state`. Restarting the API does not
guarantee a reset.

API example:

```powershell
$body = @{
  action = "step"
  step_minutes = 60
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/replay/control `
  -ContentType "application/json" `
  -Body $body
```

## Previous-Day Navigation

Use the day control above the workspaces:

- previous/next buttons move through available dates;
- the date input selects one available June day;
- reset returns to the active replay day.

The selected day persists between tabs and browser reloads. A previous day is
historical replay, not present telemetry. If incomplete, the backend returns a
notice and completeness value instead of filling missing observations.

## Live Weather Test

The Weather workspace can fetch current provider weather separately from the
June replay. This is a display/test feature:

- grid values remain simulated/replay;
- risk does not become live SCADA risk;
- current provider time and replay time must remain visibly distinct.

## Capacity Guidance

The Risk workspace shows no-action generation need with current TRA held. The
Guidance workspace shows a separate hypothetical plan.

Before using a suggestion:

- confirm the current TRA timestamp and quality;
- confirm the capacity block is configured and approved;
- confirm startup availability outside WGDSS;
- review interim risk before expected online time;
- do not count a proposed block as online until SCADA reports it.

The current small-block MW and policy are unconfirmed. Heavy MW-specific
guidance is disabled unless blocks are configured.

## Administrator: Validate the Application

```powershell
cd backend
venv\Scripts\python.exe -m pytest -q
venv\Scripts\python.exe -m alembic check

cd ..\frontend
npm test
npm run build
```

## Administrator: Import Historical SCADA

Historical exports are replay/calibration inputs, not a live feed.

```powershell
cd backend
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe scripts\run_scada_replay_pipeline.py `
  --backfill-weather "C:\path\to\approved-export.zip"
```

With an approved reporting window:

```powershell
venv\Scripts\python.exe scripts\run_scada_replay_pipeline.py `
  --reporting-start "<ISO-8601-start>" `
  --reporting-end "<ISO-8601-end>" `
  "C:\path\to\approved-export.zip"
```

The pipeline preflights tags, timestamps, quality, coverage, and aligned hours
before database mutation. Review its validation output and imported run records.

## Administrator: Forecast Dataset and Model

Build rows:

```powershell
cd backend
venv\Scripts\python.exe scripts\build_forecast_training_rows.py
```

Train/evaluate and store forecast results:

```powershell
venv\Scripts\python.exe scripts\train_demand_forecast_model.py
```

Supervised freshness-aware refresh:

```powershell
venv\Scripts\python.exe scripts\refresh_demand_forecast.py
```

The refresh exits without training when required good-quality data is missing
or no newer snapshot exists. It is not an in-process scheduler.

Before accepting results:

- verify training ended by May 31, 2026;
- verify June was excluded from feature and target training timestamps;
- compare every horizon against the selected chronological baseline;
- inspect uncertainty coverage, outliers, missing values, and quality;
- record reviewer/approval outside the application until a model registry is
  implemented.

## Administrator: Run July Snapshot Experiment

Configuration:

```dotenv
LIVE_SCADA_SNAPSHOT_PATH=C:\path\to\snapshot.zip
LIVE_SCADA_SESSION_ROOT=var/live_scada_sessions
LIVE_SCADA_MODEL_ARTIFACT_PATH=
```

Run:

```powershell
cd backend
venv\Scripts\python.exe scripts\run_live_scada_snapshot.py `
  "C:\path\to\snapshot.zip"
```

Review:

- source hash before/after read;
- available range and common boundary;
- malformed, duplicate, future, impossible, and missing-variable counts;
- raw and normalized quality;
- weather response hash;
- model status;
- generated `TEST_REPORT`.

Do not copy experiment rows into normal June tables.

## Troubleshooting

### Dashboard does not load

1. Check `http://localhost:8000/`.
2. Check `http://localhost:8000/api/v1/health`.
3. Check `http://localhost:5173`.
4. Inspect the backend and frontend terminal errors.
5. Confirm ports 8000/5173 are not occupied by an unrelated process.
6. Confirm the frontend proxy or `VITE_API_BASE_URL`.
7. Run backend tests and frontend build.

### Virtual-environment launcher error

Use:

```powershell
backend\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

If `python.exe` itself points to a removed environment, recreate `backend\venv`
and reinstall requirements.

### Database schema error

```powershell
cd backend
venv\Scripts\python.exe -m alembic current
venv\Scripts\python.exe -m alembic heads
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe -m alembic check
```

Back up before a corrective migration. Do not delete the database as a routine
schema fix.

### Weather is unavailable or degraded

- inspect `/api/v1/health`;
- verify internet access and provider URLs;
- verify MET Norway user agent;
- check request limits and timeouts;
- verify weighted-point coverage;
- do not replace missing weather with unlabelled mock values.

### Map tiles are missing

- verify browser network access to NASA GIBS/OpenStreetMap;
- disable individual Leaflet overlays to isolate the source;
- remember that map imagery and backend forecast weather are separate paths;
- external tile failure must not change grid/risk calculations.

### SCADA values disagree with the source

- compare source interval `Avg Value`, start/end, and quality;
- use interval-overlap hourly alignment, not row number or exact-hour lookup;
- inspect `scada_archive_import_runs.validation_report`;
- run alignment tests and reconcile stored snapshots;
- verify observation time is not being replaced with availability/issue time.

### Forecast is missing

- verify exact cursor match for replay artifacts;
- verify sufficient leakage-safe training rows;
- inspect model status/fallback reason;
- confirm weather forecast timestamps are available by issue time;
- confirm the July experiment has a valid frozen artifact if using SCADA Test.

### Generation need is unavailable

- confirm current TRA exists, is finite, fresh, and accepted quality;
- confirm forecast demand and uncertainty exist;
- confirm risk policy is configured;
- do not substitute TA, corrected spin, synthetic unit output, or future TRA.

## Recovery

### Local application

1. Stop backend/frontend.
2. Record current commit and Alembic revision.
3. Preserve logs, source imports, and the database.
4. Restore a verified local database backup if data corruption is confirmed.
5. Check out the reviewed application revision.
6. Recreate dependencies if needed.
7. Apply migrations.
8. Run tests and smoke checks before reopening.

### PostgreSQL target

Production recovery is not yet implemented. The approved procedure must cover:

- incident declaration and owner;
- write freeze;
- point-in-time or dump restore into an isolated database;
- schema/version verification;
- row-count/hash and latest-snapshot reconciliation;
- application smoke and operator acceptance;
- controlled cutover and audit record.

## Rollback

The stable pre-experiment baseline is tagged `pre-scada-baseline`. Confirm the
tag and target commit in Git before use; never assume a tag contains matching
database downgrade logic.

Preferred rollback:

1. Preserve current data and evidence.
2. Restore the database backup matching the previous application revision.
3. deploy/check out the previous reviewed commit or artifact;
4. run migrations only according to the reviewed rollback procedure;
5. run test/smoke/operator checks.

Alembic downgrade is not automatically safer than restore. Use it only after
reviewing the specific migration and testing on a copy.

