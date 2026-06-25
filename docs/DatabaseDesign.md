Database Design
weather_observations
Stores current weather observations from weather providers.
Fields:

id
timestamp
temperature_c
humidity_percent
wind_speed_kph
wind_direction_deg
pressure_hpa
precipitation_mm
provider_name
created_at


forecasts
Stores forecast weather data.
Fields:

id
forecast_timestamp
temperature_c
humidity_percent
wind_speed_kph
wind_direction_deg
precipitation_probability_percent
precipitation_mm
confidence_score
provider_name
created_at


generation_units
Stores generation unit operational status.
Fields:

id
station_name
unit_name
fuel_type
available_capacity_mw
current_output_mw
status
is_dispatchable
last_updated
created_at


recommendations
Stores recommendation engine outputs.
Fields:

id
probability_score
recommendation
reason
created_at

