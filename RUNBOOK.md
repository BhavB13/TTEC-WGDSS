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

## Before Editing

1. Run `git status --short` and preserve unrelated user changes.
2. Read `CURRENT_STATUS.md` and `NEXT_TASKS.md`.
3. If touching SCADA, forecasting, or probability logic, read `docs/SCADA_WEATHER_MATH_UPGRADE_PLAN.md`.
4. Keep mock/dashboard compatibility unless the task explicitly changes the contract.

## Operational Notes

- Backend dependencies already include `numpy`, `pandas`, `scikit-learn`, and `joblib`.
- The current active work appears centered on historical SCADA CSV ingestion and math-backed forecast/risk logic.
- Use the smallest relevant test slice and record any skipped verification in the handoff.
