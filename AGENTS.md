# WGDSS Agent Notes

## First Reads

Read these before making changes:

1. `CURRENT_STATUS.md`
2. `NEXT_TASKS.md`
3. `RUNBOOK.md`
4. `docs/OperationsGuide.md`
5. `docs/SCADA_WEATHER_MATH_UPGRADE_PLAN.md` when touching the new SCADA or forecasting work

## Working Rules

- The repo may contain uncommitted user work. Do not revert or reorganize existing changes unless explicitly asked.
- Prefer small, verifiable slices over broad backend and frontend changes in one pass.
- Keep the current dashboard behavior stable unless the task explicitly includes frontend or snapshot-contract changes.
- Treat the SCADA and demand-forecasting work as the active area of change. Preserve backward compatibility where practical.

## Repo Layout

- `backend/`: FastAPI app, Alembic migrations, scripts, and tests
- `frontend/`: React/Vite dashboard
- `docs/`: operational and architecture references

## Validation

- Backend: `backend\\venv\\Scripts\\python.exe -m pytest -q`
- Alembic: `backend\\venv\\Scripts\\python.exe -m alembic check`
- Frontend tests: `npm test` from `frontend`
- Frontend build: `npm run build` from `frontend`

Run the smallest relevant validation for the files you changed, and note anything you did not run in the handoff.
