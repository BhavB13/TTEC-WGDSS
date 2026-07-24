# File and Component Map

## Entry Points

| Function | Files |
|---|---|
| FastAPI application/startup | `backend/app/main.py` |
| Versioned router composition | `backend/app/api/router.py` |
| Backend settings | `backend/app/core/config.py` |
| Frontend application | `frontend/src/main.tsx` |
| Dashboard orchestration/UI | `frontend/src/pages/Dashboard.tsx` |
| Frontend API client | `frontend/src/services/api.ts` |
| Local one-command launcher | `scripts/Start-WGDSS.ps1`, `START_WGDSS.cmd` |
| CI | `.github/workflows/ci.yml` |

## Frontend Systems

| System | Components/files |
|---|---|
| Header/status | `components/Header.tsx` |
| Time selection | `context/DashboardTimeContext.tsx`, `components/DayNavigationBar.tsx` |
| Replay control | `components/ReplayControlBar.tsx` |
| Map | `components/WeatherMap.tsx`, `components/WindFlowLayer.tsx`, `services/windField.ts` |
| Map data | `data/infrastructureLayers.ts`, `data/infrastructureMarkers.ts`, `data/trinidadAndTobagoBoundary.ts` |
| Current weather | `components/CurrentConditions.tsx`, `components/WeatherCard.tsx` |
| Forecast chart | `components/DemandForecastChart.tsx`, `components/ReplayLoadChart.tsx` |
| Historical/day charts | `components/HistoricalDemandChart.tsx`, `components/SelectedDayChart.tsx`, `components/ScenarioComparisonChart.tsx` |
| Risk | `components/ProbabilityGauge.tsx`, `components/RiskTimelineChart.tsx`, `utils/probability.ts` |
| Recommendation | `components/RecommendationCard.tsx`, `components/RecommendationHistoryTable.tsx` |
| Experimental SCADA | `components/LiveScadaTest.tsx`, `components/LiveScadaSnapshotChart.tsx` |
| DTOs | `types/dashboard.ts`, `types/liveScadaExperiment.ts`, `types/storm.ts` |
| Tests/fixtures | `pages/Dashboard.test.tsx`, `components/*.test.tsx`, `test/` |
| Styling | `index.css`, `tailwind.config.cjs` |

## Backend API

| System | Files |
|---|---|
| Dashboard | `api/dashboard.py`, `schemas/dashboard.py`, `services/dashboard_service.py` |
| Health | `api/health.py`, `services/provider_health.py` |
| Weather | `api/weather.py`, `schemas/weather.py`, `schemas/forecast.py` |
| Grid | `api/generation.py`, `schemas/grid.py`, `services/grid_service.py` |
| Recommendation | `api/recommendations.py`, `schemas/recommendation.py` |
| Risk schema | `schemas/probability.py` |
| Replay | `api/replay.py`, `schemas/replay.py` |
| Capacity what-if | `api/capacity_plan.py`, `schemas/capacity_plan.py` |
| Storm | `api/storm.py`, `schemas/storm.py` |
| July experiment | `api/live_scada_experiment.py`, `schemas/live_scada_experiment.py` |

## Providers and Weather

| Function | Files |
|---|---|
| Weather contract | `providers/weather_provider.py` |
| Open-Meteo | `providers/open_meteo_provider.py` |
| Replay Open-Meteo | `providers/open_meteo_replay_provider.py` |
| MET Norway | `providers/met_norway_provider.py` |
| WeatherAPI | `providers/weatherapi_provider.py` |
| Merge/cache/failover | `services/weather_service.py` |
| Geographic weighting | `services/temperature_aggregation_service.py`, `data/temperature_sampling.py` |
| Archived weather backfill | `services/historical_weather_backfill_service.py` |
| Storm tracking | `services/storm_tracking_service.py` |

## Grid and SCADA

| Function | Files |
|---|---|
| Grid provider contract | `providers/grid_provider.py` |
| Provider selection | `providers/grid_provider_factory.py` |
| Mock grid | `providers/mock_grid_provider.py`, `data/mock_generation_data.py` |
| July immutable provider | `providers/excel_snapshot_scada_provider.py` |
| SCADA data contract | `services/scada_data_contract.py` |
| CSV import | `services/scada_import_service.py`, `scripts/import_scada_csv.py` |
| Archive import | `services/scada_archive_service.py` |
| Hourly snapshots | `services/scada_snapshot_service.py`, `scripts/build_scada_snapshots.py` |
| Alignment/reconciliation | `services/scada_alignment_service.py` |
| Replay preflight/validation | `services/scada_replay_preflight_service.py`, `services/scada_replay_validation_service.py` |
| Pipeline | `scripts/run_scada_replay_pipeline.py` |
| July session | `services/live_scada_experiment_service.py`, `scripts/run_live_scada_snapshot.py` |

## Forecasting and Risk

| Function | Files |
|---|---|
| Period leakage policy | `services/data_period_policy.py` |
| Feature row construction | `services/forecast_dataset_service.py`, `scripts/build_forecast_training_rows.py` |
| Calendar | `services/forecast_calendar_service.py` |
| Baselines | `services/demand_forecast_baselines.py` |
| Similar periods | `services/similar_period_service.py` |
| Candidate evaluation/training | `services/demand_forecast_model_service.py`, `scripts/train_demand_forecast_model.py` |
| Supervised refresh | `services/forecast_refresh_service.py`, `scripts/refresh_demand_forecast.py` |
| Replay forecast storage | `services/scada_replay_forecast_service.py` |
| Full-day replay forecast | `services/demo_load_forecast_service.py` |
| Frozen experiment loader | `services/frozen_snapshot_model_service.py` |
| Generation-need probability | `services/risk_probability_engine.py` |
| Recommendation adapter | `services/recommendation_engine.py` |
| Capacity planner | `services/capacity_planning_service.py` |
| Status/evidence | `services/model_status_service.py` |

## Replay and Time

| Function | Files |
|---|---|
| Demo archive/cursor | `services/demo_replay_service.py`, `models/demo_replay.py`, `scripts/seed_demo_replay.py` |
| Active/previous day | `services/present_day_service.py`, `schemas/dashboard_time.py` |
| Snapshot persistence | `services/snapshot_persistence_service.py` |

## Database

| Function | Files |
|---|---|
| Engine | `database/engine.py` |
| Session | `database/session.py` |
| Declarative base | `database/base.py` |
| Model registration | `models/__init__.py` |
| Initialization | `database/init_db.py` |
| Alembic environment | `alembic/env.py`, `alembic.ini` |
| Migrations | `alembic/versions/` |
| Models | `models/calibration.py`, `demand_forecast.py`, `demo_replay.py`, `forecast.py`, `generation.py`, `grid_data.py`, `historical_analysis.py`, `probability_results.py`, `recommendation.py`, `scada.py`, `users.py`, `weather.py` |

## Documentation Sources

| Topic | Existing source |
|---|---|
| Current implementation status | `CURRENT_STATUS.md` |
| Next engineering work | `NEXT_TASKS.md` |
| Local commands | `RUNBOOK.md`, `docs/LAUNCH_AND_DEPLOYMENT.md` |
| Operator behavior | `docs/OperationsGuide.md` |
| SCADA/OSI source semantics | `docs/SCADA_OSI_CONTEXT.md` |
| Required confirmations | `docs/SCADA_OSI_CONFIRMATION_REGISTER.md` |
| OT boundary | `docs/SCADA_OSI_READ_ONLY_SECURITY.md` |
| Math upgrade | `docs/SCADA_WEATHER_MATH_UPGRADE_PLAN.md` |
| June assessment | `docs/JUNE_SCADA_FORECAST_ASSESSMENT.md` |
| July experiment | `docs/LIVE_SCADA_SNAPSHOT_EXPERIMENT.md`, `docs/LIVE_SCADA_SNAPSHOT_TEST_REPORT.md` |

