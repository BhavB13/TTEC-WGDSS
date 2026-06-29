Frontend Architecture
Technology Stack

React
TypeScript
Vite
Leaflet
OpenStreetMap
NASA GIBS Blue Marble


Dashboard Layout
Header
Displays:

Application Name
Last Update Time
System Status


Weather Panel
Displays:

Current Temperature
Humidity
Wind Speed
Wind Direction
Pressure
Precipitation


Forecast Panel
Displays:

Forecast Temperature
Forecast Wind Speed
Forecast Precipitation
Confidence Score


Grid Status Panel
Displays:

Total Available Capacity
Current Generation
Reserve Margin
Grid Status


Recommendation Panel
Displays:

Recommendation
Probability Score
Reasoning

Examples:

START
MONITOR
NO_ACTION


Map Panel
Framework:

Leaflet

Base Layers:

OpenStreetMap
NASA GIBS Blue Marble

Weather Layers:

NASA GPM IMERG precipitation
NASA GOES-East cloud systems

Future Layers:

Generation Stations
Substations
Transmission Lines
Load Centers


API Integration
Backend Endpoints:

GET /api/dashboard/snapshot
GET /api/v1/health
GET /api/v1/recommendations
GET /api/v1/weather/current
GET /api/v1/weather/forecast
GET /api/v1/grid/status

