import type { WeatherData } from "../types/dashboard";

interface CurrentConditionsProps {
  weather: WeatherData;
  className?: string;
}

export default function CurrentConditions({
  weather,
  className = "",
}: CurrentConditionsProps) {
  return (
    <div className={`rounded-lg border border-slate-800 bg-slate-900/80 p-4 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            Current Conditions
          </p>
          <h2 className="mt-1 text-lg font-semibold text-white">
            Live Weather Snapshot
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-medium text-slate-300">
          {weather.rain_severity}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <Metric label="Temperature" value={`${weather.temperature_c.toFixed(1)}°C`} />
        <Metric label="Humidity" value={`${weather.humidity_percent.toFixed(0)}%`} />
        <Metric label="Rainfall" value={`${weather.rainfall_mm_hr.toFixed(1)} mm/hr`} />
        <Metric label="Cloud Cover" value={`${weather.cloud_cover_percent.toFixed(0)}%`} />
        <Metric label="Wind Speed" value={`${weather.wind_speed_kmh.toFixed(1)} km/h`} />
        <Metric label="Heat Index" value={`${weather.heat_index_c.toFixed(1)}°C`} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-400">
        <Badge>{weather.weather_condition}</Badge>
        <Badge>{weather.provider_name}</Badge>
        {weather.timestamp ? <Badge>{new Date(weather.timestamp).toLocaleTimeString()}</Badge> : null}
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white">{value}</p>
    </div>
  );
}

function Badge({ children }: { children: string }) {
  return (
    <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2.5 py-1">
      {children}
    </span>
  );
}
