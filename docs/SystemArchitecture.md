System Architecture
Overview
The T&TEC Weather-Based Generation Decision Support System is a layered application designed to combine weather data and grid operational data to support generation decision-making.

High-Level Architecture
Frontend (React + TypeScript)
↓
FastAPI Backend
↓
Service Layer
↓
Provider Layer
↓
Database

Frontend Layer
Technologies:

React
TypeScript
Vite
Leaflet

Responsibilities:

Display weather conditions
Display forecasts
Display grid status
Display recommendations
Display weather map layers


API Layer
Technology:

FastAPI

Responsibilities:

Expose REST endpoints
Validate requests
Return structured responses

Current Endpoints:

GET /api/dashboard/snapshot
GET /api/v1/health
GET /api/v1/recommendations
GET /api/v1/weather/current
GET /api/v1/weather/forecast
GET /api/v1/grid/status


Service Layer
Responsibilities:

Coordinate business logic
Aggregate provider data
Execute recommendation logic

Components:

WeatherService
GridService
RecommendationEngine


Provider Layer
Weather Providers
Interface:

WeatherProvider

Implementations:

OpenMeteoProvider
MetNorwayProvider
WeatherAPIProvider

Grid Providers
Interface:

GridProvider

Implementations:

MockGridProvider

Future:

SCADAProvider


Database Layer
Technology:

PostgreSQL
SQLAlchemy 2.0

Tables:

weather_observations
forecasts
generation_units
recommendations


Recommendation Flow
Weather Data



Forecast Data



Generation Status
↓
Recommendation Engine
↓
Probability Score
↓
Recommendation
↓
Dashboard Display

Future Architecture
Frontend
↓
FastAPI
↓
Service Layer
↓
Provider Layer
├── Open-Meteo
├── MET Norway
├── NOAA GFS
├── WeatherAPI (optional $0 fallback, disabled by default)
└── SCADA
↓
PostgreSQL
↓
Analytics & Reporting
