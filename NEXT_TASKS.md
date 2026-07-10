# Next Tasks

## Recommended Order

1. Review the current SCADA and forecasting working-tree changes for coherence across models, migrations, services, scripts, and tests.
2. Run targeted backend validation for the in-flight work:
   - `backend\\venv\\Scripts\\python.exe -m pytest -q`
   - `backend\\venv\\Scripts\\python.exe -m alembic check`
3. Confirm the modified files still align with `docs/SCADA_WEATHER_MATH_UPGRADE_PLAN.md`, especially around:
   - timestamp-based alignment
   - no future leakage
   - baseline-first forecasting
   - backward-compatible dashboard integration
4. Record the validated state and remaining gaps back into `CURRENT_STATUS.md`.
5. Only after backend validation is clean, consider frontend or snapshot-surface changes for forecast/model visibility.

## Good Nightly Slices

- Review one migration or one backend service cluster at a time
- Add or tighten tests around SCADA import, snapshot building, and dataset leakage boundaries
- Update docs after validation confirms the actual implementation

## Avoid Early

- Large frontend changes before the backend contract is stable
- Reverting or rewriting existing uncommitted work without human direction
- Deployments or external environment changes during overnight automation
