import type { ReactNode } from "react";
import type { WeatherData } from "../types/dashboard";
import {
  getTemperatureAggregationSummary,
  getTemperatureMetricLabel,
} from "../utils/weatherTemperature";

interface CurrentConditionsProps {
  weather: WeatherData;
  qualityStatus?: string;
  className?: string;
}

export default function CurrentConditions({
  weather,
  qualityStatus,
  className = "",
}: CurrentConditionsProps) {
  const temperatureSummary = getTemperatureAggregationSummary(
    weather.weather_aggregation ?? weather.temperature_aggregation,
  );

  return (
    <div className={`flex h-full w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Current Conditions
          </p>
          <h2 className="mt-1 text-[0.92rem] font-semibold leading-tight text-white">
            Current Weather Conditions
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2.5 py-1 text-[11px] font-medium text-slate-300">
          {weather.rain_severity}
        </span>
      </div>

      <div className="grid flex-1 grid-cols-1 gap-1.5 text-sm sm:grid-cols-2">
        <Metric
          label={getTemperatureMetricLabel(weather)}
          value={`${weather.temperature_c.toFixed(1)}°C`}
        />
        <Metric label="Humidity" value={`${weather.humidity_percent.toFixed(0)}%`} />
        <Metric label="Rainfall" value={`${weather.rainfall_mm_hr.toFixed(1)} mm/hr`} />
        <Metric label="Cloud Cover" value={`${weather.cloud_cover_percent.toFixed(0)}%`} />
        <Metric label="Wind Speed" value={`${weather.wind_speed_kmh.toFixed(1)} km/h`} />
        <Metric label="Heat Index" value={`${weather.heat_index_c.toFixed(1)}°C`} />
      </div>

      <div className="mt-2 flex flex-wrap justify-center gap-2 text-[11px] text-slate-400">
        <Badge label={weather.weather_condition} />
        <Badge label={weather.provider_name} />
        {qualityStatus ? <Badge label={qualityStatus} /> : null}
        {temperatureSummary ? <Badge label={temperatureSummary} /> : null}
        {weather.timestamp ? (
          <Badge label={new Date(weather.timestamp).toLocaleTimeString()} />
        ) : null}
      </div>
      <a
        className="mt-1 text-center text-[10px] text-slate-500 hover:text-cyan-300"
        href="https://creativecommons.org/licenses/by/4.0/"
        target="_blank"
        rel="noreferrer"
      >
        Weather data licensed under CC BY 4.0
      </a>
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
    <div className="flex min-h-[3.5rem] flex-col items-center justify-center rounded-lg border border-slate-800 bg-slate-950/60 px-2 py-1.5 text-center shadow-inner shadow-black/20">
      <p className="text-[10px] uppercase tracking-[0.12em] text-slate-400">{label}</p>
      <p className="mt-1 min-w-0 break-words text-[0.84rem] font-semibold leading-snug text-white">{value}</p>
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
