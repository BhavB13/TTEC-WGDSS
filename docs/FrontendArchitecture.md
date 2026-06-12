Frontend Architecture
Technology Stack

React
TypeScript
Vite
Leaflet
OpenStreetMap
Esri World Imagery


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
Esri World Imagery

Weather Layers:

Temperature
Wind
Precipitation
Clouds

Future Layers:

Generation Stations
Substations
Transmission Lines
Load Centers


API Integration
Backend Endpoints:

GET /health
GET /recommendations

Future:

GET /weather/current
GET /weather/forecast
GET /grid/status

