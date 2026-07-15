# Current Status

Last updated: 2026-07-15

## Snapshot

WGDSS is operational as a weather/grid control-room demonstration with an
immutable 12-month hourly archive and a persistent June simulated-live replay.

The dashboard currently uses `MockGridProvider`. It is explicitly labelled
`SIMULATED` and is suitable for demonstration, training, replay, and UI
validation only. It is not live T&TEC dispatch telemetry.

With `DEMO_REPLAY_ENABLED=true` (the local demonstration default), the dashboard
instead consumes `SimulatedLiveScadaReplay`. It is also explicitly simulation
only and does not claim a live T&TEC feed.

## Implemented And Validated

- Provider-based live weather and forecast data with quality metadata.
- Dashboard snapshot API, map overlays, wind display, scenario profiles, and
  historical analytics.
- SCADA CSV import with raw-source preservation, header normalization, timestamp
  parsing, quality preservation, and duplicate-file protection.
- Hourly SCADA grid snapshots aligned by timestamp, never row number.
- Chronological forecast dataset, baseline comparison, optional
  `HistGradientBoostingRegressor`, calibrated uncertainty, and operating-risk
  probability.
- SCADA replay preflight gate requiring all five tags, Good-quality samples, and
  at least eight aligned hours before imports or training mutate the database.
- Supervised refresh command requiring 48 Good-quality snapshots by default and
  newer data before model retraining.
- Alembic migration chain checked cleanly, including legacy repair of
  `scada_grid_snapshots.missing_fields`.
- Deterministic 8,760-row 2025 SCADA/weather demonstration archive.
- June replay cursor with Play/Pause/Step/Reset, configurable interval/rate, and
  persistent progress.
- Full-day weather-informed load forecast, revealed actuals, historical hourly
  baseline, 48-hour trends, and 12-month analytics.

## Current Data Limitation

The supplied calibration archive contains Excel scenario profiles and SCADA
temperature calibration data, not raw timestamped SCADA CSV exports for all five
required tags. Consequently, no model is currently trained in the local runtime.
This is deliberate: WGDSS does not fabricate a SCADA-backed forecast or risk.

## Latest Validation

- Focused dashboard, SCADA import/snapshot/replay, forecast dataset/model, and
  refresh tests pass.
- Frontend Vitest suite passes.
- Frontend production build passes.
- `alembic check` passes after applying `alembic upgrade head`.

## Next Operational Step

Obtain a historical export containing all required SCADA tags with overlapping
timestamps, run the replay preflight/pipeline, review model metrics against the
baselines, then schedule supervised refresh outside the API process.
