T&TEC Weather-Based Generation Decision Support System
Overview
The T&TEC Weather-Based Generation Decision Support System is a decision support platform designed to assist generation operators in evaluating weather conditions and grid status when making generation startup and operational decisions.
The system combines:

Weather observations
Weather forecasts
Generation unit status
Grid conditions

to produce operational recommendations with associated probability scores and reasoning.

Objectives

Improve operational awareness
Support generation startup decisions
Provide weather-driven recommendations
Visualize weather and grid conditions
Provide a foundation for future SCADA integration


Technology Stack
Backend

Python
FastAPI
SQLAlchemy 2.0
PostgreSQL

Frontend

React
TypeScript
Vite
Leaflet

Weather Providers
Primary:

Open-Meteo

Fallback:

WeatherAPI


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
Completed

Project Initialization
FastAPI Foundation
Database Models
Provider Architecture
Recommendation Engine
API Layer
Service Layer

Planned

Real Weather Integration
Dashboard Development
Leaflet Weather Map
SCADA Integration
Production Deployment


Repository Structure
backend/

api/
core/
models/
providers/
schemas/
services/

docs/

DatabaseDesign.md
RecommendationEngine.md
APIContract.md
BackendArchitecture.md
FrontendArchitecture.md


Future Enhancements

Demand Forecasting
Historical Analytics
Machine Learning Recommendations
Real-Time SCADA Integration
Generation Asset Visualization

