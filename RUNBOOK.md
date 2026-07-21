# Runbook

## Startup

One-command local launch from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Bhave\Downloads\TTEC-WGDSS\scripts\Start-WGDSS.ps1"

Alternatively, double-click `START_WGDSS.cmd`. See
`docs/LAUNCH_AND_DEPLOYMENT.md` for setup behavior and production-deployment
boundaries.

Manual startup:

Backend:

```powershell
cd backend
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

UI: `http://localhost:5173`
API docs: `http://localhost:8000/docs`

## Core Validation

Backend:

```powershell
cd backend
venv\Scripts\python.exe -m pytest -q
venv\Scripts\python.exe -m alembic check
```

Frontend:

```powershell
cd frontend
npm test
npm run build
```

## Historical SCADA Replay

Historical exports are a prototype/replay input, not a live SCADA feed. Supply
one filename-independent ZIP archive or CSV files containing the five required
tags and overlapping timestamps. For the supplied June archive:

```powershell
cd backend
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe scripts\run_scada_replay_pipeline.py `
  --backfill-weather C:\Users\<user>\Downloads\junescadadata.zip
```

When the export owner supplies an explicit reporting window, pass its ISO-8601
boundaries so spillover records are retained but flagged:

```powershell
venv\Scripts\python.exe scripts\run_scada_replay_pipeline.py `
  --reporting-start "<approved-window-start>" `
  --reporting-end "<approved-window-end>" `
  C:\path\to\scada-export.zip
```

WGDSS never infers those boundaries from a filename or month label.

For separate CSV exports:

```powershell
cd backend
venv\Scripts\python.exe scripts\run_scada_replay_pipeline.py `
  C:\exports\demand.csv C:\exports\ambient-temperature.csv `
  C:\exports\spinning-reserve.csv C:\exports\available-capacity.csv `
  C:\exports\online-capacity.csv
```

The pipeline performs a preflight before database mutation. It rejects missing
required tags or fewer than eight interval-aligned usable hourly samples. It
normalizes two-digit timestamps and tag whitespace, deduplicates CSV content,
resamples by duration-weighted interval overlap, preserves quality, builds
direct 1h-through-6h datasets,
compares chronological baselines and ML candidates, and stores a forecast for
the exact current June replay cursor. `Other` remains conditionally usable and
never becomes `Good`.

The pipeline also reconciles persisted demand snapshots against the preserved
raw intervals. Its summary reports the selected alignment method, candidate
chronological errors, matched hours, and mismatches. A mismatch means the
derived hourly table must be reviewed before it is used for model validation.

Timestamp meanings are intentionally separate:

- `timestamp`: civil-hour bucket used for historical display and model targets.
- `available_at`: exact end of the latest source interval contributing to that
  bucket.
- forecast issue time: first model clock at which `available_at` has passed.

Historical charts may show post-event actuals at their observation hour. Model
features and replay forecasts must only use rows whose `available_at` is at or
before the simulated issue time.

`--backfill-weather` makes one free Open-Meteo Archive API request for the SCADA
date range and stores observed feature-time weather. It does not fabricate
issued historical forecasts. When no archived forecast run is available, the
dataset builds a past-observation hourly weather baseline and marks its quality.

Re-run the pipeline after the simulated replay cursor changes if direct
per-horizon artifacts are required at that exact cursor. If none matches, the
dashboard uses its cutoff-safe replay forecast and never substitutes a model
trained through a later source row.

## Supervised Forecast Refresh

Run this from an operator-approved external scheduler, never from the API
process:

```powershell
cd backend
venv\Scripts\python.exe scripts\refresh_demand_forecast.py
```

The command requires 48 Good-quality SCADA snapshots by default and skips when
no newer snapshot exists. A skip is a safe result, not an error. Use `--force`
only after deliberate review.

The full candidate tournament is intentionally an offline/scheduled operation;
it must never run inside a dashboard request. It performs expanding-window
selection for every 1-6 hour horizon and may take several minutes on a laptop.
The dashboard continues to use the last persisted, validated artifact while it
runs.

After new SCADA snapshots have passed ingestion/alignment validation, retrain
from `backend` with:

```powershell
venv\Scripts\python.exe scripts\build_forecast_training_rows.py
venv\Scripts\python.exe scripts\train_demand_forecast_model.py
```

Review the printed MAE, RMSE, MAPE, peak error, selected baseline, and model
mode for all six horizons. ML is activated only when its newest chronological
holdout MAE and RMSE are both at least 2% better than the selected baseline.
Otherwise `BASELINE_ACTIVE` is the expected safe outcome. Also inspect
`candidate_metrics.temperature_analysis`, `candidate_metrics.input_quality`,
and `candidate_metrics.active.interval_coverage` in model status before using a
new artifact for replay demonstrations.

The current training history is historical OSI export data from October 2025
through June 2026. It supports calibration and replay only. Do not label the
result as a live T&TEC forecast or trigger any control action from it.

Variable or specially declared public holidays can be supplied in `backend/.env`
as a comma-separated list of `YYYY-MM-DD` values using
`FORECAST_EXTRA_HOLIDAY_DATES`. Have operations engineering approve those dates
before retraining.

## Before Editing

1. Run `git status --short` and preserve unrelated user changes.
2. Read `CURRENT_STATUS.md` and `NEXT_TASKS.md`.
3. If touching SCADA, forecasting, or probability logic, read
   `docs/SCADA_OSI_CONTEXT.md` first, then
   `docs/SCADA_WEATHER_MATH_UPGRADE_PLAN.md`.
4. Keep mock/dashboard compatibility unless the task explicitly changes the contract.

## Operational Notes

- Backend dependencies already include `numpy`, `pandas`, `scikit-learn`, and `joblib`.
- The historical SCADA math pipeline is validated for replay. The active grid
  provider remains `MockGridProvider`, so dashboard grid data is simulated and
  not valid for live dispatch.
- Use the smallest relevant test slice and record any skipped verification in the handoff.
