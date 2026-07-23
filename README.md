T&TEC Weather-Based Generation Decision Support System

Overview

The T&TEC Weather-Based Generation Decision Support System is a decision support platform designed to assist generation operators in evaluating weather conditions and grid status when making generation startup and operational decisions.

The system combines:

- Weather observations
- Weather forecasts
- Generation unit status
- Grid conditions

to produce operational recommendations with associated probability scores and reasoning.

Objectives

- Improve operational awareness
- Support generation startup decisions
- Provide weather-driven recommendations
- Visualize weather and grid conditions
- Provide a foundation for future SCADA integration

Technology Stack

Backend:

- Python
- FastAPI
- SQLAlchemy 2.0
- PostgreSQL

Frontend:

- React
- TypeScript
- Vite
- Leaflet

Weather Providers

Primary:

- Open-Meteo Best Match

Forecast cross-checks:

- MET Norway Locationforecast
- NOAA GFS through Open-Meteo's model endpoint

Fallback:

- Open-Meteo GFS. WeatherAPI's $0 plan is available only through explicit opt-in.

Architecture

Frontend
↓
FastAPI API Layer
↓
Service Layer
↓
Provider Layer
↓
Database Layer

Current Project Status

The dashboard now includes a realistic production-system demonstration mode. It
uses an immutable 12-month hourly SCADA/weather archive, replays June as a
persisted simulation feed, preserves the other eleven months for analytics,
and exposes playback controls, full-day demand forecasts, six-hour weather,
generation, demand, capacity, and reserve measurements. The bundled dataset is
deterministic synthetic demonstration data and is never presented as live T&TEC
SCADA telemetry.

The existing live weather providers, Leaflet operational map and overlays,
historical SCADA CSV pipeline, calibration profiles, forecasting services, and
risk engine remain available. See `docs/DEMO_REPLAY.md` for replay architecture,
provenance, forecast leakage controls, and the production replacement path.

The SCADA pipeline now accepts a filename-independent ZIP containing the PTL
generation-total proxy, Temperature, corrected Spin, TA, and TRA exports. It resamples irregular intervals by
timestamp overlap, compares chronological baselines with four ML families for
1h/2h/6h demand, and can overlay the historical June source at the simulated
cursor. This remains prototype replay data and is never labelled live SCADA.

The v3 forecast profile also evaluates Extra Trees, leakage-safe historical
similar-period matching, and ML/similarity blends. It models Trinidad
weekday/weekend/holiday and wet/dry-season context, then returns calibrated
confidence bounds, comparable historical periods, temperature/load
correlation, contributing factors, and horizon-specific accuracy metrics.

The six-hour pipeline now reconciles Open-Meteo Best Match, MET Norway, and
Open-Meteo NOAA GFS by timestamp and field. June synchronizes to the current
Trinidad clock, demand forecasts use validated weather features, and dispatch
guidance distinguishes the 30 MW fast-start set from 60-120 MW heavy capacity.
Live temperature uses a ten-point Trinidad demand-exposure weighted aggregate,
with residential and commercial load centers weighted above the Point Lisas
industrial reference. The weights are explicitly prototype policy and must be
confirmed or replaced with T&TEC-approved load-zone factors before operational
use.
See `docs/FORECAST_DISPATCH_UPGRADE.md` and
`docs/HISTORICAL_DATA_IMPORTS.md`.

See `docs/LAUNCH_AND_DEPLOYMENT.md` for manual, one-command, and button-style
startup instructions. See `docs/OperationsGuide.md` for migration, import,
testing, and operational guidance. See `docs/ExternalServices.md` for the
no-cost provider matrix, quotas, licensing boundary, and optional paid
alternatives.

Repository Structure

Backend:

- `api/`
- `core/`
- `models/`
- `providers/`
- `schemas/`
- `services/`

Documentation:

- `docs/SCADA_OSI_CONTEXT.md`
- `docs/SCADA_OSI_CONFIRMATION_REGISTER.md`
- `docs/SCADA_OSI_READ_ONLY_SECURITY.md`
- `docs/DatabaseDesign.md`
- `docs/RecommendationEngine.md`
- `docs/APIContract.md`
- `docs/BackendArchitecture.md`
- `docs/FrontendArchitecture.md`

Future Enhancements

- Approved read-only historian/SCADA integration
- Multi-season validation using approved T&TEC historical exports
- Production model registry and monitored scheduled retraining
- Generation asset visualization
