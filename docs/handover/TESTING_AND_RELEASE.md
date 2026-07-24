# Testing, CI, and Release

## Test Layout

Backend tests are in `backend/tests/` and cover:

- calibration and historical imports;
- raw SCADA parsing, deduplication, anomaly flags, and snapshot aggregation;
- interval alignment/reconciliation and June irregular timestamps;
- forecast dataset leakage and horizon construction;
- baseline/ML model selection, uncertainty, calendar, and similar periods;
- supervised forecast refresh;
- June replay and exact-cursor forecasts;
- weather providers, caching, consensus, weighted aggregation, and replay
  cutoff;
- risk probability and chronological Brier backtesting;
- current-TRA capacity planning, lead times, unavailable data, and API;
- dashboard snapshot/persistence/health;
- July static snapshot provider, frozen artifact guard, and session isolation.

Frontend tests cover the dashboard, demand/replay/scenario charts, and fixtures.
This is useful coverage, but it is not a substitute for full browser end-to-end,
accessibility, security, performance, or production integration tests.

## Local Validation

Backend:

```powershell
cd backend
venv\Scripts\python.exe -m pytest -q
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe -m alembic check
```

Frontend:

```powershell
cd frontend
npm test
npm run build
```

Optional runtime smoke:

```powershell
Invoke-RestMethod http://localhost:8000/
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:8000/api/v1/dashboard/snapshot
```

Do not use a successful build as evidence that weather providers, data
alignment, risk, or responsive rendering are correct.

### Handover Validation Result

Run from the inspected worktree on 2026-07-23:

- Backend: `179 passed in 100.23s`
- Alembic: `No new upgrade operations detected`
- Frontend: `4` test files and `12` tests passed
- Frontend: TypeScript check and Vite production build passed

These commands validate current automated coverage. They did not test
PostgreSQL, external provider availability, a production deployment, a live
SCADA connector, or a frozen July model artifact.

## Continuous Integration

`.github/workflows/ci.yml` currently:

- runs on pull requests;
- runs on pushes to `main` and `codex/**`;
- tests Python 3.12 backend dependencies;
- runs backend pytest;
- upgrades and checks a clean SQLite migration database;
- installs Node 22 dependencies with `npm ci`;
- runs frontend tests and production build.

The current experimental branch name does not match `codex/**`, so a push to
that branch alone is not covered by the configured push trigger. A pull request
will run CI.

CI gaps:

- no PostgreSQL service/migration/integration job;
- no browser end-to-end or visual regression job;
- no coverage threshold;
- no lint/format/type job separate from frontend build;
- no dependency, secret, SAST, container, or license scanning;
- no model-data validation or artifact-signature job;
- no deployment or post-deployment smoke stage.

## Model Validation Gate

A model release must record:

- source dataset hashes and reporting ranges;
- accepted/excluded quality counts;
- observation, availability, issue, and target time policy;
- training period and explicit June exclusion;
- feature profile and exact ordered feature list;
- preprocessing fit boundaries;
- candidate and selected model per horizon;
- chronological walk-forward and holdout metrics;
- baseline metrics and minimum improvement decision;
- residual/interval calibration and coverage;
- peak/ramp/regime errors;
- model code commit and dependency lock;
- serialized artifact hash, when artifact packaging is implemented;
- reviewer and approval status.

Reject release when:

- feature or target rows cross the training cutoff;
- future actual weather/TRA/TA/spin/demand enters features;
- random splitting replaces chronological validation;
- ML does not pass its baseline gate;
- uncertainty is absent or uncalibrated;
- data/quality/units are unapproved;
- no later actuals exist to evaluate the claimed use case;
- the model cannot be reproduced from a frozen artifact and metadata.

## July Experiment Gate

The experiment must verify:

- source hash is unchanged during reading;
- exact latest valid common boundary;
- timestamp normalization to Trinidad time;
- duplicate, malformed, future, impossible, and missing-variable reports;
- hourly overlap weighting and source coverage;
- weather begins after the boundary;
- October-May artifact training metadata;
- snapshot was not used for training;
- preprocessing was not refit;
- session artifacts remain outside normal tables.

Without a ready frozen artifact and later actuals, the experiment demonstrates
plumbing, not forecast accuracy.

## Release Checklist

1. Working tree and intended branch are confirmed.
2. Required status and handover documents are current.
3. Backend tests pass.
4. Alembic upgrade/check pass on an empty database.
5. Alembic upgrade/check pass on a copy of the target database.
6. Frontend tests/build pass.
7. API schema changes are reviewed for compatibility.
8. Dashboard is visually checked at 1366x768 and the target control-room
   resolution.
9. Weather/map degradation is tested.
10. Missing/stale SCADA and model behavior fails safely.
11. Model and policy approval records are attached.
12. Backup and restore are tested.
13. Security and deployment approval are attached.
14. Commit, migration head, environment, and artifact hashes are recorded.
15. Rollback target and owner are confirmed.

## Rollback Testing

Test rollback against a clone:

- previous application revision with its matching database state;
- restore from the selected backup;
- API health and snapshot;
- replay/source classification;
- model version and forecast results;
- frontend smoke and operator acceptance.

Do not assume source-code rollback can read a newer schema. Do not downgrade a
production database without reviewing each migration and preserving a backup.

## Remaining Validation Needed

- PostgreSQL behavior and performance;
- twelve or more months of approved data;
- genuine archived forecast issuance data;
- model drift and probability calibration over later actuals;
- live read-only connector failure/recovery;
- multi-worker state coordination;
- authentication/RBAC/TLS;
- load/performance and long-running reliability;
- browser compatibility, accessibility, and security testing;
- operator UAT with approved policy and terminology.
