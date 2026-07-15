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

The default weather site is Piarco (`10.5953, -61.3372`, 12 m elevation), which
avoids applying a mountainous grid-cell elevation to the main Trinidad load
corridor. Open-Meteo Best Match supplies current conditions and the primary
hourly forecast. MET Norway Locationforecast and an explicit NOAA GFS model
stream cross-check each hour. Set `MET_NORWAY_USER_AGENT` to an application
identifier with an operations contact or project URL before deployment.

Open-Meteo responses are cached for five minutes and protected by a process-wide
9,000-request daily safety ceiling. `GET /api/v1/health` reports current usage.
MET Norway responses honor `Expires`, `Last-Modified`, and `ETag` headers. Slow
forecast members are abandoned after 12 seconds so one provider cannot stall the
operator dashboard.

The default map uses NASA GIBS Blue Marble, GOES-East cloud imagery, and GPM
IMERG precipitation. OpenStreetMap is the optional street layer. No OpenWeather
or Esri billing key is read by the frontend. See `ExternalServices.md` before
changing providers or deploying the hosted Open-Meteo endpoint operationally.

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

Dashboard requests persist weather, grid, and probability observations when
`SNAPSHOT_PERSISTENCE_ENABLED=true`. Persistence failures degrade the quality
status but do not interrupt the operator snapshot.

## Historical SCADA Replay And Forecast Refresh

The SCADA CSV path is a historical-export prototype workflow, not a live SCADA
integration. Before the replay pipeline imports data it verifies all required
tags, Good-quality samples, and timestamp overlap. Run it with all source CSVs:

```powershell
cd backend
venv\Scripts\python.exe scripts\run_scada_replay_pipeline.py C:\exports\*.csv
```

The supported tags are `PTL132 GENERATION TOTALS`, `MHO132 AVERAGE AMBIENT
TEMPERATURE`, `GSYS SYSTEM_CORRECTED_SPIN_TOTAL`, `GSYS SYSTEM_AVAIL_TOTAL`, and
`GSYS SYSTEM_ONLN_TOTAL`. The pipeline requires at least eight aligned hours;
short history may replay but is not a trusted production-training set.

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
simulated-live feed backed by 8,760 deterministic hourly SCADA/weather
observations. June 2025 is replayed; the remaining eleven months support
historical analytics. This mode does not claim a live T&TEC integration.

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
