# WGDSS Operations Guide

## Local startup

Backend:

```powershell
cd backend
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

The dashboard is available at `http://localhost:5173`. The API documentation is
available at `http://localhost:8000/docs`.

## Configuration

Copy `backend/.env.example` to `backend/.env` and set environment-specific
values. Production deployments must set explicit `CORS_ALLOWED_ORIGINS`; wildcard
origins are deliberately ignored. Set `DATABASE_AUTO_CREATE=false` in managed
environments and apply Alembic migrations during deployment.

The frontend reads `VITE_API_BASE_URL` when the API is hosted separately. Local
development uses Vite's `/api` proxy.

The forecast model includes fixed and Easter-relative Trinidad and Tobago
holidays. Add engineering-approved variable or specially declared dates as a
comma-separated list when required:

```text
FORECAST_EXTRA_HOLIDAY_DATES=2026-03-20,2026-11-09
```

Dates must use `YYYY-MM-DD`. This setting changes calendar features and
similar-period classification; it does not retrieve a calendar API.

Current conditions and forecasts use one batch Open-Meteo request covering
eleven Trinidad and Tobago points. Temperature, humidity, rainfall, cloud cover, wind speed,
pressure, and precipitation probability are calculated with the same
demand-exposure weights. Wind direction uses the same weights with a circular
mean so directions around north are combined correctly. Heat index,
weather condition, and rain severity are then derived from those weighted
inputs. Dense residential and commercial centers carry more weight than the
Point Lisas industrial reference. This is a configurable
`PROTOTYPE_DEMAND_EXPOSURE_V1` index, not an approved population, customer-count,
or T&TEC feeder-load allocation.

| Sampling point | Prototype weight | Role |
| --- | ---: | --- |
| Port of Spain | 1.60 | Dense commercial/residential |
| Chaguanas | 1.50 | Dense residential/commercial |
| San Fernando | 1.40 | Dense residential/commercial |
| Arima | 1.25 | Residential/commercial |
| Diego Martin | 1.20 | Dense residential |
| Piarco / East-West Corridor | 1.10 | Mixed residential/commercial |
| Penal / Debe | 0.90 | Residential/mixed |
| Sangre Grande | 0.80 | Regional residential |
| Mayaro | 0.30 | Lower-density residential |
| Scarborough | 0.50 | Tobago commercial/residential |
| Point Lisas | 0.50 | Industrial reference |

The aggregate is used only when at least 70% of configured sampling weight is
available. Below that threshold, the service retains the provider's
representative-site/consensus weather and does not mislabel it as an aggregate.
The existing temperature-named settings are retained for configuration
compatibility: `TEMPERATURE_AGGREGATION_ENABLED`,
`TEMPERATURE_AGGREGATION_MIN_WEIGHT_COVERAGE_PERCENT`, and
`TEMPERATURE_AGGREGATION_POLICY_STATUS`. T&TEC should replace prototype weights
with approved customer/load-zone exposure factors when those become available.

Open-Meteo Best Match supplies current conditions and the primary hourly
forecast. MET Norway Locationforecast and an explicit NOAA GFS model stream
cross-check each hour. The spatial temperature pass replaces only temperature
and the derived heat index; the other fields retain the existing provider
consensus. Set `MET_NORWAY_USER_AGENT` to an application identifier with an
operations contact or project URL before deployment.

Open-Meteo responses are cached for five minutes and protected by a process-wide
9,000-request daily safety ceiling. `GET /api/v1/health` reports current usage.
MET Norway responses honor `Expires`, `Last-Modified`, and `ETag` headers. Slow
forecast members are abandoned after 12 seconds so one provider cannot stall the
operator dashboard.

The default map uses NASA GIBS Blue Marble, GOES-East Band 13 Clean Infrared
cloud imagery, and GPM IMERG precipitation. The cloud tiles refresh every ten
minutes and remain usable at night. OpenStreetMap is the optional street layer.
No OpenWeather or Esri billing key is read by the frontend. See
`ExternalServices.md` before changing providers or deploying the hosted
Open-Meteo endpoint operationally.

## Database migration

For a new database:

```powershell
cd backend
venv\Scripts\python.exe -m alembic upgrade head
```

For an existing database created before Alembic was introduced, back it up,
verify that its schema matches the initial migration, then stamp it once:

```powershell
venv\Scripts\python.exe -m alembic stamp 87c46bdfdad4
```

Do not stamp an unverified database. Subsequent releases should always use
`alembic upgrade head`.

## Calibration import

Import the supplied weather and generation archive:

```powershell
cd backend
venv\Scripts\python.exe scripts\import_calibration_data.py "C:\path\to\data.zip"
```

The import replaces records previously loaded from the same archive path. It
loads hot, typical, and rainy demand/spinning-reserve profiles plus `Good` SCADA
temperature samples. `Inactive` samples remain stored for provenance but are not
used in dashboard temperature traces.

Automatic startup import is available through:

```text
CALIBRATION_DATA_ZIP_PATH=C:\path\to\data.zip
CALIBRATION_AUTO_IMPORT=true
```

## Health and data quality

`GET /api/v1/health` reports:

- database connectivity;
- primary and fallback weather-provider configuration;
- independent MET Norway consensus-provider configuration;
- NOAA GFS secondary consensus-provider configuration;
- Open-Meteo daily request usage and safety limit;
- optional WeatherAPI monthly usage and safety limit;
- external API cost mode (`zero_cost` or `review_required`);
- calibration row/sample availability.

`GET /api/dashboard/snapshot` includes `data_quality`, identifying weather as
`LIVE`, `CALIBRATED`, `FALLBACK`, or `STALE`; grid data as `LIVE` or `SIMULATED`;
and calibration as `CALIBRATED` or `UNAVAILABLE`.

When the active provider is `MockGridProvider`, `data_quality.decision_status`
is `SIMULATION` and the dashboard labels grid status as simulated. Those values
support training and replay only; they must not be interpreted as live dispatch
authority.

Forecast periods are a rolling horizon beginning at the current hour. The UI
shows the next six periods strictly after the current Trinidad time and refreshes
the snapshot every five minutes. Imported SCADA temperature is historical
calibration evidence and is never substituted for a live weather observation.
Historical replay identifies `MHO132 AVERAGE AMBIENT TEMPERATURE` as a source
aggregate, but does not claim that the SCADA tag uses the prototype spatial
weights; its exact sensor composition requires T&TEC/OSI confirmation.

Dashboard requests persist weather, grid, and probability observations when
`SNAPSHOT_PERSISTENCE_ENABLED=true`. Persistence failures degrade the quality
status but do not interrupt the operator snapshot.

## Historical SCADA Replay And Forecast Refresh

The SCADA CSV path is a historical-export prototype workflow, not a live SCADA
integration. Before mutation, the replay pipeline verifies all required tags,
conditionally usable quality, and timestamp overlap. Run one ZIP archive with
optional Open-Meteo historical weather:

```powershell
cd backend
venv\Scripts\python.exe scripts\run_scada_replay_pipeline.py `
  --backfill-weather C:\exports\scada-history.zip
```

Or run all separate source CSVs:

```powershell
cd backend
venv\Scripts\python.exe scripts\run_scada_replay_pipeline.py C:\exports\*.csv
```

The supported tags are `PTL132 GENERATION TOTALS`, `MHO132 AVERAGE AMBIENT
TEMPERATURE`, `GSYS SYSTEM_CORRECTED_SPIN_TOTAL`, `GSYS SYSTEM_AVAIL_TOTAL`, and
`GSYS SYSTEM_ONLN_TOTAL`. The pipeline requires at least eight aligned hours;
short history may replay but is not a trusted production-training set. `Other`
quality remains visible as `USABLE_WITH_WARNING`; it is not converted to
`Good`. The command stores direct forecasts only for the exact mapped replay
cursor and reports which chronological baseline/model won each horizon.

If the export owner provides an explicit reporting window, pass
`--reporting-start` and `--reporting-end` as ISO-8601 values. Records outside
that window remain preserved and are flagged. WGDSS does not infer the window
from a filename or assume that a month label defines exact boundaries.

In replay, the dashboard maps the compatibility demand field to `PTL132
GENERATION TOTALS` as an unconfirmed proxy, generation to the current TRA
interpretation (`GSYS SYSTEM_ONLN_TOTAL`), and System Spin to the corrected
spin tag. Official tag semantics and units remain pending T&TEC/OSI approval.
The raw `TRA - demand` gap remains visible as a diagnostic, together with the
adjustment between that gap and corrected System Spin. Weather affects forecast
demand and risk; WGDSS does not invent a weather correction for measured spin.

For the replay outlook, WGDSS requests the latest six-hour global model cycle
that is conservatively assumed to have completed before the historical SCADA
cursor. The free Open-Meteo Single Runs archive supplies ECMWF IFS, NOAA GFS,
and DWD ICON in one cached request. These values are mapped by forecast lead,
not by calendar year, and feed the active replay demand/risk forecast. If the
archive call fails, the past-only weather baseline and exact-cursor persisted
forecast remain available.

Run supervised refresh outside the API process after new Good-quality SCADA data
arrives:

```powershell
venv\Scripts\python.exe scripts\refresh_demand_forecast.py
```

It requires 48 snapshots by default and skips when there is no new data. Model
results should be reviewed against their chronological baseline metrics before
they influence operating decisions.

## Bundled Production Demonstration

When `DEMO_REPLAY_ENABLED=true`, the dashboard uses a clearly labelled
simulation replay backed by 8,760 deterministic hourly grid/weather
observations. June 2025 is replayed; the remaining eleven months support
historical analytics. This mode does not claim a live T&TEC integration.

The application has no SCADA/OSI write or control capability. Read
`SCADA_OSI_CONTEXT.md`, `SCADA_OSI_CONFIRMATION_REGISTER.md`, and
`SCADA_OSI_READ_ONLY_SECURITY.md` before designing any production provider.

Initialize or reset it with:

```powershell
cd backend
venv\Scripts\python.exe scripts\seed_demo_replay.py --force
```

The dashboard refreshes every five seconds while replay metadata is present.
Play/Pause/Step/Reset actions persist in `demo_replay_state`; source
observations in `demo_observations` remain immutable. See `DEMO_REPLAY.md` for
the full data-flow and no-future-leakage rules.

## Validation

```powershell
cd backend
venv\Scripts\python.exe -m pytest -q
venv\Scripts\python.exe -m alembic check

cd ..\frontend
npm test
npm run build
npm audit
```

## Production deployment

Use PostgreSQL, apply migrations before starting the API, terminate TLS at the
reverse proxy, and restrict CORS to the deployed dashboard origins. Run Uvicorn
behind a production process manager and collect the JSON logs using the
organization's normal log platform.
