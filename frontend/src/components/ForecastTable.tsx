import type { ForecastData } from "../types/dashboard";

interface ForecastTableProps {
  forecast: ForecastData[];
  className?: string;
}

export default function ForecastTable({
  forecast,
  className = "",
}: ForecastTableProps) {
  return (
    <div className={`rounded-lg border border-slate-800 bg-slate-900/80 p-4 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            Forecast
          </p>
          <h2 className="mt-1 text-lg font-semibold text-white">
            Weather Outlook
          </h2>
        </div>
      </div>

      <div className="overflow-hidden rounded-md border border-slate-800">
        <table className="min-w-full divide-y divide-slate-800 text-left text-sm">
          <thead className="bg-slate-950/70 text-slate-300">
            <tr>
              <th className="px-3 py-2 font-medium">Time</th>
              <th className="px-3 py-2 font-medium">Temp</th>
              <th className="px-3 py-2 font-medium">Humidity</th>
              <th className="px-3 py-2 font-medium">Rain</th>
              <th className="px-3 py-2 font-medium">Wind</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 bg-slate-950/40 text-slate-100">
            {forecast.map((item) => (
              <tr key={item.forecast_timestamp}>
                <td className="whitespace-nowrap px-3 py-2 text-slate-300">
                  {new Date(item.forecast_timestamp).toLocaleString()}
                </td>
                <td className="px-3 py-2">{item.temperature_c.toFixed(1)}°C</td>
                <td className="px-3 py-2">{item.humidity_percent.toFixed(0)}%</td>
                <td className="px-3 py-2">{item.precipitation_probability_percent.toFixed(0)}%</td>
                <td className="px-3 py-2">{item.wind_speed_kmh.toFixed(1)} km/h</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
