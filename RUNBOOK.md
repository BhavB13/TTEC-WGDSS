# Runbook

## Startup

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
resamples by interval overlap, preserves quality, builds 1h/2h/6h datasets,
compares chronological baselines and ML candidates, and stores a forecast for
the exact current June replay cursor. `Other` remains conditionally usable and
never becomes `Good`.

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

## Before Editing

1. Run `git status --short` and preserve unrelated user changes.
2. Read `CURRENT_STATUS.md` and `NEXT_TASKS.md`.
3. If touching SCADA, forecasting, or probability logic, read `docs/SCADA_WEATHER_MATH_UPGRADE_PLAN.md`.
4. Keep mock/dashboard compatibility unless the task explicitly changes the contract.

## Operational Notes

- Backend dependencies already include `numpy`, `pandas`, `scikit-learn`, and `joblib`.
- The historical SCADA math pipeline is validated for replay. The active grid
  provider remains `MockGridProvider`, so dashboard grid data is simulated and
  not valid for live dispatch.
- Use the smallest relevant test slice and record any skipped verification in the handoff.
