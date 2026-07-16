# SCADA + Weather Mathematical Forecasting Upgrade Plan

> **Authoritative context:** `docs/SCADA_OSI_CONTEXT.md` supersedes any older
> tag semantics, units, thresholds, or production-integration suggestions in
> this plan. Utility-specific assumptions are tracked in
> `docs/SCADA_OSI_CONFIRMATION_REGISTER.md`.

## Summary

This upgrade moves WGDSS from mostly rule-based, mock-grid decision support toward a mathematically grounded forecasting and probability engine using historical SCADA CSV exports plus live/weather forecast data.

### Implemented Mathematical Hardening

The current `demand-forecast-v3.0` implementation and
`operating-risk-v3.0` engine add these integrity controls:

- Baseline and ML evaluation use chronological outer holdout data.
- Baseline choice and ML parameter choice use expanding-window walk-forward validation inside the training period, leaving the outer holdout untouched until final evaluation.
- Hourly-average baselines are keyed to the forecast target hour, not the feature hour.
- Daily and weekly cycles use sine/cosine encoding so midnight and adjacent days remain mathematically close.
- Model features retain target-hour forecast humidity, wind speed, precipitation probability, and current pressure instead of discarding fields already supplied by the weather providers.
- Contemporaneous SCADA spinning reserve, available capacity, online capacity,
  reserve margin, and online spare values are retained in the auditable dataset
  and used by operating risk. June benchmarks showed that these dispatch-response
  variables worsened demand generalization, so the default demand-model vector
  excludes them.
- Cooling-degree, temperature/humidity interaction, forecast-temperature delta, transformed rainfall, source-quality, and missing-value indicators are generated without changing the stored training schema.
- Forecast weather is eligible for a training row only when its `created_at` timestamp proves it was available at the feature timestamp.
- Bad SCADA feature/target rows are excluded from model fitting; weather-degraded rows remain usable with explicit missingness indicators.
- ML is activated only when both MAE and RMSE improve on the selected baseline by at least 2%.
- Similar-period matching and 25/50/75% ML blends compete under the same
  chronological gates. Neighbours must have a target already observable by the
  query feature time.
- Calendar context separates Trinidad weekdays, weekends, public holidays, and
  wet/dry seasons. Variable holiday dates can be supplied through
  `FORECAST_EXTRA_HOLIDAY_DATES`.
- Forecast artifacts expose calibrated 90% bounds, per-horizon metrics,
  temperature/load correlation, comparable historical periods, and major
  contributing factors.
- ML fitting uses a 14-day exponential recency half-life and lower weights for weather-degraded rows, allowing the model to adapt while keeping all split and feature chronology intact.
- Forecast uncertainty is calibrated from residual standard deviation, MAE/RMSE floors, demand/horizon floors, and the empirical 90th-percentile absolute error.
- Historical replay/backtest forecasts cannot drive the live dashboard recommendation. Live use requires fresh generation time, fresh SCADA, good quality, and a forecast target strictly after the latest SCADA timestamp.
- After model/baseline selection, the active method is refit on all eligible historical rows and applied to a separate inference row built from the newest good SCADA snapshot. The stored timestamp is therefore a genuine future 1h, 2h, or 6h target when current inference inputs exist.
- When no archived provider-issued forecast is available, target-hour weather
  uses an explicitly labelled baseline built only from past observations. It is
  down-weighted and receives degraded uncertainty treatment; future observed
  weather is never used.
- The offline replay pipeline stores exact-cursor 1h/2h/6h results. Dashboard
  replay uses them only when the artifact cursor matches the simulated source
  cursor; later artifacts cannot drive an earlier replay decision.
- The rule-based fallback now estimates demand transparently and sends it through the operating-risk probability engine; it no longer presents an arbitrary additive score as a probability.

Current SCADA files are historical exports, not a live SCADA stream. The first implementation should support prototype modeling, replay, validation, and calibration. Production SCADA integration should later use automated CSV export, historian database access, PI/OSIsoft, OPC-UA, or a formal SCADA API.

The core objective is to:

1. Import SCADA measurements safely.
2. Align SCADA tags by timestamp, never row number.
3. Build normalized hourly grid snapshots.
4. Combine SCADA grid state with weather and forecast weather.
5. Train and validate demand forecasting models.
6. Convert forecast demand and uncertainty into an operating-risk probability.
7. Feed `/api/dashboard/snapshot` without breaking the current dashboard or mock provider.

## Project Purpose

TTEC-WGDSS supports Trinidad and Tobago electricity control-room decision making by estimating whether weather-driven demand and available generation conditions may require additional generation.

The upgraded mathematical engine should answer:

- What is current system demand?
- What is the current reserve position?
- What demand is likely in 1h, 2h, and 6h?
- How uncertain is that forecast?
- What is the probability that demand exceeds safe online capacity?
- What operational recommendation should be shown?

## SCADA and Weather Roles

### SCADA Data Role

SCADA data provides measured grid and operating-state inputs.

Current CSV structure:

```text
Pen Index, Name, Start Time, End Time, Min Time, Min Value, Max Time, Max Value, Avg Value, Quality
```

Use `Avg Value` as the interval measurement value.

Known SCADA tags:

| SCADA Tag | Meaning | Normalized Field |
|---|---|---|
| `PTL132 GENERATION TOTALS` | Generation total; currently used as an unconfirmed demand proxy | `system_generation_total_mw` / compatibility field `current_demand_mw` |
| `MHO132 AVERAGE AMBIENT TEMPERATURE` | Ambient temperature; unit pending confirmation | `temperature_c` |
| `GSYS SYSTEM_CORRECTED_SPIN_TOTAL` | Corrected System Spin; formula/unit pending confirmation | `spinning_reserve_mw` |
| `GSYS SYSTEM_AVAIL_TOTAL` | TA interpretation pending confirmation | `available_capacity_mw` |
| `GSYS SYSTEM_ONLN_TOTAL` | TRA interpretation pending confirmation | `online_capacity_mw` |

### Weather Data Role

Weather data provides demand-driving external conditions.

Use current and forecast weather fields:

- temperature
- humidity
- rainfall
- cloud cover
- wind speed
- forecast temperature
- forecast rainfall
- forecast cloud cover

Current weather providers remain in place. Open-Meteo remains primary. WeatherAPI.com remains optional fallback. Weather data should supplement SCADA; it should not replace measured SCADA demand, reserve, or capacity values.

## Existing Repo Context

The repo already has:

- FastAPI backend.
- SQLAlchemy models and Alembic migrations.
- Provider-based `GridProvider`.
- `MockGridProvider`.
- Weather provider abstraction.
- Open-Meteo provider.
- WeatherAPI provider.
- MET Norway forecast consensus provider.
- Calibration import service for prior Excel archive work.
- Dashboard snapshot endpoint.
- Rule-based recommendation engine.
- Snapshot persistence.
- Frontend dashboard using the snapshot API.

This plan should extend the current architecture instead of replacing it.

## Mathematical Formulas

### Normalized Grid Snapshot Formulas

Create hourly aligned grid snapshots using timestamps only.

Fields:

```text
timestamp
current_demand_mw
temperature_c
spinning_reserve_mw
available_capacity_mw
online_capacity_mw
reserve_margin_mw
reserve_margin_percent
online_spare_mw
quality_status
source
```

Formulas:

```text
reserve_margin_mw = available_capacity_mw - current_demand_mw
reserve_margin_percent = reserve_margin_mw / current_demand_mw * 100
online_spare_mw = online_capacity_mw - current_demand_mw
```

Terminology correction: the `reserve_margin_*` fields above are retained as
legacy available-capacity-margin features for compatibility. Operator-facing
**System Spin** is `spinning_reserve_mw` from `GSYS
SYSTEM_CORRECTED_SPIN_TOTAL`. `online_spare_mw` is the raw TRA-minus-demand gap
and may differ from corrected System Spin.

Guardrails:

- If `current_demand_mw <= 0`, do not calculate percentage margin.
- If any required tag is missing for an hour, mark snapshot quality as degraded.
- Preserve original SCADA `Quality`.
- Use timestamp alignment only.
- Never join SCADA series by row index.

### Risk Event Formula

The risk event is:

```text
actual_demand_mw > safe_online_capacity_mw
```

Where:

```text
immediate_capacity_mw = min(
    online_capacity_mw,
    current_demand_mw + spinning_reserve_mw
)
safe_online_capacity_mw = immediate_capacity_mw - required_reserve_mw
```

A first version currently evaluates this configurable prototype policy:

```text
required_reserve_mw = max(current_demand_mw, forecast_demand_mw)
                      * configured_reserve_fraction
```

The configured value is not an approved T&TEC operating rule. Its status is
returned in the API as `policy_status`; production use requires the utility to
confirm reserve requirements, credible-contingency treatment, thresholds, unit
blocks, and lead times.

If a trustworthy spinning-reserve measurement is unavailable, use online capacity as the immediate-capacity boundary and state that limitation in model status. Historical calibration spinning reserve must not be substituted for live spinning reserve.

## Database Design Additions

Add new tables rather than forcing model-grade SCADA rows into current live dashboard tables.

### `scada_import_runs`

Purpose: track source CSV imports and prevent duplicate loads.

Suggested fields:

```text
id
source_filename
source_path
source_hash
row_count
import_status
summary
imported_at
```

Duplicate protection:

- Calculate file hash.
- Skip or replace based on explicit importer option.
- Record import outcome.

### `scada_raw_measurements`

Purpose: preserve raw SCADA measurements.

Suggested fields:

```text
id
import_run_id
pen_index
tag_name
start_time
end_time
min_time
min_value
max_time
max_value
avg_value
quality
source_filename
created_at
```

Indexes:

```text
(tag_name, start_time)
(import_run_id)
(quality)
```

### `scada_grid_snapshots`

Purpose: normalized hourly aligned SCADA grid state.

Suggested fields:

```text
id
timestamp
current_demand_mw
temperature_c
spinning_reserve_mw
available_capacity_mw
online_capacity_mw
reserve_margin_mw
reserve_margin_percent
online_spare_mw
quality_status
source
created_at
```

Indexes:

```text
(timestamp)
(quality_status)
```

### `forecast_training_rows`

Purpose: model-ready supervised learning rows.

Suggested fields:

```text
id
feature_timestamp
horizon_hours
target_timestamp
target_demand_mw
current_demand_mw
lag_1h_demand_mw
lag_2h_demand_mw
lag_24h_demand_mw
rolling_3h_demand_mw
rolling_6h_demand_mw
hour_of_day
day_of_week
temperature_c
humidity_percent
rainfall_mm_hr
cloud_cover_percent
wind_speed_kmh
forecast_temperature_c
forecast_rainfall_mm_hr
forecast_cloud_cover_percent
source_quality_status
created_at
```

### `demand_forecast_results`

Purpose: store model output and uncertainty.

Suggested fields:

```text
id
forecast_timestamp
generated_at
horizon_hours
forecast_demand_mw
forecast_uncertainty_mw
model_name
model_version
baseline_name
baseline_forecast_mw
quality_status
created_at
```

## Forecast Dataset Design

Build training rows from timestamp-aligned SCADA snapshots and weather observations/forecasts.

Features:

- current demand
- lag 1 hour demand
- lag 2 hour demand
- lag 24 hour demand
- rolling 3 hour demand average
- rolling 6 hour demand average
- hour of day
- day of week
- temperature
- humidity
- rainfall
- cloud cover
- wind speed
- forecast temperature
- forecast rainfall
- forecast cloud cover

Targets:

- demand 1 hour ahead
- demand 2 hours ahead
- demand 6 hours ahead

No future leakage:

- For a row at time `t`, only use SCADA values observed at or before `t`.
- For forecast weather, use forecast values that would have been available at `t`.
- Do not use actual future weather as a feature unless explicitly labeled as retrospective oracle analysis.
- Do not randomize train/test rows.

## Demand Forecast Model Design

### Forecast Horizons

Forecast:

```text
1 hour demand
2 hour demand
6 hour demand
```

The existing 30-minute and 60-minute dashboard fields can remain for compatibility, but the new mathematical engine should internally support 1h, 2h, and 6h outputs.

### Baselines

Always compute baselines:

1. Persistence

```text
forecast_demand = current_demand_mw
```

2. Same-hour-yesterday

```text
forecast_demand = demand at same hour on previous day
```

3. Hourly average

```text
forecast_demand = historical average demand for that hour of day
```

### Stronger Model

Use one v1 stronger model:

```text
HistGradientBoostingRegressor
```

Fallback if dependency or data volume is insufficient:

```text
RandomForestRegressor
```

Recommended default:

```text
HistGradientBoostingRegressor
```

This model is a good first choice because it handles nonlinear weather/load interactions well and works without requiring complex feature scaling.

### Required Python Dependencies

Add later when implementing model training:

```text
scikit-learn
numpy
pandas
joblib
```

### Train/Test Split

Use chronological split only.

Recommended default:

```text
first 80% of timestamps = train
last 20% of timestamps = test
```

Do not use random train/test split.

### Metrics

Calculate:

- MAE
- RMSE
- MAPE
- residual standard deviation
- baseline comparison

Only trust the ML model if it beats the best baseline on MAE and RMSE.

If it does not beat baseline:

- Mark model status as `BASELINE_ACTIVE`.
- Use best baseline forecast.
- Continue showing forecast uncertainty.

## Probability / Risk Engine Design

Replace arbitrary score weighting with operating-risk probability.

Inputs:

- forecast demand
- forecast uncertainty
- online generation capacity
- available generation capacity
- spinning reserve
- reserve margin threshold
- model status
- data quality

Risk event at each valid horizon through six hours:

```text
actual_demand_mw + required_reserve_mw > immediate_online_capacity_mw
```

With corrected spin available, immediate capacity honors both the TRA ceiling
and the corrected rapid-response reserve constraint:

```text
immediate_online_capacity_mw = min(
    TRA,
    current_demand_mw + corrected_spin_mw
)
safe_online_capacity_mw = immediate_online_capacity_mw - required_reserve_mw
```

Required reserve:

```text
required_reserve_mw = max(current_demand_mw, forecast_demand_mw)
                      * reserve_margin_threshold
```

The reserve fraction is configurable and explicitly unconfirmed. Do not treat
the development default as an approved operating threshold. Corrected spin is
not redefined as `TRA - demand`, and the reserve requirement is subtracted only
once. TA is not immediate capacity; verified TA headroom only bounds capacity
that guidance may identify as startable.

### Probability Estimate

For v1, use normal approximation:

```text
z = (safe_online_capacity_mw - forecast_demand_mw) / forecast_uncertainty_mw
probability = 1 - normal_cdf(z)
```

The API returns this calculation for every valid horizon and uses the maximum
horizon probability as the headline risk. Horizons are correlated, so it does
not combine them using an independence formula. The result also includes exact
expected positive shortfall and confidence-upper-bound conservative shortfall.

Guardrails:

- If `forecast_uncertainty_mw <= 0`, use residual standard deviation from validation.
- If uncertainty is unavailable, mark probability quality as degraded.
- If SCADA or weather data is stale/missing, fail safely.
- Probability must come from operating risk, not arbitrary scoring.

### Risk Levels

```text
LOW < 0.30
MEDIUM 0.30-0.65
HIGH > 0.65
```

### Recommendations

```text
LOW = NO ACTION REQUIRED
MEDIUM = MONITOR CONDITIONS
HIGH = PREPARE ADDITIONAL GENERATION / START ADDITIONAL TURBINE
```

For compatibility with the current frontend, the backend can continue mapping the high-risk action to the existing displayed string if needed.

### Reasoning Output

Reasoning should explain operational drivers, for example:

- Forecast demand is within safe online capacity.
- Forecast demand is approaching safe online capacity.
- Forecast uncertainty is high.
- Reserve margin is below planning threshold.
- Spinning reserve is low relative to load.
- Weather conditions are increasing expected demand.
- Model is using baseline fallback.

## Dashboard/API Integration

Do not break the existing dashboard or mock provider.

Eventually `/api/dashboard/snapshot` should return:

- SCADA-backed grid data
- weather data
- forecast demand
- forecast uncertainty
- risk probability
- recommendation
- reasoning
- model status

Implementation status:

- Phase 6 adds optional `demand_forecast`, `model_status`, and `scada_status` blocks to the dashboard snapshot.
- Existing `weather`, `grid`, `forecast`, `probability`, `recommendation`, `calibration`, and `data_quality` fields remain backward compatible.
- If SCADA snapshots and demand forecast results are present, the backend can populate probability and recommendation from the operating-risk engine.
- If SCADA/model data is missing, the dashboard continues using the existing rule-based recommendation path.
- `MockGridProvider` remains available and unchanged.

Recommended backward-compatible approach:

- Keep existing `weather`, `grid`, `forecast`, `probability`, `recommendation`, `calibration`, and `data_quality`.
- Add optional `model_status`.
- Add optional `demand_forecast`.
- Add optional `scada_status`.
- Keep existing probability fields populated.
- Preserve `MockGridProvider` as default unless `GRID_PROVIDER=scada_csv` or similar is configured.

Suggested future response additions:

```json
{
  "model_status": {
    "active_model": "HistGradientBoostingRegressor",
    "model_version": "demand-hgb-v1",
    "mode": "ML_ACTIVE",
    "trained_through": "2026-06-30T23:00:00-04:00",
    "metrics": {
      "mae": 0,
      "rmse": 0,
      "mape": 0,
      "residual_std": 0
    },
    "baseline_comparison": {
      "best_baseline": "same_hour_yesterday",
      "ml_beats_baseline": true
    }
  },
  "demand_forecast": {
    "horizons": [
      {
        "horizon_hours": 1,
        "forecast_demand_mw": 0,
        "forecast_uncertainty_mw": 0
      },
      {
        "horizon_hours": 2,
        "forecast_demand_mw": 0,
        "forecast_uncertainty_mw": 0
      },
      {
        "horizon_hours": 6,
        "forecast_demand_mw": 0,
        "forecast_uncertainty_mw": 0
      }
    ]
  },
  "scada_status": {
    "source": "historical_csv",
    "latest_snapshot": "2026-06-30T23:00:00-04:00",
    "quality_status": "GOOD"
  }
}
```

## Phased Implementation Plan

## Phase 1 - SCADA Import Foundation

### Goal

Import raw SCADA CSV files safely and preserve source measurements.

### Likely Files Created Later

- `backend/app/models/scada.py`
- `backend/app/schemas/scada.py`
- `backend/app/services/scada_import_service.py`
- `backend/scripts/import_scada_csv.py`
- Alembic migration under `backend/alembic/versions/`
- `backend/tests/test_scada_import_service.py`

### Likely Files Modified Later

- `backend/app/models/__init__.py`
- `backend/requirements.txt` only if CSV parsing needs extra packages, otherwise avoid new dependencies
- `docs/SCADA_WEATHER_MATH_UPGRADE_PLAN.md`

### Steps

1. Add `scada_import_runs`.
2. Add `scada_raw_measurements`.
3. Build a CSV importer using Python `csv.DictReader`.
4. Normalize headers case-insensitively.
5. Parse `Start Time`, `End Time`, `Min Time`, and `Max Time`.
6. Store `Avg Value` as numeric interval value.
7. Preserve `Quality`.
8. Store source filename and import hash.
9. Prevent duplicate imports by file hash.
10. Add import script for local historical CSVs.
11. Add tests with sample rows for all known tags.

### Acceptance Criteria

- Raw CSV rows import successfully.
- Headers are normalized.
- Timestamps parse consistently.
- `Avg Value` is stored as the interval measurement.
- Duplicate imports are skipped or explicitly replaced.
- Original quality values are preserved.
- Tests pass.

### Risk Level

Low to medium. Main risks are timestamp format variation and inconsistent SCADA tag naming.

## Phase 2 - Normalized Grid Snapshots

### Goal

Create hourly aligned SCADA grid snapshots from raw measurements.

### Likely Files Created Later

- `backend/app/services/scada_snapshot_service.py`
- `backend/tests/test_scada_snapshot_service.py`

### Likely Files Modified Later

- `backend/app/models/scada.py`
- Alembic migration

### Steps

1. Add `scada_grid_snapshots`.
2. Map known SCADA tags to normalized fields.
3. Group raw measurements by timestamp bucket.
4. Align by `Start Time` or interval timestamp, not row number.
5. Calculate reserve formulas.
6. Assign `quality_status`.
7. Record missing fields.
8. Add snapshot build command.

### Acceptance Criteria

- Hourly snapshots are produced from raw measurements.
- No row-number joins are used.
- Reserve formulas match the plan.
- Missing fields produce degraded quality.
- Good-quality rows remain distinguishable from bad/inactive rows.

### Risk Level

Medium. Alignment rules must be strict to avoid false mathematical confidence.

## Phase 3 - SCADA + Weather Forecast Dataset

### Goal

Build model-ready training rows using SCADA snapshots and weather data.

### Likely Files Created Later

- `backend/app/services/forecast_dataset_service.py`
- `backend/tests/test_forecast_dataset_service.py`

### Likely Files Modified Later

- `backend/app/models/forecast.py` or new model table file
- `backend/app/services/weather_service.py` only if persisted historical forecast lookup is needed

### Steps

1. Add `forecast_training_rows`.
2. Join SCADA snapshots to weather by timestamp.
3. Build lag and rolling demand features.
4. Build hour/day calendar features.
5. Attach forecast weather for each horizon.
6. Generate target demand for 1h, 2h, and 6h.
7. Exclude rows where target or required features are missing.
8. Add leakage checks in tests.

### Acceptance Criteria

- Training rows are timestamp aligned.
- 1h, 2h, and 6h horizons are generated.
- No future demand appears in feature columns.
- Rows with insufficient history are skipped or marked unusable.

### Risk Level

Medium to high. Leakage prevention is critical.

## Phase 4 - Demand Forecast Model

### Goal

Train and evaluate baselines plus one stronger demand forecast model.

### Likely Files Created Later

- `backend/app/services/demand_forecast_model_service.py`
- `backend/app/services/demand_forecast_baselines.py`
- `backend/scripts/train_demand_forecast_model.py`
- `backend/tests/test_demand_forecast_model_service.py`

### Likely Files Modified Later

- `backend/requirements.txt`

### Steps

1. Add `scikit-learn`, `numpy`, `pandas`, and `joblib`.
2. Implement persistence baseline.
3. Implement same-hour-yesterday baseline.
4. Implement hourly-average baseline.
5. Train `HistGradientBoostingRegressor`.
6. Use chronological split only.
7. Calculate metrics.
8. Compare ML against baselines.
9. Persist model artifact and metadata.
10. Fall back to best baseline if ML does not beat baseline.

### Acceptance Criteria

- Baselines run without ML.
- ML trains only when enough data exists.
- Metrics are stored or emitted.
- Chronological split is enforced.
- Model is trusted only if it beats baseline.

### Risk Level

High. One month of data may be too little for reliable ML.

## Phase 5 - Probability / Risk Engine Upgrade

### Goal

Convert forecast demand and uncertainty into operating-risk probability.

### Likely Files Created Later

- `backend/app/services/risk_probability_engine.py`
- `backend/tests/test_risk_probability_engine.py`

### Likely Files Modified Later

- `backend/app/services/recommendation_engine.py`
- `backend/app/schemas/probability.py`
- `backend/app/schemas/recommendation.py`
- `backend/app/models/probability_results.py`

### Steps

1. Add operating-risk probability calculation.
2. Use forecast demand and uncertainty.
3. Calculate safe online capacity.
4. Calculate probability using normal approximation.
5. Assign LOW/MEDIUM/HIGH.
6. Generate recommendation.
7. Generate reasoning.
8. Fail safely when required data is missing.
9. Keep existing response fields for frontend compatibility.

### Acceptance Criteria

- Probability comes from risk event math.
- No arbitrary score-only probability is used.
- LOW/MEDIUM/HIGH thresholds match the plan.
- Missing SCADA/model/weather data inhibits or degrades recommendations safely.
- Existing dashboard still renders.

### Risk Level

Medium. The statistical model is simple but must be explained clearly.

## Phase 6 - Dashboard/API Integration

### Goal

Expose SCADA-backed grid state, demand forecasts, model status, and probability through the dashboard snapshot.

### Likely Files Created Later

- Optional `backend/app/schemas/model_status.py`

### Likely Files Modified Later

- `backend/app/services/dashboard_service.py`
- `backend/app/schemas/dashboard.py`
- `backend/app/services/grid_service.py`
- `backend/app/providers/grid_provider_factory.py`
- `frontend/src/types/dashboard.ts`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/components/DemandForecastChart.tsx`

### Steps

1. Add a config-selected SCADA CSV/replay provider without removing `MockGridProvider`.
2. Add optional model and SCADA status blocks to dashboard snapshot.
3. Populate existing probability and recommendation fields from the new engine.
4. Update frontend types.
5. Display forecast uncertainty and model status without breaking current cards.
6. Keep mock mode as default for demos.

### Acceptance Criteria

- `/api/dashboard/snapshot` remains backward compatible.
- Mock mode still works.
- SCADA-backed mode works when configured.
- Frontend shows model status and uncertainty when present.
- Dashboard does not crash if model data is absent.

### Risk Level

Medium. The main risk is breaking existing frontend assumptions.

## Phase 7 - Validation, Documentation, and Safety

### Goal

Make the mathematical assumptions and operational limits clear.

### Likely Files Modified Later

- `README.md`
- `docs/PROJECT_OVERVIEW.md`
- `docs/ARCHITECTURE.md`
- `docs/API.md`
- `docs/WEATHER_DATA_SOURCES.md`
- `docs/SCADA_INTEGRATION_PLAN.md`
- `docs/ML_FORECASTING_PLAN.md`
- `docs/SECURITY.md`
- `docs/USER_MANUAL.md`

### Steps

1. Document historical-export limitation.
2. Document formulas.
3. Document model training approach.
4. Document probability limitations.
5. Document fail-safe behavior.
6. Document future live SCADA options.
7. Add smoke-test instructions.

### Acceptance Criteria

- Engineers can understand the math.
- Operators can understand recommendation meaning.
- Limitations are explicit.
- Future SCADA integration path is documented.

### Risk Level

Low.

## Implemented Backend Pipeline Status

The backend now supports the following offline/prototype SCADA math pipeline:

1. Import separate CSVs or a filename-independent ZIP archive with content-hash
   deduplication, two-digit timestamp support, and quality preservation.
2. Resample irregular source intervals into hourly snapshots by timestamp
   overlap, recording coverage, missing fields, and conditional quality.
3. Optionally backfill observed Open-Meteo historical weather for the SCADA
   range without presenting it as an archived issued forecast.
4. Build leakage-safe 1h/2h/6h training and inference rows using each snapshot's
   explicit availability time.
5. Compare five chronological baselines plus Ridge,
   HistGradientBoostingRegressor, and RandomForestRegressor per horizon.
6. Persist model metrics, uncertainty, feature profile, candidate metrics, and
   exact-cursor replay artifacts outside API requests.
7. Expose cursor-consistent forecast/model/SCADA status through
   `/api/dashboard/snapshot` and evaluate the full horizon profile with TA, TRA,
   Spin, reserve, uncertainty, and startup constraints.

Phases 1-7 are implemented as a historical-export prototype. This is not a live
SCADA stream, the June model remains `PROTOTYPE`, and engineering review plus a
representative 12-month dataset are required before operational trust.

## Dashboard Snapshot Additions

The dashboard snapshot may now include these optional objects:

```json
{
  "demand_forecast": {
    "horizons": [
      {
        "horizon_hours": 1,
        "forecast_timestamp": "2026-06-30T09:00:00Z",
        "forecast_demand_mw": 1040,
        "forecast_uncertainty_mw": 30,
        "model_name": "persistence",
        "model_version": "demand-forecast-v3.0",
        "baseline_name": "persistence",
        "baseline_forecast_mw": 1030,
        "quality_status": "BASELINE_ACTIVE"
      }
    ]
  },
  "model_status": {
    "active_model": "persistence",
    "model_version": "demand-forecast-v3.0",
    "mode": "BASELINE_ACTIVE",
    "trained_through": "2026-06-30T09:00:00Z",
    "metrics": {
      "mae": 10,
      "rmse": 12,
      "mape": 1.2,
      "residual_std": 30
    },
    "baseline_comparison": {
      "best_baseline": "persistence",
      "ml_beats_baseline": false
    }
  },
  "scada_status": {
    "source": "scada.csv",
    "latest_snapshot": "2026-06-30T08:00:00Z",
    "quality_status": "GOOD",
    "missing_fields": ""
  }
}
```

These fields are optional. Frontend and API clients must continue handling snapshots where they are absent.

## Operating-Risk Integration Behavior

When both a latest 1-hour demand forecast and a latest SCADA grid snapshot exist, the dashboard can use:

```text
safe_online_capacity_mw = immediate_capacity_mw - required_reserve_mw
required_reserve_mw = max(current_demand_mw, forecast_demand_mw)
                      * configured_reserve_fraction
probability = P(actual_demand_mw > safe_online_capacity_mw)
```

The probability uses forecast uncertainty from validation residuals. If
SCADA/model data is unavailable, incomplete, or invalid, the system must fail
safely and label the recommendation unavailable or degraded. Replay and mock
inputs must never be presented as live telemetry.

## Validation Commands

Backend validation:

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
```

Migration validation:

```powershell
cd backend
.\venv\Scripts\python.exe -m alembic upgrade head
```

Script checks:

```powershell
cd backend
.\venv\Scripts\python.exe scripts\import_scada_csv.py --help
.\venv\Scripts\python.exe scripts\build_scada_snapshots.py --help
.\venv\Scripts\python.exe scripts\build_forecast_training_rows.py --help
.\venv\Scripts\python.exe scripts\train_demand_forecast_model.py --help
```

Frontend validation:

```powershell
cd frontend
npm run build
```

## Safety Notes

- Historical SCADA exports are for prototype modeling, replay, and validation only.
- The dashboard must not claim live T&TEC SCADA integration until an actual historian/API/OPC-UA/live export path is implemented.
- The ML path is optional. Baselines remain the trusted fallback.
- ML should only be considered active when it beats the best baseline on chronological validation.
- Probability must remain tied to the operating-risk event, not arbitrary visual scoring.
- Missing or stale SCADA/weather/model data must fail safely.

## Mathematical Integrity Rules

These rules are mandatory:

- No row-number joins.
- Timestamp alignment only.
- No future leakage.
- No random train/test split.
- Always compare to baseline.
- Store forecast uncertainty.
- Probability must come from operating risk, not arbitrary scoring.
- Fail safely if SCADA, weather, or model data is missing.
- Preserve raw SCADA measurements before deriving snapshots.
- Preserve SCADA quality status.
- Keep mock provider available.

## Phase 9 - End-to-End Historical Replay and Math Hardening

### Goal

Phase 9 turns the individual SCADA/math services into a repeatable historical replay pipeline. This is still a prototype and validation workflow, not live SCADA integration.

The replay pipeline should let an engineer run one command against historical SCADA CSV exports and produce:

- imported raw SCADA measurements
- hourly normalized SCADA grid snapshots
- forecast training rows
- trained/evaluated demand forecast results
- validation status for imports, snapshot quality, model metrics, and risk readiness

### Implemented Replay Script

```text
backend/scripts/run_scada_replay_pipeline.py
```

The script runs these services in order:

1. `ScadaImportService`
2. `ScadaSnapshotService`
3. `ForecastDatasetService`
4. `DemandForecastModelService`
5. `ScadaReplayValidationService`

It prints:

- files imported
- duplicates skipped
- raw rows stored
- snapshots created
- degraded snapshots
- training rows created
- skipped rows
- model horizons evaluated
- active model per horizon
- MAE, RMSE, MAPE, residual standard deviation
- whether ML beats the baseline
- risk-engine readiness

### Validation Report Service

```text
backend/app/services/scada_replay_validation_service.py
```

The report summarizes:

- import status
- raw measurement count
- latest source file
- total/good/degraded snapshots
- missing snapshot fields
- training row counts by horizon
- latest model metrics by horizon
- best baseline and ML gating result
- whether the operating-risk engine has enough data to run

### Hardened Mathematical Rules

Phase 9 keeps the following rules explicit and test-backed:

- SCADA joins use timestamps, never row numbers.
- Forecast targets must be strictly future timestamps.
- Lag and rolling features use only current or past demand.
- Train/test splits are chronological only.
- Baselines are always evaluated before ML is trusted.
- ML becomes active only if it beats the best baseline on both MAE and RMSE.
- Forecast uncertainty is forced positive before risk evaluation.
- Operating risk is based on:

```text
actual_demand_mw > safe_online_capacity_mw
```

Where:

```text
safe_online_capacity_mw = online_capacity_mw - required_reserve_mw
required_reserve_mw = current_demand_mw * reserve_margin_threshold
```

- If SCADA, weather, forecast, online capacity, or model uncertainty is missing, the engine fails safely with an unavailable status instead of inventing a probability.

### Phase 9 Acceptance Criteria

- Replay command accepts one or more CSV exports.
- Duplicate CSV imports are skipped by source hash.
- Shuffled SCADA rows still produce correct timestamp-aligned snapshots.
- Missing SCADA tags degrade snapshots and are reported.
- Forecast training rows are grouped by horizon.
- Demand model metrics are stored by horizon.
- ML is not activated unless it beats the baseline.
- Risk probability is unavailable without online capacity.
- Existing dashboard snapshot compatibility is preserved.
- `MockGridProvider` remains available.

## Core Math Hardening v1.1

### Forecast Baselines

The demand forecast model now evaluates multiple transparent baselines before trusting ML:

- persistence
- trend-adjusted persistence
- rolling trend
- same-hour-yesterday
- hourly average

The best baseline is selected by MAE first, then RMSE, then MAPE. This avoids choosing a model that only wins one error measure while behaving worse on another.

### Chronological Evaluation

Forecast rows are sorted by `feature_timestamp` inside the model service before the train/test split. This keeps the split chronological even if the caller provides rows out of order.

### Forecast Uncertainty

Forecast uncertainty is calibrated conservatively using the maximum of:

- residual standard deviation
- MAE
- half RMSE
- 1.5% of forecast demand
- a horizon-scaled minimum MW floor

This prevents unrealistically low uncertainty on smooth or short replay datasets.

### Operating Risk Probability

The operating-risk engine validates numeric inputs before calculating probability. It rejects missing, non-finite, negative, or physically invalid values and returns `UNAVAILABLE` instead of producing a misleading score.

The probability calculation remains tied to the operating event:

```text
actual_demand_mw > safe_online_capacity_mw
```

Corrected spin and TRA are separate constraints on immediate capability. TA is
used only for verified startability context. Weather enters the risk calculation
through the leakage-safe demand forecast and residual uncertainty, not through
fixed probability points.

## Limitations of One Month of SCADA Data

One month of SCADA data can support prototype modeling and validation, but it has limits:

- It may not include enough extreme weather events.
- It may not capture seasonal demand shifts.
- It may not represent holidays or unusual outages.
- ML may overfit daily patterns.
- Forecast uncertainty may be underestimated.
- Baselines may outperform ML.
- Recommendations should be labeled prototype/calibration until more history is collected.

Minimum preferred production training history:

```text
6-12 months
```

Better target:

```text
24+ months
```

## Future Live SCADA / Historian Integration

Historical CSV support should evolve toward one of these production paths:

1. Automated CSV export into a monitored import folder.
2. An approved read-only historian database or replica.
3. An approved AspenTech OSI export or historian interface.
4. An approved read-only OPC UA interface.
5. An approved vendor API.
6. An approved telemetry/message interface.

No endpoint, protocol, or credential should be implemented until T&TEC/OSI
owners select and document the approved option.

The future live provider should implement the existing `GridProvider` pattern rather than bypassing dashboard services.

Suggested future provider names:

```text
ScadaCsvReplayProvider
HistorianGridProvider
ScadaApiGridProvider
```

## Validation Checklist

### Import Validation

- SCADA CSV imports all known tags.
- Duplicate import protection works.
- `Avg Value` is used.
- `Quality` is preserved.
- Bad or inactive rows are not silently treated as good.

### Snapshot Validation

- Snapshots align by timestamp.
- Reserve formulas are correct.
- Missing tags degrade quality.
- No row-number joins exist.

### Dataset Validation

- Lag features use only past data.
- Rolling averages use only past/current data.
- Targets are future demand only.
- Forecast weather is horizon-specific.
- Rows with leakage risk are excluded.

### Model Validation

- Chronological split is used.
- Baselines are calculated.
- ML metrics are calculated.
- ML only activates if it beats baseline.
- Residual standard deviation is stored.

### Probability Validation

- Safe online capacity is calculated.
- Forecast uncertainty is used.
- Probability increases when forecast demand approaches safe capacity.
- Probability decreases when reserve margin improves.
- Missing data fails safely.

### API/Dashboard Validation

- Existing dashboard still loads.
- Mock provider still works.
- Snapshot remains backward compatible.
- SCADA/model fields are optional.
- Frontend handles unavailable model status.

## Recommended First Implementation Phase

Start with:

```text
Phase 1 - SCADA Import Foundation
```

### Why This Should Be First

The importer is the foundation for every later mathematical step. Without trustworthy raw SCADA ingestion, normalized snapshots, training rows, forecasts, and probabilities would all rest on uncertain data. This phase is also low-risk because it can be implemented without changing the live dashboard behavior.

### First Implementation Prompt

```text
Implement Phase 1 only.

Create the SCADA CSV import foundation for WGDSS.

Requirements:
- Backend only.
- Do not modify frontend.
- Do not change dashboard behavior.
- Do not remove MockGridProvider.
- Add SQLAlchemy models for scada_import_runs and scada_raw_measurements.
- Add Alembic migration.
- Add ScadaImportService.
- Add backend/scripts/import_scada_csv.py.
- Normalize CSV headers case-insensitively.
- Parse Start Time, End Time, Min Time, Max Time.
- Use Avg Value as the interval value.
- Preserve Quality.
- Store Pen Index and Name.
- Store source filename and source hash.
- Avoid duplicate imports by source hash.
- Add tests for valid import, duplicate import, missing fields, and known tag preservation.
- Run backend tests.
```
