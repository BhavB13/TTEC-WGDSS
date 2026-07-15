# Current Status

Last updated: 2026-07-15

## Snapshot

WGDSS is operational as a weather/grid control-room demonstration with an
immutable synthetic archive plus an optional historical June SCADA overlay.

The dashboard currently uses `MockGridProvider`. It is explicitly labelled
`SIMULATED` and is suitable for demonstration, training, replay, and UI
validation only. It is not live T&TEC dispatch telemetry.

With `DEMO_REPLAY_ENABLED=true` (the local demonstration default), the dashboard
consumes a persistent June replay. When the five-tag historical archive has been
imported, the current June hour is sourced from that archive and labelled
`HistoricalScadaSimulatedReplay`; otherwise it uses the deterministic synthetic
archive. Neither path is a live T&TEC feed.

## Implemented And Validated

- Provider-based live weather and forecast data with quality metadata.
- Dashboard snapshot API, map overlays, wind display, scenario profiles, and
  historical analytics.
- SCADA CSV import with raw-source preservation, header normalization, timestamp
  parsing, quality preservation, and duplicate-file protection.
- Hourly SCADA grid snapshots aligned by timestamp, never row number.
- Leakage-safe direct 1h, 2h, and 6h forecast rows with demand lags, rolling
  trends, SCADA temperature, observed weather, and issued-or-past-only weather
  outlook features.
- Per-horizon comparison of persistence/time-series baselines, Ridge,
  `HistGradientBoostingRegressor`, and `RandomForestRegressor` using nested
  expanding-window validation and an untouched chronological holdout.
- Exact-cursor replay forecast artifacts with calibrated uncertainty, model
  version, candidate metrics, feature profile, and prototype/validated status.
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
  baseline, 48-hour trends, and 12-month analytics. Persisted 1h/2h/6h artifacts
  replace the corresponding chart points only when their source cursor matches
  exactly; mismatched or future artifacts are ignored.
- Three-source, per-field hourly weather consensus with timestamp synchronization
  and explicit degradation when any source is unavailable.
- Current-clock June alignment with real-time automatic playback and manual
  accelerated controls.
- Operating-risk probability based on the full valid forecast profile, TA, TRA,
  Spin, uncertainty, reserve requirement, weather effect, and startup timing.
  Dispatch distinguishes one or two 15 MW fast-start sets from a 60-120 MW
  heavy set and reports insufficient startable capacity explicitly.
- Registry-based historical imports with schema mapping, validation, SHA-256
  deduplication, and documented recalibration/retraining steps.

## Current Data Limitation

The supplied June archive contains the five required historical SCADA exports:
Demand, Temperature, Spin, TA, and TRA. It supports prototype training, replay,
and validation only. Demand and Spin are labelled `Other`, so 569 aligned hours
are conditionally usable rather than `Good`; 153 other hourly buckets are
degraded by coverage or excluded quality. Less than one month of common history
is insufficient for seasonal, holiday, outage, or production validation.

Open-Meteo historical weather supplies observed humidity, rainfall, cloud,
wind, and pressure at Piarco. Because archived provider-issued forecast runs
were not supplied, missing target-hour forecasts use an explicitly labelled
past-observation hourly baseline. Future observed weather is never used as a
forecast feature.

## Latest Validation

- The real June ZIP pipeline imports filename-independent CSV members, creates
  722 hourly buckets, 2,157 direct-horizon training rows, 744 Open-Meteo weather
  observations, and three cutoff-safe replay forecast artifacts.
- Backend suite: 111 tests pass, including ingestion, resampling, leakage,
  forecasting, replay, dashboard, and operating risk.
- Frontend Vitest suite: 7 tests pass.
- Frontend production build passes.
- Both the current database and a clean database upgraded from revision zero
  pass `alembic check`.
- A real Uvicorn request to `/api/dashboard/snapshot` returns the v2.1 1h/2h/6h
  exact-cursor bundle in under one second on the development machine.

## Next Operational Step

Obtain at least twelve months of engineering-approved exports spanning seasons,
holidays, outages, and dispatch regimes. Review the meaning of `Other` quality
with T&TEC engineering, then rerun chronological validation before considering
any model trusted or any connection to a read-only historian/SCADA interface.
