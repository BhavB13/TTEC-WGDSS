import type { ReactNode } from "react";
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
    <div className={`flex h-full w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3.5 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Current Conditions
          </p>
          <h2 className="mt-1 text-[1.05rem] font-semibold text-white">
            Current Weather Conditions
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2.5 py-1 text-[11px] font-medium text-slate-300">
          {weather.rain_severity}
        </span>
      </div>

      <div className="grid flex-1 grid-cols-1 gap-2.5 text-sm sm:grid-cols-2">
        <Metric label="Temperature" value={`${weather.temperature_c.toFixed(1)}°C`} />
        <Metric label="Humidity" value={`${weather.humidity_percent.toFixed(0)}%`} />
        <Metric label="Rainfall" value={`${weather.rainfall_mm_hr.toFixed(1)} mm/hr`} />
        <Metric label="Cloud Cover" value={`${weather.cloud_cover_percent.toFixed(0)}%`} />
        <Metric label="Wind Speed" value={`${weather.wind_speed_kmh.toFixed(1)} km/h`} />
        <Metric label="Heat Index" value={`${weather.heat_index_c.toFixed(1)}°C`} />
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-400">
        <Badge label={weather.weather_condition} />
        <Badge label={weather.provider_name} />
        {weather.timestamp ? (
          <Badge label={new Date(weather.timestamp).toLocaleTimeString()} />
        ) : null}
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
    <div className="flex min-h-[4.25rem] flex-col justify-center rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-2.5 shadow-inner shadow-black/20">
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-1 text-[0.92rem] font-semibold text-white">{value}</p>
    </div>
  );
}

function Badge({ label }: { label: ReactNode }) {
  return (
    <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2.5 py-1">
      {label}
    </span>
  );
}
