# WGDSS Technical Overview and Machine Learning Implementation

## 1. System Purpose

The T&TEC Weather Grid Decision Support System (WGDSS) is a full-stack,
read-only operational decision-support platform. It combines historical SCADA
trend exports, weather observations and forecasts, demand forecasting,
probabilistic capacity-risk calculations, and an interactive control-room
dashboard.

The current application is a prototype and historical replay system. It is not
connected to a live T&TEC SCADA system and it does not start, stop, or otherwise
control generation equipment.

## 2. Technology Stack

| Area | Technologies |
| --- | --- |
| Frontend | React 18, TypeScript, Vite |
| Styling | Tailwind CSS and custom responsive CSS |
| Mapping | Leaflet and React-Leaflet |
| Charts | Chart.js and react-chartjs-2 |
| Backend | Python, FastAPI, Pydantic |
| Database | SQLAlchemy, Alembic, SQLite locally, PostgreSQL-ready |
| Data processing | pandas and NumPy |
| Machine learning | scikit-learn |
| External HTTP | requests with asynchronous FastAPI orchestration |
| Frontend testing | Vitest, Testing Library, jsdom |
| Backend testing | pytest |
| Continuous integration | GitHub Actions |
| Runtime | Uvicorn and Node.js/npm |
| Windows launch tooling | PowerShell and command scripts |

## 3. Frontend Architecture

The frontend is a React single-page application written in TypeScript. Vite
provides the development server, TypeScript build integration, environment
variables, module bundling, and production builds.

The primary data flow is:

```text
Dashboard
  -> TypeScript API client
  -> GET /api/dashboard/snapshot
  -> Typed dashboard DTO
  -> Map, weather, demand, risk, guidance, and analytics components
```

Important frontend development techniques include:

- Strong TypeScript interfaces for API responses.
- Reusable functional React components and hooks.
- Responsive CSS grid and flex layouts.
- Internal tab workspaces that limit page-level scrolling.
- Responsive Chart.js canvases using `maintainAspectRatio: false`.
- Leaflet layer controls for operational overlays.
- Loading, unavailable, stale-data, and historical replay states.
- Separation between API services, types, components, and map datasets.

Important components include:

- `Dashboard.tsx`: application composition and API data distribution.
- `WeatherMap.tsx`: Leaflet map and operational layers.
- `DemandForecastChart.tsx`: full-day demand, uncertainty, actual demand, and TRA.
- `ProbabilityGauge.tsx`: operational risk visualization.
- `RiskTimelineChart.tsx`: no-action and post-plan capacity risk.
- `RecommendationCard.tsx`: machine-generated operator guidance.
- `ReplayLoadChart.tsx`: historical replay visualization.
- `CurrentConditions.tsx`: current weather presentation.
- `GridStatusCard.tsx`: grid-state presentation.

## 4. Mapping and Weather Visualization

The map uses Leaflet rather than ArcGIS. It supports:

- NASA Blue Marble base imagery.
- OpenStreetMap as an alternative base map.
- NASA/NOAA GOES-East infrared cloud imagery.
- NASA GPM IMERG precipitation imagery.
- Wind direction markers.
- A frontend-rendered animated wind-flow field.
- Generation stations, substations, load centers, and transmission lines.
- National Hurricane Center storm-tracking information.
- Trinidad and Tobago boundary highlighting.

Weather imagery is remote, time-dependent tile data. It is not produced by the
machine-learning engine. Wind particles are rendered client-side from sampled
weather vectors.

## 5. Backend Architecture

FastAPI provides the application API and startup lifecycle. The backend follows
a layered design:

```text
API routers
  -> Aggregation and application services
  -> Weather, grid, forecasting, risk, capacity-planning, and replay services
  -> Provider abstractions
  -> SQLAlchemy models and external data sources
```

Backend capabilities include:

- Versioned `/api/v1` routes.
- Backward-compatible `/api` aliases for the current frontend.
- Pydantic request and response validation.
- Configurable CORS restrictions.
- Request IDs and structured logging.
- Security headers and no-store API responses.
- Startup database initialization.
- Optional calibration and replay-data seeding.
- Fail-safe behavior when weather, SCADA, TRA, or model data is unavailable.

## 6. Provider Architecture

Weather and grid sources are isolated behind provider interfaces so application
services do not depend directly on one vendor.

Weather providers include:

- Open-Meteo.
- MET Norway.
- WeatherAPI.com as an optional fallback.
- Open-Meteo model-specific and archive endpoints for historical replay.

The weather service can merge providers per field and forecast hour. For
example, temperature may be selected from one provider while rainfall or cloud
cover is selected from another. The resulting records include source count,
confidence, timestamps, and quality metadata.

Grid providers include:

- `MockGridProvider`, which remains the active runtime grid source.
- Provider interfaces prepared for future historian and SCADA sources.

The rest of WGDSS consumes normalized grid data rather than depending directly
on a provider implementation.

## 7. SCADA Data Processing

The current SCADA inputs are historical AspenTech OSI trend exports, not a live
stream. The principal imported tags represent:

- System demand/load.
- Average ambient temperature.
- Corrected spinning reserve.
- Available generation capacity.
- Online generation capacity or TRA.

Raw records preserve:

- Start and end timestamps.
- Average interval value.
- Original tag name.
- Quality.
- Source filename.
- File hash and provenance.
- Data availability timestamp.

Irregular SCADA records are not joined by row number or exact clock hour. Civil
hour snapshots are produced through duration-weighted interval overlap:

```text
hourly value =
    sum(interval value * overlap duration)
    / sum(overlap duration)
```

This prevents skipped, duplicated, or falsely matched readings. Quality and
coverage thresholds determine whether an hourly value is accepted, degraded,
or unavailable.

## 8. Database Architecture

SQLAlchemy 2 provides persistence and transaction handling. Alembic manages
schema migrations. Local development defaults to SQLite, while PostgreSQL is
supported through `DATABASE_URL`, connection pooling, connection recycling,
and pre-ping validation.

Persisted domains include:

- Raw SCADA imports and normalized snapshots.
- Weather observations and forecasts.
- Grid observations.
- Calibration profiles.
- Demand-forecast training rows and evaluations.
- Probability results.
- Historical analyses.
- Recommendations.
- Replay state.
- Users.

# Machine Learning Implementation

WGDSS contains two related demand-forecasting systems. The current repository
does not use XGBoost. It uses scikit-learn linear, tree, boosting, and ensemble
techniques.

Machine learning predicts **future demand**. It does not predict future TRA as
if generation were an uncontrolled weather variable. TRA is operator-controlled
capacity and is anchored to the latest quality-accepted SCADA observation.

## 9. Direct-Horizon Demand Forecasting

The direct-horizon engine predicts demand independently at one through six
hours ahead. Each training row represents one issue time and one target horizon:

```text
features available at issue time -> demand at issue time + horizon
```

This structure makes the information cutoff explicit and reduces the risk of
future-data leakage.

### 9.1 Input Features

#### Demand state

- Current demand.
- Demand lags at 1, 2, 3, 6, 24, 48, and 168 hours.
- Rolling means over 3, 6, 12, 24, and 168 hours.
- Same-hour historical averages.
- Demand volatility.
- One-, three-, and six-hour demand ramps.

#### Grid state

- Corrected spinning reserve.
- Available capacity.
- Current TRA or online capacity.
- Reserve margin.
- Online spare capacity.
- Grid-state lags and rates of change.

#### Weather

- Observed and forecast temperature.
- SCADA ambient temperature.
- Humidity.
- Rainfall and rain probability.
- Cloud cover.
- Wind speed.
- Pressure.
- Forecast-versus-current weather changes.

#### Calendar

- Hour-of-day sine and cosine.
- Day of week.
- Weekend indicator.
- Month and day of year.
- Trinidad and Tobago holiday indicators.
- Wet- and dry-season indicators.

#### Engineered interactions

- Cooling- and heating-degree values.
- Temperature deviation from historical normal.
- Temperature-humidity interaction.
- Temperature-demand interaction.
- Log-transformed rainfall.
- Capacity-to-demand ratios.
- Missing-data and clipping indicators.

### 9.2 Candidate Models

The forecasting tournament evaluates:

- Persistence.
- Trend-adjusted persistence.
- Rolling trend.
- Same hour yesterday.
- Same hour in the prior week.
- Seven-day same-hour average.
- General hourly average.
- Similar-period matching.
- Ridge regression.
- Load-state residual Ridge regression.
- `HistGradientBoostingRegressor`.
- `RandomForestRegressor`.
- `ExtraTreesRegressor`.
- Blends between ML predictions and similar historical periods.

Residual models predict a correction to a credible load-state or historical
anchor rather than predicting the complete load from zero:

```text
forecast demand = historical/load-state anchor + predicted residual
```

This arrangement is more stable when the available archive is limited.

### 9.3 Similar-Period Matching

The system searches only earlier observations for periods resembling the
forecast issue time. Similarity considers:

- Target hour.
- Day type.
- Season and month.
- Temperature and humidity.
- Rainfall and cloud cover.
- Current demand.
- Recent demand trend.

The nearest historical periods receive exponentially decreasing weights. This
produces a local historical forecast that can stand alone or be blended with an
ML model.

### 9.4 Leakage Prevention

The pipeline applies these safeguards:

- Timestamp joins only.
- Forecast weather must have been issued by the forecast issue time.
- Future actual demand is never used as a feature.
- Preprocessing is fitted only on training folds.
- No random train/test split is used.
- Chronological expanding-window validation is used.
- The newest chronological segment is retained as an untouched holdout.
- Full-day future values depend on prior predictions, not unrevealed actuals.

### 9.5 Model Selection

The outer dataset is divided chronologically into older training data and a
newest holdout period. Expanding-window folds within the older data select the
candidate model and blend. The selected model is then evaluated against the
strongest baseline on the untouched newest period.

ML is activated only if it improves both MAE and RMSE by at least two percent.
Otherwise, WGDSS retains the stronger baseline. This prevents model complexity
from being treated as proof of better forecasting.

Evaluation metrics include:

- Mean absolute error (MAE).
- Root mean squared error (RMSE).
- Mean absolute percentage error (MAPE).
- Peak error.
- Residual standard deviation.
- Forecast interval coverage.
- Improvement relative to the selected baseline.

### 9.6 Preprocessing

Preprocessing parameters are learned from training data only:

- Missing values use training medians or controlled defaults.
- Inputs are clipped at training-derived 0.5th and 99.5th percentiles.
- Sample weights decay with age using a 14-day half-life.
- Lower-quality records receive reduced weight.
- Abnormal current demand is checked against similar historical periods.
- Degraded source quality widens forecast uncertainty.

## 10. Full-Day Replay Forecaster

A second forecasting path builds the full-day chart used during historical
replay. It combines:

- An hourly historical profile.
- The median recent profile residual.
- Load-state and weather residual Ridge regression.
- A tuned blend between the statistical profile and Ridge result.

It uses chronological fit, tuning, and holdout periods. The model becomes active
only when it beats the moving-profile baseline on newer unseen data.

Future values are generated recursively:

```text
predict next hour
  -> add prediction to temporary demand history
  -> construct the following hour's lag and rolling features
  -> predict the following hour
```

This allows the curve to react to the current load trajectory while preventing
future actual demand from leaking into the forecast.

## 11. Forecast Uncertainty

WGDSS returns a point forecast and an uncertainty range. Uncertainty considers:

- Residual standard deviation.
- MAE and RMSE.
- Empirical absolute errors.
- Forecast horizon.
- Minimum MW and percentage floors.
- Weather confidence.
- Source quality.

Direct-horizon intervals use calibration residual quantiles with a statistical
minimum width. Full-day uncertainty expands with forecast distance and weather
confidence.

## 12. Capacity-Risk Mathematics

Demand is forecast by the ML system. TRA is treated as operator-controlled
capacity and remains anchored to the latest accepted observation.

For each horizon:

```text
safe capacity = current TRA - required reserve
risk event = actual demand > safe capacity
```

Under the version-one normal forecast-error approximation:

```text
z = (safe capacity - forecast demand) / forecast sigma
risk probability = 1 - NormalCDF(z)
```

The required reserve and risk-policy thresholds are configurable prototype
assumptions. They require T&TEC control-engineering confirmation before
production use.

The capacity planner calculates two trajectories:

- **No action:** current observed TRA remains constant.
- **Post plan:** current TRA plus configured start blocks after their startup
  lead times.

Small prototype blocks use a configurable 20-minute startup time. Heavy blocks
use a configurable 60-minute lead time, but MW-specific heavy recommendations
are suppressed until approved capacities are configured.

The planner remains advisory. Hypothetical capacity does not reduce the
headline operational risk until the corresponding increase is observed in
SCADA.

## 13. Current Limitations

- The active grid provider remains simulated or replay-based.
- Historical SCADA exports are not a live OSI connection.
- The common quality-controlled archive is short for production ML validation.
- A short archive cannot represent annual seasonality, outages, industrial
  schedules, or rare extreme events reliably.
- Some capacities, reserve targets, startup policies, and thresholds remain
  unconfirmed.
- The normal forecast-error approximation can underestimate non-normal tail
  risk.
- Weather confidence does not guarantee local station accuracy.
- ML output must remain operator guidance rather than automated control.

A production-ready model should be validated on at least 12 months of
quality-controlled data, preferably multiple years containing unusual weather
and operating conditions.

## 14. Testing, CI, and Delivery

The repository uses:

- `pytest` for backend unit, integration, ingestion, replay, forecast, risk, and
  capacity-planning tests.
- Vitest and Testing Library for frontend tests.
- TypeScript checking as part of frontend builds.
- Alembic migration checks.
- GitHub Actions for backend tests, migrations, frontend tests, and builds.
- PowerShell and command scripts for one-command local startup.

The central architectural safety property is the separation of four concepts:

1. Forecast demand.
2. Observed TRA.
3. Corrected spinning reserve.
4. Hypothetical planned capacity.

Keeping these quantities separate is necessary for mathematically credible and
operationally safe decision support.
