# Live SCADA Snapshot Experiment

## Purpose

This branch tests WGDSS parsing and inference plumbing against one immutable
Excel/OSI trend-export package. It is read-only decision support. It is not a
live SCADA connection and has no command or dispatch capability.

The stable June replay is preserved at tag `pre-scada-baseline`. Experimental
work is isolated on branch `experiment/live-scada-snapshot`.

## Architecture

- `ExcelSnapshotScadaProvider` implements the existing `GridProvider`
  architecture and exposes a partial snapshot when utility variables are
  missing.
- Timestamps are interpreted in `America/Port_of_Spain`.
- Interval exports use overlap-weighted hourly aggregation. Point samples use
  their effective interval to the following sample.
- The latest experiment boundary is the latest timestamp shared by demand,
  temperature, corrected spin, and TRA.
- Raw and cleaned audit records are saved separately under
  `backend/var/live_scada_sessions/<session-id>/`.
- No experiment row is written to the normal WGDSS database.
- Current/forecast weather is captured once per session. Forecast targets must
  be strictly after the SCADA boundary.
- `FrozenSnapshotModelService` accepts only a serialized, previously fitted
  artifact with October-May training metadata. It calls `predict` only.

## Configuration

```env
LIVE_SCADA_SNAPSHOT_PATH=C:\Users\Bhave\Downloads\20260723.zip
LIVE_SCADA_SESSION_ROOT=var/live_scada_sessions
LIVE_SCADA_MODEL_ARTIFACT_PATH=
```

Run a session through the `SCADA Test` tab, `POST
/api/v1/experiments/live-scada-snapshot/sessions/run`, or:

```powershell
cd backend
.\venv\Scripts\python.exe scripts\run_live_scada_snapshot.py C:\Users\Bhave\Downloads\20260723.zip
```

## Frozen Artifact Contract

The optional joblib artifact must be a dictionary with schema
`wgdss-frozen-demand-model-v1`, October-May training dates, feature names,
training fill values, and fitted horizon pipelines. It must explicitly state
that the snapshot was not used in training.

The current repository does not include a fitted serialized model artifact.
Persisted model metadata and prior predictions are not sufficient to reproduce
inference. The experiment therefore fails closed and displays a clearly marked
persistence reference. It does not retrain or refit preprocessing.

## Items Requiring T&TEC / OSI Confirmation

- Exact semantics and engineering units for all tags.
- Validation bounds and accepted quality mappings.
- `GSYS SYSTEM_ONLN_TOTAL` interpretation as TRA.
- Availability/TA tag and source; it is absent from the supplied package.
- Approved frozen model artifact and its signed release process.
- Operational freshness limits and reserve policy.
