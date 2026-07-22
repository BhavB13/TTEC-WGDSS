# Current Status

Last updated: 2026-07-21

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
- Revealed demand and TRA chart lines now share the same observation-hour
  source timeline. Forecast/risk history remains a separate availability-gated
  copy, preventing synthetic fallback values from contaminating the TRA display
  or post-event actuals from leaking into model inputs.
- Raw irregular SCADA intervals are preserved unchanged. Derived civil-hour
  snapshots use duration-weighted interval overlap, never row number, nearest
  row, or exact-hour lookup.
- Source-to-snapshot reconciliation recomputes hourly demand from raw intervals,
  records duplicate removal, compares candidate alignment methods on an
  untouched chronological holdout, and flags numerical mismatches above 0.1 MW.
- Observation hour, exact source availability, and model issue time are handled
  as separate timestamps. Replay charts show post-event values at their actual
  observation hour; forecast features are unavailable until every contributing
  interval has finalized.
- Snapshot availability comes from the latest contributing source interval end;
  forecast issue times are rounded forward only after that exact availability,
  preventing future interval aggregates from leaking into model features.
- Leakage-safe direct 1h through 6h forecast rows with demand lags, rolling
  trends, SCADA temperature, observed weather, and issued-or-past-only weather
  outlook features.
- Target-hour historical features are now distinct from issue-hour load-state
  features. Same-hour-yesterday, same-hour-weekly, and seven-day target-hour
  averages are keyed to `target_timestamp` and are included only when their
  source interval was available by forecast issue time.
- The current derived dataset contains 26,478 direct-horizon rows from 6,554
  hourly SCADA snapshots spanning October 2025 through June 2026. This remains
  historical replay/calibration data, not a live SCADA stream.
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
- Forecast responses include 80% prototype prediction bounds, horizon MAE/RMSE/MAPE,
  peak-demand error, adjusted temperature/load correlation, comparable
  historical examples, and major contributing factors. Bounds use residuals
  from cutoff-safe expanding-window calibration and report holdout coverage.
- Temperature balance points and hour/season normals are learned inside each
  training cutoff. Nonlinear cooling/heating degrees, humidity interaction,
  temperature deviation/rate, permutation importance, and a no-temperature
  ablation are retained as model evidence; no fixed MW-per-degree adjustment is
  active in the replay forecaster.
- Model inputs are median-filled and clipped to training-only 0.5/99.5
  percentile bounds. Missing/outlier diagnostics are stored per forecast, and
  an isolated abnormal current-demand reading is constrained by validated
  similar-period spread and holdout RMSE.
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
  baseline, 48-hour trends, and 12-month analytics. Persisted 1h-through-6h artifacts
  replace the corresponding chart points only when their source cursor matches
  exactly; mismatched or future artifacts are ignored.
- The replay full-day model now includes exact 1/2/3/6/24/48/168-hour demand lags,
  trailing 3/6/12/24-hour means, short load ramps, and the residual between the
  recent load state and the historical hourly profile. Its level correction is
  the median of six recent profile residuals, which follows sustained movement
  without allowing one bad interval to dominate. A regularized
  load-state/weather residual model and blend tune on a middle chronological
  partition and activate only when they beat the preselected statistical method
  on a separate newest holdout; otherwise the moving profile remains active.
  Ridge inputs and residual corrections are clipped to
  robust ranges learned from the training partition. Current Spin, TA, TRA, and
  weather are model context; future chart points recurse on prior predictions
  and never read unrevealed source demand.
- Forecast training is source-regime strict. A SCADA-backed day uses only
  finalized SCADA intervals and keeps model issue time separate from the later
  chart reveal time. A day outside complete SCADA coverage uses the synthetic
  archive, synthetic weather context, and `simulation` label; SCADA rows are
  never silently mixed with synthetic fallback values.
- Three-source, per-field hourly weather consensus with timestamp synchronization
  and explicit degradation when any source is unavailable.
- Current-clock June alignment with real-time automatic playback and manual
  accelerated controls.
- Continuous capacity-risk probability for every valid horizon through six
  hours. The engine calculates `projected reserve = forecast TRA - forecast
  demand` and evaluates the probability that actual reserve falls below the
  configurable 30 MW project target using calibrated forecast residuals. The
  API exposes the selected horizon's demand, TRA, projected reserve, target,
  surplus/deficit, uncertainty provenance, status, and earliest expected
  insufficiency. Corrected System Spin remains separate SCADA context. Reserve
  policy, status bands, unit blocks, and lead times are configurable and returned
  as `PROTOTYPE_UNCONFIRMED`; they are not approved utility settings.
- Current-TRA anchored aggregate capacity planning. The no-action profile holds
  the exact TRA displayed in the dashboard at every horizon. A separately
  labelled hypothetical profile can add up to three configurable small blocks
  only after the 20-minute lead time. The current 15 MW value remains
  `UNCONFIRMED`; heavy-set MW guidance is disabled until approved capacities
  are configured. Baseline risk never changes because of a proposed action.
- The dashboard snapshot now includes current TRA evidence, before/after risk,
  aggregate block definitions, proposed starts, deadlines, interim exposure,
  warnings, and a machine-generated suggestion with an auditable mathematical
  basis. The suggestion remains fixed while an operator compares a different
  what-if plan. A bounded 15-minute endpoint recalculates a plan without
  persisting instructions or communicating with SCADA. Guidance permanently
  states that manual operator action is required, and shutdown advice remains
  excluded.
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

- The June 20 02:00 demand source interval is 1,028.35 MW. Because the following
  interval begins at 02:59:10, the correct duration-weighted 02:00-03:00 value is
  1,027.966 MW. The prior 745 MW dashboard value was a synthetic fallback caused
  by keying replay rows to rounded availability time; the corrected replay keys
  them to observation hour and keeps availability only for as-of gating.
- On the supplied June demand export, interval-overlap hourly alignment produced
  lower mean 1h-through-6h chronological baseline error (42.812 MW MAE,
  53.464 MW RMSE) than containing-interval midpoint (46.520/58.217 MW)
  and nearest-interval midpoint (46.447/58.190 MW) methods.

- The real June ZIP pipeline imports filename-independent CSV members and
  creates 722 hourly buckets. The active combined historical store currently
  contains 26,478 leakage-gated direct 1h-through-6h training rows; June data
  remains historical replay/calibration input rather than a live feed.
- A provenance audit of the five-member archive reads 2,750 unique interval
  rows, 1,631 `good`, 6 `uncertain`, and 1,113 `unknown` normalized quality
  values. With an explicit June reporting boundary it flags one spillover
  interval, two out-of-interval minima, and two out-of-interval maxima without
  deleting or silently repairing them.
- After rebuilding against the corrected observation/availability alignment,
  untouched chronological holdout MAE is 22.50, 23.32, 25.18, 26.48, 27.48,
  and 26.50 MW for horizons 1 through 6. Similar-period baselines remain active
  at 1-5h. At 6h, a Random Forest/similar-period blend improves on the selected
  baseline from 28.44 to 26.50 MW MAE. Methods remain independently gated per
  horizon; these are prototype results, not production guarantees.
- For the full-day replay selector, rolling chronological holdout MAE at the
  June 15, June 20, and June 25 10:00 checkpoints is 11.67, 8.37, and 10.31 MW,
  compared with 37.04, 28.26, and 31.49 MW for the hourly-average baseline.
  These are one-month replay results, not seasonal or production validation.
- The June 30 screenshot exposed a source-regime mismatch: a 569-row SCADA
  model was being compared with a synthetic day outside complete SCADA
  coverage. Source routing reduced chart MAE against revealed values from
  187.15 MW to 8.91 MW and maximum absolute error from 353.85 MW to 71.11 MW.
- Backend suite: 163 tests pass, including ingestion, resampling, leakage,
  forecasting, replay, dashboard, continuous operating risk, exact 20/50/80%
  probabilities, chronological Brier-score backtesting, current-TRA anchoring,
  20/60-minute lead-time behavior, unavailable telemetry, block limits, and the
  capacity-plan API.
- Frontend Vitest suite: 11 tests pass.
- Frontend production build passes.
- The Risk and Guidance workspaces were visually verified at 1366x768 with no
  document scroll, horizontal overflow, overlapping panels, or clipped risk
  bands. Guidance uses internal scrolling only for longer operator-check lists.
- Both the current database and a clean database upgraded from revision zero
  pass `alembic check`.
- A real Uvicorn request to `/api/dashboard/snapshot` returns all direct
  1h-through-6h exact-cursor horizons, confidence bounds, alignment evidence,
  metrics, similar examples, and capacity-risk-v5.0 output.
- A runtime snapshot invariant check confirmed that every no-action horizon
  equals the displayed 1,285.16 MW current TRA. Its 22.13% peak no-action risk
  produced a one-block recommendation; a one-block what-if reduced hypothetical
  post-plan peak risk to 16.52% without changing the baseline.

## Next Operational Step

Obtain at least twelve months of engineering-approved exports spanning seasons,
holidays, outages, and dispatch regimes. Review the meaning of `Other` quality
with T&TEC engineering, then rerun chronological validation before considering
any model trusted or any connection to a read-only historian/SCADA interface.
