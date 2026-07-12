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
CSV files containing the five required tags and overlapping timestamps:

```powershell
cd backend
venv\Scripts\python.exe scripts\run_scada_replay_pipeline.py `
  C:\exports\demand.csv C:\exports\ambient-temperature.csv `
  C:\exports\spinning-reserve.csv C:\exports\available-capacity.csv `
  C:\exports\online-capacity.csv
```

The pipeline performs a preflight before database mutation. It rejects missing
required tags, missing Good-quality samples, or fewer than eight aligned hourly
samples. Review its baseline/ML metrics and risk-readiness output before using
the resulting model status in an operational discussion.

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
