# Frozen Model and Intermittent Live-Data Implementation Plan

## Objective

Make one leakage-safe WGDSS inference path work consistently with:

1. June historical replay.
2. Newly imported immutable SCADA exports.
3. Intermittent near-live file drops.
4. A future approved read-only historian provider.

The source may change, but timestamp alignment, feature construction, model
loading, forecasting, uncertainty, generation-need calculations, provenance,
and fail-safe behavior must remain the same.

WGDSS remains read-only decision support. This work does not add SCADA commands,
invent an AspenTech OSI endpoint, or approve utility policy.

## Phase 1 - Frozen Model Artifact

### Goal

Export the selected October-May models and fitted preprocessing state as a
reproducible, inference-only artifact.

### Work

- Package one fitted estimator per direct 1h-6h horizon.
- Store the exact ordered features, fill values, clipping bounds, temperature
  profile, uncertainty calibration, model selection evidence, dataset period,
  source hashes where available, code/model version, and schema version.
- Calculate and verify an artifact SHA-256.
- Refuse artifacts whose training period enters June or whose metadata says a
  new snapshot was used for training.
- Keep the current baseline gate: ML is active only when it beats the
  chronological baseline.

### Acceptance

- Loading the artifact reproduces the stored forecast without calling `fit`,
  `partial_fit`, or `fit_transform`.
- Artifact schema, feature order, training cutoff, and hash are tested.

## Phase 2 - Unified As-Of Feature Builder

### Goal

Build model inputs exactly as they would have existed at a requested issue
time.

### Work

- Reuse the canonical forecast dataset feature calculations.
- Require interval completion/availability at or before the issue time.
- Separate observation, available, issue, and target timestamps.
- Attach observed weather through the issue boundary and only issued/past-only
  forecast weather after it.
- Return explicit missing/stale/quality diagnostics.

### Acceptance

- Identical source state and issue time produce identical ordered features in
  replay, import, and near-live modes.
- Future rows never alter earlier inputs.

## Phase 3 - Repeatable Imported-Data Provider

### Goal

Turn immutable CSV/ZIP imports into a repeatable operational batch source
without mixing them into mock or experiment data.

### Work

- Import unseen source hashes only.
- Preserve raw records, source path/name, quality, interval metadata, anomaly
  flags, and import run status.
- Normalize and align with duration-weighted overlap.
- Maintain an incremental high-water mark for the latest complete snapshot.
- Reject duplicate, stale, future, incomplete, or contradictory updates
  according to explicit policy.

### Acceptance

- Reimporting the same file creates no duplicate measurements, snapshots, or
  forecasts.
- A newer complete interval advances the watermark exactly once.

## Phase 4 - Intermittent Near-Live Batch Worker

### Goal

Support approved periodic file exports without presenting them as a continuous
SCADA stream.

### Work

- Add an external command that scans a configured directory.
- Process files in stable order after they stop changing.
- Import unseen hashes and run inference only when the complete-data watermark
  advances.
- Persist job/run status and return a machine-readable summary.
- Keep this worker outside FastAPI request handling.

### Acceptance

- No new file means no new forecast issue.
- Partial/changing files are deferred.
- Mode is labelled `BATCH_SCADA_EXPORT`, never `LIVE_SCADA`.

## Phase 5 - Forecast Orchestrator

### Goal

Produce one auditable forecast snapshot after each valid data advance.

### Work

1. Resolve latest complete grid boundary.
2. Resolve weather available at that boundary.
3. Build direct +1h through +6h inference rows.
4. Load the frozen artifact once.
5. Generate predictions and uncertainty.
6. Hold current valid TRA for no-action risk.
7. Calculate generation need and optional hypothetical plan.
8. Persist source/model/weather/probability provenance as one issue.

### Acceptance

- All returned values share one issue time and source boundary.
- Missing model, TRA, weather, or quality fails explicitly.
- A previous successful result may be shown only with an age/stale warning.

## Phase 6 - Frozen June Replay

### Goal

Make June replay a true simulation of production inference.

### Work

- Stop fitting model parameters on revealed June data.
- Load the same frozen October-May artifact used for imports.
- Feed only measurements available at the replay cursor.
- Keep later June observations hidden until reveal.
- Retain later actuals only for post-forecast evaluation.
- Keep the full-day statistical profile separately labelled where the frozen
  artifact covers only 1h-6h.

### Acceptance

- Moving the replay cursor does not mutate the model artifact.
- June never enters training, preprocessing fit, model selection, or tuning.
- Replay and imported-data inference match for identical source inputs.

## Phase 7 - API and Dashboard Provenance

### Goal

Make source, issue time, freshness, model, and forecast boundary unmistakable.

### Work

- Return data mode, source provider, source observation/availability time,
  latest complete timestamp, forecast issue time, model/artifact identifiers,
  training cutoff, age, and status.
- Support `HISTORICAL_REPLAY`, `BATCH_SCADA_EXPORT`,
  `EXPERIMENTAL_SNAPSHOT`, `LIVE_READ_ONLY`, and `MOCK`.
- Show observed, current-boundary, and forecast sections distinctly.
- Keep generated plans advisory and manual.

### Acceptance

- Operators can identify where observed data ends and forecast data begins.
- No batch, replay, experiment, or mock source is labelled live.

## Phase 8 - Future Historian Boundary

### Goal

Prepare a fail-closed provider interface for an approved read-only historian
without inventing its transport.

### Work

- Define provider capabilities for latest values, ranges, health, quality, and
  watermark.
- Add a configuration-disabled `HistorianGridProvider` boundary.
- Require approved endpoint, authentication, certificates, tag mapping, units,
  quality policy, network zone, and stale threshold before enabling it.
- Reuse Phases 2, 5, and 7 unchanged.

### Acceptance

- Selecting historian mode without approved configuration fails closed.
- No write, command, acknowledgment, or control method exists.

## Validation Intervals

Run focused validation after each phase:

| Boundary | Minimum validation |
|---|---|
| Phase 1 | Artifact export/load/reproduction/leakage tests |
| Phase 2 | As-of timestamp, feature-order, weather-boundary tests |
| Phases 3-4 | Import idempotency, watermark, partial-file, batch-job tests |
| Phases 5-6 | End-to-end forecast invariants and June no-refit tests |
| Phases 7-8 | API/frontend source labels and fail-closed provider tests |
| Final | Full backend suite, Alembic check, frontend tests/build, runtime smoke |

## Production Gates

The following remain external approvals:

- official T&TEC tag definitions and engineering units;
- accepted OSI quality meanings;
- approved reserve and generation-block policy;
- approved frozen model release;
- approved historian transport and OT/IT boundary;
- authentication, TLS, secrets, PostgreSQL, monitoring, backup, and operator
  acceptance.

## Implementation Status

Implemented on `experiment/live-scada-snapshot`:

- Phase 1: v2 frozen artifact export/load with exact fitted estimator, scaler,
  clipping/fill/temperature transform, Similar Periods reference history,
  calibration bias, uncertainty, selection evidence, cutoff guard, and hash.
- Phase 2: shared cutoff-safe as-of feature service with availability/weather
  issue checks and deterministic feature fingerprint.
- Phase 3: existing hash-idempotent raw importer and duration-weighted snapshot
  path retained as the single import foundation.
- Phase 4: stable-file batch worker, persisted watermark/run state, duplicate
  suppression, and issue-on-advance callback.
- Phase 5: one issue-time orchestrator anchoring generation need to accepted
  current TRA and frozen forecast uncertainty.
- Phase 6: June direct horizons use the frozen release; the full-day display
  curve is explicitly a statistical replay profile and cannot fit ML on June.
- Phase 7: dashboard snapshot exposes source, observation/availability/issue
  times, model/artifact, training cutoff, mode, status, and advisory-only flag.
- Phase 8: fail-closed historian provider boundary with no write or control
  methods and no invented transport.

The generated `.joblib` file is not source control content. Release/deployment
must generate or supply the reviewed artifact and verify its printed SHA-256.
