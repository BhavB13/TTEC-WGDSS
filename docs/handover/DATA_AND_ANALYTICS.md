# Data, Forecasting, and Risk

## Data Classification

| Dataset | Classification | Persistence | Model use |
|---|---|---|---|
| Deterministic 2025 demo archive | Simulated | `demo_observations` | Demonstration and fallback behavior |
| June 2026 five-tag trend exports | Historical replay/calibration | SCADA import, raw, snapshot, and forecast tables | Prototype training/replay under cutoff rules |
| Open-Meteo/MET Norway weather | External observed/forecast | Snapshot/weather tables where invoked | Weather features and display |
| July 23 static package | Experimental immutable snapshot | Session filesystem only | Inference plumbing only; no fitted artifact currently available |
| Future OSI/historian feed | Planned | Not defined | Requires approved connector and governance |

## Weather

### Current and Forecast Sources

The default forecast ensemble is:

1. Open-Meteo primary.
2. MET Norway consensus.
3. Open-Meteo NOAA GFS cross-check.

If all consensus sources fail, the service attempts its fallback. The fallback
is Open-Meteo GFS unless WeatherAPI is explicitly enabled and a key is supplied.

Forecast periods are normalized and matched by rounded UTC hour. For each
operational field, values from valid synchronized sources are merged. Missing
operational fields cause that hour to be skipped rather than invented.
Responses retain provider names, source count, synchronization/degradation
status, and confidence metadata.

The service caches current and forecast responses. Default cache TTL is 300
seconds. Replay weather has a separate six-hour run-availability lag and
six-hour cache by default.

### Weighted Trinidad and Tobago Weather

The weighted aggregation is a demand-exposure prototype. The same point set is
used for temperature, humidity, rainfall, cloud cover, wind, direction,
pressure, and precipitation probability.

| Point | Weight |
|---|---:|
| Piarco | 1.10 |
| Port of Spain | 1.60 |
| Chaguanas | 1.50 |
| San Fernando | 1.40 |
| Arima | 1.25 |
| Diego Martin | 1.20 |
| Penal/Debe | 0.90 |
| Sangre Grande | 0.80 |
| Mayaro | 0.30 |
| Scarborough | 0.50 |
| Point Lisas | 0.50 |

The policy is labelled `PROTOTYPE_UNCONFIRMED`. Point locations, weights,
demand exposure, representativeness, and minimum coverage require engineering
approval.

### Replay Weather

Historical replay requests archived model runs from ECMWF IFS, GFS, and ICON
through Open-Meteo's single-runs interface. A configured availability lag
prevents using a model run before it would have been available. If a genuine
issued run cannot be obtained, the implementation uses a labelled past-only
fallback. Future observed weather must not be treated as a forecast feature.

## SCADA Trend Export Contract

The main historical importer expects:

```text
Pen Index, Name, Start Time, End Time, Min Time, Min Value,
Max Time, Max Value, Avg Value, Quality
```

`Avg Value` is the interval value. Raw intervals, extrema, raw quality,
normalized quality, file hashes, stable row hashes, anomaly flags, and
provenance are retained.

### Five Known Tags

| Source tag | WGDSS field/use | Confirmation |
|---|---|---|
| `PTL132 GENERATION TOTALS` | `system_generation_total_mw`; compatibility demand proxy | Official target semantics and units unconfirmed |
| `MHO132 AVERAGE AMBIENT TEMPERATURE` | SCADA ambient temperature | Sensor location/representativeness and units unconfirmed |
| `GSYS SYSTEM_CORRECTED_SPIN_TOTAL` | corrected System Spin | Exact corrected formula and quality policy unconfirmed |
| `GSYS SYSTEM_AVAIL_TOTAL` | TA / available capacity | Exact TA definition unconfirmed |
| `GSYS SYSTEM_ONLN_TOTAL` | TRA / online capacity | Exact TRA definition unconfirmed |

Corrected System Spin is retained as an independent source value. It is not
reconstructed from TRA minus demand.

### Time Alignment

Rows are irregular interval summaries, not exact hourly samples. The selected
hourly method is duration-weighted interval overlap:

```text
hour_value =
  sum(interval_average * overlap_seconds_with_hour)
  / sum(overlap_seconds_with_hour)
```

The raw source is not modified. The alignment audit also compares containing
interval midpoint and nearest midpoint methods on chronological holdout data.
Stored hourly values are reconciled to the overlap-weighted source result with
a 0.1 MW tolerance.

The data model separates:

- observation hour;
- exact source interval completion/availability time;
- forecast issue time;
- forecast target time.

Features cannot use a source interval until the full interval has finalized.
This is the main protection against future interval leakage.

Quality mappings are provisional. `Good` maps to good and `Other` is
conditionally usable under current settings; utility approval is required.

## June Simulated-Present and Previous Day

The active June day is replayed against a persistent cursor. When imported
five-tag data exists and is complete for the source regime, the replay uses it
and identifies it as historical SCADA replay. Otherwise deterministic
simulation remains available and is labelled accordingly.

For the active day:

- rows after the replay cursor are withheld;
- exact-cursor forecast artifacts are used only when their source cursor
  matches;
- future observed demand, TRA, weather, or capacity is not exposed as an input.

For a previous selected day:

- completed observations for that date are returned;
- the classification changes to `SIMULATED_REPLAY_DAY`;
- completeness and missing/degraded values are reported;
- active replay controls and current risk planning are not presented as live.

## July Snapshot Test Evidence

`docs/LIVE_SCADA_SNAPSHOT_TEST_REPORT.md` records the supplied static package:

| Item | Recorded result |
|---|---|
| Source | `20260723.zip` |
| SHA-256 | `1c4802aedbda50848bf3a3f0c4b3b3c6ad52dc083891cabd7b091ebbc22cf8f7` |
| Available range | 2026-07-23 00:00-11:30 AST |
| Common valid boundary | 2026-07-23 11:30 AST |
| Raw/accepted rows | 2,486 / 2,486 |
| Duplicate/malformed/future/impossible rows | 0 / 0 / 0 / 0 |
| Latest demand proxy | 1,274.98 MW |
| Latest TRA | 1,408.6 MW |
| Latest corrected spin | 72.76 MW |
| Latest SCADA temperature | 32.7 C |
| Missing required field | available generation capacity / TA |
| Model status | `NO_FROZEN_MODEL_ARTIFACT` |

That report is evidence from the existing experiment, not a live refresh
performed by this handover. Forty-eight post-boundary weather periods were
captured for the session. The source remained immutable and normal June tables
were not changed.

## Demand Forecasting

### Version and Period Policy

- Model metadata version: `demand-forecast-v5.0`
- Feature profile: `demand_weather_grid_state_v5`
- Configured training: 2025-10-01 through 2026-05-31
- Configured simulated-live period: 2026-06-01 through 2026-06-30
- Direct horizons: 1 through 6 hours

`DataPeriodPolicy` requires both feature and target timestamps to fall inside
October-May before a row enters normal training. June rows may exist in the
derived table for replay/inference, but `train_and_store()` excludes them from
training when using the normal application session.

This policy is implemented and tested; it is not a claim that the available
historical sample is sufficient for production validation.

There are two related forecast paths:

- `demand-forecast-v5.0` evaluates and stores direct 1h-6h horizon artifacts
  from `forecast_training_rows`;
- `demo-load-forecast-v3.1` constructs the full-day replay chart from the
  available source regime, recent load state, historical profile, weather, and
  validated statistical/ML selection.

Exact-cursor 1h-6h replay artifacts can replace corresponding full-day future
points only when their source cursor matches. A direct-horizon model result
must not be described as the same fitted object as the full-day display model.

### Base Feature Order

The ordered `FEATURE_COLUMNS` contract is:

```text
current_demand_mw
lag_1h_demand_mw
lag_2h_demand_mw
lag_3h_demand_mw
lag_6h_demand_mw
lag_24h_demand_mw
lag_48h_demand_mw
lag_168h_demand_mw
target_lag_24h_demand_mw
target_lag_48h_demand_mw
target_lag_168h_demand_mw
rolling_3h_demand_mw
rolling_6h_demand_mw
rolling_12h_demand_mw
rolling_24h_demand_mw
rolling_168h_demand_mw
same_hour_7d_average_mw
target_same_hour_7d_average_mw
demand_volatility_6h_mw
demand_rate_1h_mw
demand_rate_3h_mw
demand_rate_6h_mw
spinning_reserve_mw
available_capacity_mw
online_capacity_mw
reserve_margin_mw
online_spare_mw
spinning_reserve_lag_1h_mw
available_capacity_lag_1h_mw
online_capacity_lag_1h_mw
spinning_reserve_rate_1h_mw
available_capacity_rate_1h_mw
online_capacity_rate_1h_mw
temperature_c
scada_temperature_c
temperature_lag_1h_c
rolling_3h_temperature_c
temperature_rate_1h_c
humidity_percent
rainfall_mm_hr
cloud_cover_percent
wind_speed_kmh
pressure_hpa
forecast_temperature_c
forecast_humidity_percent
forecast_rainfall_mm_hr
forecast_cloud_cover_percent
forecast_wind_speed_kmh
forecast_precipitation_probability_percent
```

The model vector then appends, in code-defined order:

- target-hour cyclical and weekend features;
- nonlinear cooling/heating and weather/load interactions;
- load/capacity ratios and input-quality diagnostics;
- month/day/year, weekday, holiday, and wet/dry-season features;
- calendar/hour interactions;
- one missing indicator for every base feature.

The authoritative ordering is `_feature_names()` in
`demand_forecast_model_service.py`. Any serialized artifact must preserve that
exact order and feature profile.

### Preprocessing

For each chronological training cutoff:

- missing base inputs are filled from the training rows;
- continuous inputs are clipped to training-only 0.5th/99.5th percentiles when
  there are enough samples;
- temperature normal and balance-point profiles are learned from training
  rows only;
- calendar and interaction features are generated deterministically;
- abnormal current-demand inputs can constrain the output around validated
  similar-period spread and holdout RMSE.

No global scaler is fitted across June. The code uses model-specific
scikit-learn fitting inside chronological evaluation, not a repository-wide
pre-fitted scaler.

### Candidate Selection and Validation

Each horizon is evaluated independently:

1. Sort rows chronologically.
2. Keep the newest 20% as an untouched holdout.
3. Select/bias-correct baselines using expanding walk-forward folds in the
   earlier 80%.
4. Evaluate candidate ML models and blends.
5. Activate ML only when both MAE and RMSE improve by at least 2% over the
   selected baseline on the newest holdout.

Candidate families include:

- persistence, trend, rolling trend, same-hour-yesterday, weekly seasonal,
  hourly average, target same-hour average, and similar-period baselines;
- Ridge;
- HistGradientBoostingRegressor;
- RandomForestRegressor;
- ExtraTreesRegressor;
- load-state residual and similarity blends.

There is no XGBoost implementation or dependency in the inspected repository.

Metrics include MAE, RMSE, MAPE, residual standard deviation, peak error,
candidate comparison, and empirical interval coverage. The prototype interval
level is 80%. Uncertainty is bounded by residual, error, demand-relative, and
horizon-dependent floors, then empirical residual offsets are used for the
reported interval.

### Model Storage and Loading

The normal training command fits/evaluates candidates and stores forecast
results, metrics, metadata, feature evidence, and uncertainty in SQL tables. It
does **not** serialize the fitted estimator or preprocessing transform.

The July experiment has a separate inference-only loader for a joblib
dictionary with schema `wgdss-frozen-demand-model-v1`. It validates:

- feature names and fill values supplied by the artifact;
- fitted horizon pipelines;
- model/training metadata;
- training end no later than 2026-05-31;
- an explicit assertion that the July snapshot was not used for training.

The current repository has no such artifact. Model loading for the experiment
therefore fails closed without retraining or refitting preprocessing.

## Generation-Need Probability

### Event

For each horizon:

```text
projected_reserve = forecast_TRA - forecast_demand
safe_capacity = forecast_TRA - required_reserve
generation_need_event = actual_demand > safe_capacity
z = (safe_capacity - forecast_demand) / forecast_sigma
probability = 1 - NormalCDF(z)
```

The default no-action TRA projection is current observed TRA held constant. A
future observed TRA is not used as a forecast. Corrected System Spin is
separate context.

The engine evaluates valid points through six hours and selects the point with
the highest probability, then shortfall and earlier horizon as tie-breakers.
The UI describes this as the highest-risk time.

### Prototype Policy

Defaults in configuration:

- required reserve: 30 MW;
- Watch: probability >= 0.20;
- Prepare: probability >= 0.50;
- Add generation: probability >= 0.80.

All are `PROTOTYPE_UNCONFIRMED`.

### Capacity Planner

The baseline profile always holds current TRA. A hypothetical plan can add
configured aggregate blocks only after their lead time. Default prototype
configuration contains:

- up to three small blocks;
- 15 MW per block;
- 20-minute startup lead;
- verification status `UNCONFIRMED`;
- 60-minute heavy lead, but no heavy MW blocks configured.

The planner seeks the smallest feasible block combination that reaches the
target risk. A proposed action affects only the post-plan profile. It does not
change the headline/no-action risk until a new observed TRA is received.

The what-if endpoint uses a bounded in-process context cache with a 15-minute
default TTL. It is not suitable for multiple API workers without a shared
store.

Shutdown planning is not implemented.

## Dated Validation Evidence

`CURRENT_STATUS.md` records the latest repository validation claims. At its
2026-07-21 update it reported:

- 26,478 direct-horizon rows from 6,554 hourly snapshots;
- October-May training and June exclusion;
- 1h-6h holdout MAE of 22.50, 23.32, 25.18, 26.48, 27.48, and 26.50 MW;
- 163 backend tests and 11 frontend tests passing at that time.

These are dated prototype results. Re-run the pipeline and tests before a model
release; do not treat this handover as independent reproduction of those
metrics.

The handover validation on 2026-07-23 reran software tests but did not retrain
the model or reproduce the reported error metrics.
