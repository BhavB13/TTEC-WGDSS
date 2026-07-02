# WGDSS System, Component, and File Map

## 1. Document Purpose

This document inventories the systems currently present in WGDSS, identifies
the components that make each system work, and maps each capability to its
source files. It is intended for maintainers, reviewers, operators, and future
SCADA integration teams.

Status terminology:

- **Active:** used by the running application.
- **Optional:** active only when configured or selected.
- **Foundation:** implemented as a model/component but not in the primary
  runtime path.
- **Test-only/legacy:** retained for tests, compatibility, or earlier UI paths.
- **Future:** represented by an interface or design boundary but not connected.

## 2. Repository Architecture

```text
frontend/
  src/
    components/        React visual and map components
    pages/             Dashboard shell and tab composition
    services/          Backend API client and direct map-data clients
    types/             TypeScript API contracts
    data/              Infrastructure and geographic fixtures

backend/
  app/
    api/               FastAPI routes
    core/              Configuration and logging
    providers/         External/source-specific adapters
    services/          Application and decision logic
    schemas/           Pydantic response contracts
    models/            SQLAlchemy persistence models
    database/          Engine, sessions, and initialization
    data/              Mock operational fixtures
  alembic/             Database migration configuration
  scripts/             Administrative import scripts
  tests/               Backend verification

docs/                  Architecture and operating documentation
```

## 3. Application Bootstrap and Runtime Configuration

**Purpose:** Start the backend, load settings, initialize persistence, import
calibration data when configured, register middleware, and expose API routes.

**Status:** Active.

| Component/function | Responsibility | Files |
|---|---|---|
| FastAPI application | Creates the application and root endpoint | `backend/app/main.py` |
| Lifespan handler | Database auto-create and optional calibration import | `backend/app/main.py` |
| Request middleware | Request IDs, duration logging, exception logging | `backend/app/main.py` |
| Settings | URLs, provider flags, coordinates, limits, cache TTLs, database, CORS | `backend/app/core/config.py` |
| Logging configuration | Human/JSON logging setup and formatting | `backend/app/core/logging_config.py` |
| Environment templates | Local configuration examples | `backend/.env.example`, `frontend/.env.example` |
| Backend dependencies | FastAPI, SQLAlchemy, Pydantic, requests, Alembic, PostgreSQL driver | `backend/requirements.txt`, `backend/requirements-dev.txt` |
| Frontend build/runtime | React plugin, API proxy, vendor chunks | `frontend/vite.config.ts`, `frontend/package.json`, `frontend/tsconfig.json` |

The active backend entry point is `app.main:app`. The active frontend entry
point is `frontend/src/main.tsx`.

## 4. API and Routing System

**Purpose:** Validate incoming parameters and expose normalized service results.

**Status:** Active.

| Endpoint | Purpose | Route file | Main service/schema files |
|---|---|---|---|
| `GET /` | Application status | `backend/app/main.py` | `backend/app/core/config.py` |
| `GET /api/dashboard/snapshot` | Primary frontend aggregate payload | `backend/app/api/dashboard.py` | `backend/app/services/dashboard_service.py`, `backend/app/schemas/dashboard.py` |
| `GET /api/storm/tracking` | NHC active-storm data | `backend/app/api/storm.py` | `backend/app/services/storm_tracking_service.py`, `backend/app/schemas/storm.py` |
| `GET /api/v1/health` | Database, providers, quotas, calibration health | `backend/app/api/health.py` | provider health and database files |
| `GET /api/v1/weather/current` | Current normalized weather | `backend/app/api/weather.py` | `backend/app/services/weather_service.py`, `backend/app/schemas/weather.py` |
| `GET /api/v1/weather/forecast` | Normalized hourly forecast | `backend/app/api/weather.py` | `backend/app/services/weather_service.py`, `backend/app/schemas/forecast.py` |
| `GET /api/v1/grid/status` | Normalized Version 1 grid status | `backend/app/api/generation.py` | `backend/app/services/grid_service.py`, `backend/app/schemas/grid.py` |
| `GET /api/v1/recommendations` | Recommendation-only response | `backend/app/api/recommendations.py` | `backend/app/services/dashboard_service.py`, `backend/app/schemas/recommendation.py` |
| `GET /api/v1/dashboard/snapshot` | Versioned aggregate alias | `backend/app/api/router.py`, `backend/app/api/dashboard.py` | dashboard service and schema |

Router composition is defined in:

- `backend/app/api/router.py`
- `backend/app/main.py`
- `backend/app/api/__init__.py`

## 5. Dashboard Aggregation System

**Purpose:** Produce one internally consistent snapshot for the UI.

**Status:** Active and central to the application.

**Primary flow:**

1. Fetch current weather, forecast, grid status, and generation status in
   parallel.
2. attach generation units to the grid result;
3. load and select the calibration scenario;
4. evaluate probability, demand forecasts, risk, and recommendation;
5. validate the response through Pydantic schemas;
6. generate data-quality metadata;
7. persist the snapshot when enabled;
8. return one `DashboardSnapshotResponse`.

| Component/function | Files |
|---|---|
| `DashboardService.get_snapshot` | `backend/app/services/dashboard_service.py` |
| Probability/recommendation-only helper | `backend/app/services/dashboard_service.py` |
| Aggregate response schema | `backend/app/schemas/dashboard.py` |
| Data-quality schema and builder | `backend/app/schemas/data_quality.py`, `backend/app/services/dashboard_service.py` |
| Dashboard API route | `backend/app/api/dashboard.py` |
| Frontend snapshot client | `frontend/src/services/api.ts` |
| Frontend aggregate contract | `frontend/src/types/dashboard.ts` |
| Dashboard state, refresh, and composition | `frontend/src/pages/Dashboard.tsx` |

## 6. Weather Observation System

**Purpose:** Retrieve, normalize, cache, and fail over current weather data.

**Status:** Active and live.

| Layer | Component | Files |
|---|---|---|
| Provider contract | `WeatherProvider` abstract interface | `backend/app/providers/weather_provider.py` |
| Primary provider | Open-Meteo Best Match | `backend/app/providers/open_meteo_provider.py` |
| Default fallback | Open-Meteo NOAA GFS model | `backend/app/providers/open_meteo_provider.py`, `backend/app/services/weather_service.py` |
| Optional fallback | WeatherAPI.com | `backend/app/providers/weatherapi_provider.py`, `backend/app/core/config.py` |
| Orchestration | Failover, cache, normalization, rain severity, heat index | `backend/app/services/weather_service.py` |
| Provider health | Success/failure state | `backend/app/services/provider_health.py` |
| API route | Current-weather endpoint | `backend/app/api/weather.py` |
| Contracts | Current weather response | `backend/app/schemas/weather.py`, `frontend/src/types/dashboard.ts` |
| UI | Current conditions and weather-driver displays | `frontend/src/components/CurrentConditions.tsx`, `frontend/src/components/WeatherCard.tsx`, `frontend/src/pages/Dashboard.tsx` |
| Persistence | Stored observations | `backend/app/models/weather.py`, `backend/app/services/snapshot_persistence_service.py` |

Current weather fields include temperature, humidity, rainfall, cloud cover,
wind speed, wind direction, pressure, condition, heat index, severity,
timestamp, and provider.

## 7. Forecast Consensus System

**Purpose:** Produce a more robust hourly forecast by reconciling multiple
free sources.

**Status:** Active and live.

| Component | Responsibility | Files |
|---|---|---|
| Open-Meteo Best Match | Primary forecast | `backend/app/providers/open_meteo_provider.py` |
| MET Norway | Independent forecast cross-check | `backend/app/providers/met_norway_provider.py` |
| NOAA GFS | Model-specific cross-check through Open-Meteo | `backend/app/providers/open_meteo_provider.py`, `backend/app/services/weather_service.py` |
| Consensus coordinator | Concurrent requests and failure isolation | `backend/app/services/weather_service.py` |
| Reconciliation | Hour alignment, weighted means, condition and confidence | `backend/app/services/weather_service.py` |
| Forecast schema | Normalized hourly output and source metadata | `backend/app/schemas/forecast.py` |
| Frontend types | Forecast DTO | `frontend/src/types/dashboard.ts` |
| Next-six-hours view | Select future periods and render source verification | `frontend/src/pages/Dashboard.tsx` |
| Legacy forecast table | Tabular forecast component | `frontend/src/components/ForecastTable.tsx` |

Provider behavior is verified by:

- `backend/tests/test_weather_service.py`
- `backend/tests/test_met_norway_provider.py`
- `backend/tests/test_provider_caching.py`

## 8. Grid and Generation System

**Purpose:** Supply demand, generation, available capacity, reserve margin,
period status, and unit readiness.

**Status:** Active but simulated in Version 1.

| Component | Responsibility | Files |
|---|---|---|
| Provider contract | Stable source-independent grid interface | `backend/app/providers/grid_provider.py` |
| Mock provider | Time-based demand curve and mock generation totals | `backend/app/providers/mock_grid_provider.py` |
| Mock units | Station/unit output and available capacity | `backend/app/data/mock_generation_data.py` |
| Normalization service | Standard grid DTO and calculated reserve fallback | `backend/app/services/grid_service.py` |
| Grid API | Grid-only endpoint | `backend/app/api/generation.py` |
| Schemas | Grid and generation units | `backend/app/schemas/grid.py`, `backend/app/schemas/generation.py` |
| Frontend contract | Grid and generation-unit types | `frontend/src/types/dashboard.ts` |
| Operations UI | Station dispatch, unit readiness, utilization | `frontend/src/pages/Dashboard.tsx` |
| Legacy grid card | Compact grid component | `frontend/src/components/GridStatusCard.tsx` |
| Persistence | Grid snapshots | `backend/app/models/grid_data.py`, `backend/app/services/snapshot_persistence_service.py` |

**Future provider boundary:** `ScadaGridProvider` and `HistorianGridProvider`
are architectural targets, not current source files. They should implement
`GridProvider` and be injected into `GridService`.

## 9. Probability and Recommendation System

**Purpose:** Convert weather, grid, and calibration conditions into explainable
operator guidance.

**Status:** Active, deterministic, and rule-based.

| Component | Responsibility | Files |
|---|---|---|
| Rule engine | Score, risk, demand projections, factors, recommendation | `backend/app/services/recommendation_engine.py` |
| Probability schema | Score, risk, forecasts, factors, reason | `backend/app/schemas/probability.py` |
| Recommendation schema | Probability result plus action | `backend/app/schemas/recommendation.py` |
| Recommendation API | Recommendation-only endpoint | `backend/app/api/recommendations.py` |
| Aggregation | Supplies live inputs and calibration | `backend/app/services/dashboard_service.py` |
| Persistence | Stores probability result and action | `backend/app/models/probability_results.py`, `backend/app/services/snapshot_persistence_service.py` |
| Additional model foundation | Separate recommendation table | `backend/app/models/recommendation.py` |
| Frontend gauge | Probability display and risk bands | `frontend/src/components/ProbabilityGauge.tsx` |
| Frontend guidance | Actions and operational thresholds | `frontend/src/pages/Dashboard.tsx` |
| Legacy recommendation card | Standalone recommendation display | `frontend/src/components/RecommendationCard.tsx` |

Tests:

- `backend/tests/test_recommendation_engine.py`
- `backend/tests/test_dashboard_service.py`

## 10. Demand Forecast and Scenario Charting System

**Purpose:** Show current, 30-minute, 60-minute, and imported 24-hour scenario
demand behavior.

**Status:** Active.

| Component | Responsibility | Files |
|---|---|---|
| Near-term forecast formula | Weather-adjusted and scenario-anchored demand | `backend/app/services/recommendation_engine.py` |
| Calibration scenario values | Current/next hour profile values | `backend/app/services/calibration_service.py` |
| Demand chart | Chart.js current/scenario demand and SCADA temperature | `frontend/src/components/DemandForecastChart.tsx` |
| Scenario comparison | Hot, typical, and rainy 24-hour curves | `frontend/src/components/ScenarioComparisonChart.tsx` |
| Demand tab | Chart and demand snapshot composition | `frontend/src/pages/Dashboard.tsx` |
| Chart tests | Dataset and rendering behavior | `frontend/src/components/DemandForecastChart.test.tsx`, `frontend/src/components/ScenarioComparisonChart.test.tsx` |

Both demand chart axes use the operational range `700-1500 MW`. Scenario
temperature uses a separate `20-36°C` axis.

## 11. SCADA Calibration Import System

**Purpose:** Import the supplied archive as historical calibration evidence and
turn it into scenario profiles used by the decision engine.

**Status:** Active when calibration data has been imported. It is not live
SCADA ingestion.

| Component | Responsibility | Files |
|---|---|---|
| Archive importer | Reads outer ZIP and nested XLSX workbooks | `backend/app/services/calibration_import_service.py` |
| XLSX reader | Parses workbook XML without a large spreadsheet dependency | `backend/app/services/calibration_import_service.py` |
| Scenario mappings | Maps workbook/sheet names to hot, typical, rainy | `backend/app/services/calibration_import_service.py` |
| CLI import | Manual administrative import | `backend/scripts/import_calibration_data.py` |
| Startup import | Optional automatic import | `backend/app/main.py`, `backend/app/core/config.py` |
| Calibration models | Import runs, temperature samples, scenario profiles | `backend/app/models/calibration.py` |
| Selection service | Scores scenarios and selects hourly values | `backend/app/services/calibration_service.py` |
| API schema | Calibration snapshot and curves | `backend/app/schemas/calibration.py`, `backend/app/schemas/dashboard.py` |
| Frontend contracts | Calibration types | `frontend/src/types/dashboard.ts` |
| Analytics UI | Summary and scenario comparison | `frontend/src/pages/Dashboard.tsx`, `frontend/src/components/ScenarioComparisonChart.tsx` |

Tests:

- `backend/tests/test_calibration_import.py`
- `backend/tests/test_dashboard_service.py`

## 12. Database and Historical Persistence System

**Purpose:** Provide SQLAlchemy persistence for observations, decisions,
calibration, users, and future analytics.

**Status:** Partly active. SQLite is the local default; PostgreSQL is supported
through `DATABASE_URL`.

### 12.1 Database wiring

| Component | Files |
|---|---|
| Declarative base | `backend/app/database/base.py`, `backend/app/models/base.py` |
| Engine | `backend/app/database/engine.py` |
| Session factory and dependency | `backend/app/database/session.py` |
| Local table initialization | `backend/app/database/init_db.py` |
| Model registration | `backend/app/models/__init__.py` |
| Alembic environment | `backend/alembic/env.py`, `backend/alembic.ini` |
| Initial migration | `backend/alembic/versions/87c46bdfdad4_initial_wgdss_schema.py` |

### 12.2 Tables and implementation status

| Table | Model file | Active use |
|---|---|---|
| `weather_observations` | `backend/app/models/weather.py` | Snapshot persistence |
| `grid_data` | `backend/app/models/grid_data.py` | Snapshot persistence |
| `probability_results` | `backend/app/models/probability_results.py` | Snapshot persistence |
| `calibration_import_runs` | `backend/app/models/calibration.py` | Calibration import |
| `scada_temperature_samples` | `backend/app/models/calibration.py` | Calibration selection |
| `calibration_scenario_profiles` | `backend/app/models/calibration.py` | Calibration selection |
| `forecasts` | `backend/app/models/forecast.py` | Foundation; not written by active snapshot persistence |
| `generation_units` | `backend/app/models/generation.py` | Foundation; active grid comes from provider |
| `recommendations` | `backend/app/models/recommendation.py` | Foundation; action is stored in `probability_results` |
| `historical_analysis` | `backend/app/models/historical_analysis.py` | Foundation; no active analytics service |
| `users` | `backend/app/models/users.py` | Foundation; no active authentication API |

Snapshot persistence behavior is implemented in:

- `backend/app/services/snapshot_persistence_service.py`
- `backend/tests/test_snapshot_persistence.py`

## 13. Data Quality, Provider Health, and Quota System

**Purpose:** Make source reliability and freshness visible.

**Status:** Active.

| Component | Responsibility | Files |
|---|---|---|
| Provider state registry | Records last success/failure | `backend/app/services/provider_health.py` |
| Snapshot quality builder | Freshness, fallback, consensus, grid and calibration status | `backend/app/services/dashboard_service.py` |
| Data-quality contract | Status and notes | `backend/app/schemas/data_quality.py`, `frontend/src/types/dashboard.ts` |
| Health endpoint | Database, providers, API usage, calibration | `backend/app/api/health.py` |
| Provider usage counters | Open-Meteo daily and WeatherAPI monthly protection | `backend/app/providers/open_meteo_provider.py`, `backend/app/providers/weatherapi_provider.py` |
| Header indicators | Weather, forecast, grid, scenario, update time | `frontend/src/components/Header.tsx` |

## 14. Tropical Storm and Hurricane System

**Purpose:** Display active NOAA/NHC tropical systems without coupling them to
the recommendation engine.

**Status:** Optional and live when the map layer is enabled.

| Component | Responsibility | Files |
|---|---|---|
| NHC client | Retry, cache, normalization, graceful failure | `backend/app/services/storm_tracking_service.py` |
| Storm route | Backend endpoint | `backend/app/api/storm.py` |
| Storm schemas | Systems, advisories, movement, intensity | `backend/app/schemas/storm.py` |
| Frontend API client | Storm request and force refresh | `frontend/src/services/api.ts` |
| Frontend types | Storm DTOs | `frontend/src/types/storm.ts` |
| Map rendering | Markers, classification colors, popup links | `frontend/src/components/WeatherMap.tsx` |

The backend caches NHC results for 15 minutes. The frontend refreshes the
enabled layer every 15 minutes and keeps the map usable if the feed fails.

## 15. Operational Map System

**Purpose:** Provide geographic situational awareness beside the tabbed
dashboard.

**Status:** Active.

### 15.1 Base map and weather imagery

| Layer | Source | Files |
|---|---|---|
| NASA Blue Marble | NASA GIBS | `frontend/src/components/WeatherMap.tsx` |
| OpenStreetMap | OpenStreetMap tiles | `frontend/src/components/WeatherMap.tsx` |
| Cloud systems | NASA GIBS GOES-East GeoColor | `frontend/src/components/WeatherMap.tsx` |
| Rainfall coverage | NASA GIBS IMERG precipitation rate | `frontend/src/components/WeatherMap.tsx` |
| Country outline | Local boundary coordinates | `frontend/src/data/trinidadAndTobagoBoundary.ts`, `frontend/src/components/WeatherMap.tsx` |

Cloud and rainfall imagery are visual overlays only. Recommendation weather is
still supplied by the backend weather service.

### 15.2 Wind direction and animated flow

| Component | Responsibility | Files |
|---|---|---|
| Exact current wind marker | Uses snapshot bearing, speed, provider | `frontend/src/components/WeatherMap.tsx`, `frontend/src/pages/Dashboard.tsx` |
| Regional wind API | 63 Open-Meteo coordinates, 15-minute cache | `frontend/src/services/windField.ts` |
| Canvas animation | Interpolation, particle movement, map lifecycle | `frontend/src/components/WindFlowLayer.tsx` |
| Canvas stacking | Overlay z-index and pointer behavior | `frontend/src/index.css` |

The wind-flow layer is opt-in and free/keyless. It covers `8°N-14°N` and
`65°W-57°W`, interpolates the four nearest samples, and renders particles below
operational markers.

### 15.3 Infrastructure layers

| Layer | Files |
|---|---|
| Generation stations | `frontend/src/data/infrastructureLayers.ts`, `frontend/src/components/WeatherMap.tsx` |
| Substations | `frontend/src/data/infrastructureLayers.ts`, `frontend/src/components/WeatherMap.tsx` |
| Transmission lines | `frontend/src/data/infrastructureLayers.ts`, `frontend/src/components/WeatherMap.tsx` |
| Load centers | `frontend/src/data/infrastructureLayers.ts`, `frontend/src/components/WeatherMap.tsx` |
| Operations center | `frontend/src/components/WeatherMap.tsx` |

`frontend/src/data/infrastructureMarkers.ts` contains an earlier/alternate
fixture set and is not imported by the active map.

### 15.4 Map lifecycle helpers

All are implemented in `frontend/src/components/WeatherMap.tsx`:

- `MapOverlaySync`: tracks optional storm and wind-flow toggles;
- `MapResizeSync`: invalidates Leaflet dimensions on container/browser resize;
- `MapViewSync`: applies the initial Trinidad view;
- `MapTileStabilizer`: invalidates tile layout after movement and zoom;
- storm coordinate, palette, and radius helpers;
- wind compass and marker-icon helpers.

## 16. Frontend Application and State System

**Purpose:** Fetch the live snapshot, preserve the map, and organize operational
views without page-level navigation.

**Status:** Active.

| Component | Responsibility | Files |
|---|---|---|
| React mount | Creates the application root | `frontend/src/main.tsx` |
| API client | Timeout, errors, snapshot/storm helpers | `frontend/src/services/api.ts` |
| Type contracts | Weather, grid, forecast, probability, recommendation, calibration | `frontend/src/types/dashboard.ts`, `frontend/src/types/storm.ts` |
| Dashboard state | Loading, error, refresh, active tab, fallbacks | `frontend/src/pages/Dashboard.tsx` |
| Shell/header | Persistent header and viewport layout | `frontend/src/pages/Dashboard.tsx`, `frontend/src/components/Header.tsx` |
| Persistent map | Left-side Leaflet panel | `frontend/src/components/WeatherMap.tsx` |
| Global styling | Tailwind layers and responsive control-room styles | `frontend/src/index.css`, `frontend/tailwind.config.cjs` |

The dashboard refresh timer runs every five minutes. API failures preserve an
explicit error/retry state rather than silently replacing live values with
unrelated mock data.

## 17. Frontend Tabs and Component Ownership

| Tab | Main information | Active files |
|---|---|---|
| Home | Demand/generation summary, weather drivers, compact demand chart | `frontend/src/pages/Dashboard.tsx`, `frontend/src/components/DemandForecastChart.tsx` |
| Operations | Station dispatch, unit status, utilization and headroom | `frontend/src/pages/Dashboard.tsx` |
| Weather | Current conditions and next six hours | `frontend/src/pages/Dashboard.tsx`, `frontend/src/components/CurrentConditions.tsx` |
| Demand | Demand profile chart and forecast snapshot | `frontend/src/pages/Dashboard.tsx`, `frontend/src/components/DemandForecastChart.tsx` |
| Risk | Probability gauge and classified factors | `frontend/src/pages/Dashboard.tsx`, `frontend/src/components/ProbabilityGauge.tsx` |
| Guidance | Operator action list and probability/reserve/headroom thresholds | `frontend/src/pages/Dashboard.tsx` |
| Analytics | Selected calibration summary and scenario comparison | `frontend/src/pages/Dashboard.tsx`, `frontend/src/components/ScenarioComparisonChart.tsx` |

Shared helpers such as `PanelCard`, `MiniMetric`, timestamp formatting,
forecast filtering, station metrics, and utilization bars currently live in
`frontend/src/pages/Dashboard.tsx`.

## 18. Legacy and Compatibility Frontend Components

These files exist but are not part of the primary tab composition:

| File | Role |
|---|---|
| `frontend/src/components/WeatherCard.tsx` | Earlier standalone weather summary |
| `frontend/src/components/GridStatusCard.tsx` | Earlier standalone grid card |
| `frontend/src/components/RecommendationCard.tsx` | Earlier recommendation card |
| `frontend/src/components/ForecastTable.tsx` | Table-form forecast view |
| `frontend/src/components/RecommendationHistoryTable.tsx` | Recommendation-history presentation foundation |
| `frontend/src/data/mockData.ts` | Legacy frontend mock values |
| `frontend/src/data/infrastructureMarkers.ts` | Alternate infrastructure fixtures |

They should not be treated as active dashboard data paths unless reintroduced
by an explicit import.

## 19. Test and Validation System

### Backend

| Test area | Files |
|---|---|
| Shared fixtures/configuration | `backend/tests/conftest.py` |
| Health endpoint | `backend/tests/test_health.py` |
| Weather normalization/consensus | `backend/tests/test_weather_service.py` |
| MET Norway adapter | `backend/tests/test_met_norway_provider.py` |
| Provider caching | `backend/tests/test_provider_caching.py` |
| Recommendation rules | `backend/tests/test_recommendation_engine.py` |
| Dashboard assembly | `backend/tests/test_dashboard_service.py` |
| Calibration import | `backend/tests/test_calibration_import.py` |
| Snapshot persistence | `backend/tests/test_snapshot_persistence.py` |

### Frontend

| Test area | Files |
|---|---|
| Test environment | `frontend/src/test/setup.ts`, `frontend/vitest.config.ts` |
| Dashboard fixture | `frontend/src/test/dashboardFixture.ts` |
| Dashboard integration | `frontend/src/pages/Dashboard.test.tsx` |
| Demand chart | `frontend/src/components/DemandForecastChart.test.tsx` |
| Scenario chart | `frontend/src/components/ScenarioComparisonChart.test.tsx` |

Build and test commands are defined in `frontend/package.json` and the backend
requirements files.

## 20. Future and Incomplete Systems

| System | Current foundation | Missing active components |
|---|---|---|
| Live SCADA | `GridProvider`, normalized grid contract, calibration samples | `ScadaGridProvider`, credentials, network/security controls, live tag mapping |
| Historian | Database and provider boundary | `HistorianGridProvider`, historian client, query/caching policy |
| Authentication | `users` table | Login API, password service, tokens/sessions, route protection, frontend auth |
| Historical analytics | Snapshot tables and `historical_analysis` model | Analytics service/API, aggregation jobs, UI queries |
| Recommendation history | Probability persistence and table component | History endpoint and active dashboard integration |
| Forecast persistence | `forecasts` table | Writer, retention policy, verification queries |
| Generation persistence | `generation_units` table | Provider-to-database synchronization |
| Machine learning | Historical/calibration foundation | Explicitly outside Version 1 |
| Notifications | None | Explicitly outside Version 1 |

## 21. Change-Impact Guide

Use this map when modifying the system:

| Desired change | Primary files to inspect |
|---|---|
| Change decision thresholds | `backend/app/services/recommendation_engine.py`, its tests, decision docs |
| Add a weather field | provider files, `weather_service.py`, weather/forecast schemas, TypeScript types, consuming UI |
| Change forecast providers | `weather_service.py`, provider adapter, config, health endpoint, tests |
| Add a live grid source | `grid_provider.py`, new provider file, `grid_service.py`, config, provider tests |
| Change scenario selection | `calibration_service.py`, calibration tests, analytics UI |
| Change imported workbook format | `calibration_import_service.py`, import script, import tests, models/migration if necessary |
| Add a dashboard field | backend schema/service, frontend type, `Dashboard.tsx` or component |
| Add a map overlay | `WeatherMap.tsx`, optional service/data file, `index.css` if canvas/pane styling is required |
| Change database schema | model, Alembic revision, persistence/service, tests |
| Change startup behavior | `main.py`, `core/config.py`, `.env.example`, operations documentation |

