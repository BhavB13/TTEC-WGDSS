# Current Status

Last updated: 2026-07-16

## Snapshot

WGDSS is operational as a weather/grid control-room demonstration with an
immutable synthetic archive plus an optional historical June SCADA overlay.

The dashboard currently uses `MockGridProvider`. It is explicitly labelled
`SIMULATED` and is suitable for demonstration, training, replay, and UI
validation only. It is not live T&TEC dispatch telemetry.

With `DEMO_REPLAY_ENABLED=true` (the local demonstration default), the dashboard
consumes a persistent June replay. When the five-tag historical archive has been
imported, the current June hour is sourced from that archive and labelled
`HistoricalScadaReplay`; otherwise it uses the deterministic synthetic
archive. Neither path is a live T&TEC feed.

## Implemented And Validated

- Provider-based live weather and forecast data with quality metadata.
- Historical SCADA replay weather uses cutoff-safe archived ECMWF IFS, NOAA
  GFS, and DWD ICON runs when available, with a past-only fallback.
- Dashboard snapshot API, map overlays, wind display, scenario profiles, and
  historical analytics.
- SCADA CSV import with raw-source preservation, header normalization, timestamp
  parsing, interval/provenance metadata, stable record hashes, raw and
  normalized quality, anomaly reports, duplicate-file protection, and
  cross-file record deduplication.
- Historical replay keeps demand, TRA generation, TA available capacity, and
  corrected System Spin as separate quantities. The dashboard displays the
  corrected spin tag in MW and retains TRA-minus-demand only as a diagnostic.
- Hourly SCADA grid snapshots aligned by timestamp, never row number.
- Snapshot availability comes from the latest contributing source interval end;
  forecast issue times are rounded forward only after that exact availability,
  preventing future interval aggregates from leaking into model features.
- Leakage-safe direct 1h, 2h, and 6h forecast rows with demand lags, rolling
  trends, SCADA temperature, observed weather, and issued-or-past-only weather
  outlook features.
- Per-horizon comparison of persistence/time-series baselines, Ridge,
  `HistGradientBoostingRegressor`, `RandomForestRegressor`, and
  `ExtraTreesRegressor` using nested
  expanding-window validation and an untouched chronological holdout.
- Leakage-safe similar-period matching compares target hour, forecast
  temperature, day type, season, humidity, rainfall, cloud, current demand, and
  recent trend. Pure similarity and ML/similarity blends compete with every
  other candidate per horizon.
- Trinidad calendar features separate weekdays, weekends, fixed/movable public
  holidays, configurable variable holidays, and wet/dry seasons.
- Forecast responses include 90% confidence bounds, horizon MAE/RMSE/MAPE,
  adjusted temperature/load correlation, comparable historical examples, and
  major contributing factors.
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
- Continuous operating-risk probability for every valid horizon through six
  hours, based on TRA, corrected Spin, residual uncertainty, reserve requirement,
  weather-informed demand, and startup timing. The API exposes raw probability,
  demand bounds, safe capacity, headroom, expected/conservative shortfall,
  peak-risk time, decision deadline, severity, confidence, and structured
  drivers; the headline uses the maximum correlated-horizon probability.
  Reserve policy, risk bands, unit blocks, and lead times are configurable and
  returned as `PROTOTYPE_UNCONFIRMED`; they are not approved utility settings.
- Synthetic replay no longer defines corrected Spin as `TRA - demand`; it uses
  a separately generated, explicitly simulated series. Historical replay still
  reads the exported corrected-spin tag directly.
- Repository audit found no XGBoost dependency or XGBoost implementation. The
  existing tested Ridge, histogram gradient boosting, random forest,
  extra-trees, baseline, similarity, and blend candidates were preserved.
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
- A provenance audit of the five-member archive reads 2,750 unique interval
  rows, 1,631 `good`, 6 `uncertain`, and 1,113 `unknown` normalized quality
  values. With an explicit June reporting boundary it flags one spillover
  interval, two out-of-interval minima, and two out-of-interval maxima without
  deleting or silently repairing them.
- On the untouched chronological June holdout, v3 records 14.88 MW MAE at 1h,
  19.43 MW at 2h, and 19.67 MW at 6h. The selected methods are independently
  gated per horizon; these are prototype results, not production guarantees.
- Backend suite: 134 tests pass, including ingestion, resampling, leakage,
  forecasting, replay, dashboard, continuous operating risk, exact 20/50/80%
  probabilities, and chronological Brier-score backtesting.
- Frontend Vitest suite: 10 tests pass.
- Frontend production build passes.
- The Risk workspace was visually verified at 1366x768 with no document scroll,
  horizontal overflow, or overlapping gauge/timeline/evidence panels.
- Both the current database and a clean database upgraded from revision zero
  pass `alembic check`.
- A real Uvicorn request to `/api/dashboard/snapshot` returns the v3.0 1h/2h/6h
  exact-cursor bundle, confidence bounds, metrics, similar examples, and factors
  in under one second on the development machine.

## Next Operational Step

Obtain at least twelve months of engineering-approved exports spanning seasons,
holidays, outages, and dispatch regimes. Review the meaning of `Other` quality
with T&TEC engineering, then rerun chronological validation before considering
any model trusted or any connection to a read-only historian/SCADA interface.
