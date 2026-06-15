import { WeatherData } from "../types/dashboard";

interface WeatherCardProps {
  weather: WeatherData;
}

export default function WeatherCard({
  weather,
}: WeatherCardProps) {
  return (
    <div>
      <h2>Current Weather</h2>

      <p>Temperature: {weather.temperature_c}°C</p>
      <p>Humidity: {weather.humidity_percent}%</p>
      <p>Wind Speed: {weather.wind_speed_kph} km/h</p>
      <p>Pressure: {weather.pressure_hpa} hPa</p>
    </div>
  );
}
