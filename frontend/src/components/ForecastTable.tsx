import { ForecastData } from "../types/dashboard";

interface ForecastTableProps {
  forecast: ForecastData[];
}

export default function ForecastTable({
  forecast,
}: ForecastTableProps) {
  return (
    <div>
      <h2>Forecast</h2>

      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Temp</th>
            <th>Wind</th>
            <th>Rain</th>
          </tr>
        </thead>

        <tbody>
          {forecast.map((item) => (
            <tr key={item.forecast_timestamp}>
              <td>{item.forecast_timestamp}</td>
              <td>{item.temperature_c}</td>
              <td>{item.wind_speed_kph}</td>
              <td>
                {item.precipitation_probability_percent}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}