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

The Version 1 dashboard is operational with live Open-Meteo weather, a three-member Open-Meteo/MET Norway/NOAA GFS hourly forecast consensus, provider fallback, simulated grid data, Leaflet operational layers, rule-based recommendations, persisted historical snapshots, and imported SCADA calibration profiles.

See `docs/OperationsGuide.md` for startup, migration, import, testing, and deployment instructions. See `docs/ExternalServices.md` for the no-cost provider matrix, quotas, licensing boundary, and optional paid alternatives.

Repository Structure

Backend:

- `api/`
- `core/`
- `models/`
- `providers/`
- `schemas/`
- `services/`

Documentation:

- `docs/DatabaseDesign.md`
- `docs/RecommendationEngine.md`
- `docs/APIContract.md`
- `docs/BackendArchitecture.md`
- `docs/FrontendArchitecture.md`

Future Enhancements

- Demand forecasting
- Historical analytics
- Machine learning recommendations
- Real-time SCADA integration
- Generation asset visualization
