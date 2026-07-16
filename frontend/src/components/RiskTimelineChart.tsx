import { useMemo } from "react";
import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  type ChartOptions,
} from "chart.js";
import { Line } from "react-chartjs-2";

import type { ProbabilityData, RiskHorizon } from "../types/dashboard";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

interface RiskTimelineChartProps {
  probability: ProbabilityData;
  theme?: "dark" | "light";
  className?: string;
}

export default function RiskTimelineChart({
  probability,
  theme = "dark",
  className = "",
}: RiskTimelineChartProps) {
  const profile = useMemo(
    () =>
      [...(probability.risk_profile ?? [])]
        .filter(
          (point) =>
            point.horizon_minutes > 0 &&
            point.horizon_minutes <= 360 &&
            Number.isFinite(point.probability),
        )
        .sort((left, right) => left.horizon_minutes - right.horizon_minutes),
    [probability.risk_profile],
  );
  const textColor = theme === "light" ? "#334155" : "#cbd5e1";
  const gridColor =
    theme === "light" ? "rgba(71,85,105,0.16)" : "rgba(148,163,184,0.13)";
  const labels = profile.map(formatHorizon);
  const chartData = useMemo(
    () => ({
      labels,
      datasets: [
        {
          label: "_lower",
          data: profile.map((point) => point.forecast_lower_mw),
          borderColor: "rgba(34,211,238,0)",
          backgroundColor: "rgba(34,211,238,0)",
          borderWidth: 0,
          pointRadius: 0,
          tension: 0.25,
        },
        {
          label: "Forecast uncertainty band",
          data: profile.map((point) => point.forecast_upper_mw),
          borderColor: "rgba(34,211,238,0.22)",
          backgroundColor: "rgba(34,211,238,0.13)",
          borderWidth: 1,
          pointRadius: 0,
          fill: "-1",
          tension: 0.25,
        },
        {
          label: "Forecast demand",
          data: profile.map((point) => point.forecast_demand_mw),
          borderColor: "#22d3ee",
          backgroundColor: "#22d3ee",
          borderWidth: 2.5,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.25,
        },
        {
          label: "Safe online capacity",
          data: profile.map((point) => point.safe_online_capacity_mw),
          borderColor: "#fbbf24",
          backgroundColor: "#fbbf24",
          borderWidth: 2,
          borderDash: [7, 5],
          pointRadius: 2,
          pointHoverRadius: 4,
          tension: 0.15,
        },
      ],
    }),
    [labels, profile],
  );
  const options = useMemo<ChartOptions<"line">>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      layout: { padding: { top: 2, right: 4, bottom: 0, left: 0 } },
      plugins: {
        legend: {
          position: "bottom",
          align: "start",
          labels: {
            color: textColor,
            boxWidth: 11,
            boxHeight: 3,
            padding: 10,
            font: { size: 10 },
            filter: (item) => item.text !== "_lower",
          },
        },
        tooltip: {
          backgroundColor: "rgba(2,6,23,0.96)",
          borderColor: "rgba(34,211,238,0.3)",
          borderWidth: 1,
          titleColor: "#f8fafc",
          bodyColor: "#e2e8f0",
          padding: 10,
          filter: (item) => item.datasetIndex !== 0,
          callbacks: {
            title: (items) => {
              const point = profile[items[0]?.dataIndex ?? 0];
              return point ? formatPointTime(point) : "Risk horizon";
            },
            label: (context) => {
              const point = profile[context.dataIndex];
              if (!point) {
                return "";
              }
              if (context.datasetIndex === 1) {
                const confidenceLevel = Math.round(
                  (point.confidence_level ?? 0.9) * 100,
                );
                return `${confidenceLevel}% band: ${point.forecast_lower_mw.toFixed(1)}–${point.forecast_upper_mw.toFixed(1)} MW`;
              }
              if (context.datasetIndex === 2) {
                return [
                  `Forecast: ${point.forecast_demand_mw.toFixed(1)} MW`,
                  `Shortfall probability: ${(point.probability * 100).toFixed(1)}%`,
                ];
              }
              return `Safe capacity: ${point.safe_online_capacity_mw.toFixed(1)} MW`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 10 } },
        },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 10 },
            callback: (value) => `${Number(value).toFixed(0)} MW`,
          },
        },
      },
    }),
    [gridColor, profile, textColor],
  );

  return (
    <section
      className={`flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300">
            Six-Hour Risk Timeline
          </p>
          <h2 className="mt-0.5 truncate text-sm font-semibold text-white">
            Demand, uncertainty, and safe capacity
          </h2>
        </div>
        <span className="shrink-0 rounded-full border border-cyan-400/25 bg-cyan-500/10 px-2 py-1 text-[9px] font-semibold text-cyan-100">
          Peak {formatPeakHorizon(probability.peak_risk_horizon_minutes)}
        </span>
      </div>

      {profile.length ? (
        <>
          <div className="mt-1.5 min-h-[5.75rem] flex-1">
            <Line data={chartData} options={options} />
          </div>
          <div
            className="mt-1.5 grid gap-1.5"
            style={{ gridTemplateColumns: `repeat(${Math.min(profile.length, 5)}, minmax(0, 1fr))` }}
          >
            {profile.slice(0, 5).map((point) => (
              <div
                key={`${point.horizon_minutes}-${point.forecast_timestamp ?? "risk"}`}
                className="min-w-0 rounded-lg border border-slate-800 bg-slate-950/55 px-1.5 py-1 text-center"
              >
                <p className="truncate text-[9px] uppercase tracking-[0.1em] text-slate-400">
                  {formatHorizon(point)}
                </p>
                <p className="mt-0.5 text-xs font-semibold text-white">
                  {(point.probability * 100).toFixed(1)}%
                </p>
                <p
                  className={`truncate text-[9px] ${
                    point.reserve_adjusted_headroom_mw >= 0
                      ? "text-emerald-300"
                      : "text-rose-300"
                  }`}
                >
                  {point.reserve_adjusted_headroom_mw >= 0 ? "+" : ""}
                  {point.reserve_adjusted_headroom_mw.toFixed(0)} MW
                </p>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-center text-sm text-slate-400">
          Per-horizon risk evidence is unavailable for this snapshot.
        </div>
      )}
    </section>
  );
}

function formatHorizon(point: RiskHorizon): string {
  if (point.horizon_minutes < 60) {
    return `+${point.horizon_minutes}m`;
  }
  const hours = point.horizon_minutes / 60;
  return Number.isInteger(hours) ? `+${hours}h` : `+${hours.toFixed(1)}h`;
}

function formatPeakHorizon(minutes?: number | null): string {
  if (minutes == null) {
    return "--";
  }
  return minutes < 60 ? `+${minutes}m` : `+${minutes / 60}h`;
}

function formatPointTime(point: RiskHorizon): string {
  if (!point.forecast_timestamp) {
    return formatHorizon(point);
  }
  const date = new Date(point.forecast_timestamp);
  if (Number.isNaN(date.getTime())) {
    return formatHorizon(point);
  }
  return `${formatHorizon(point)} · ${new Intl.DateTimeFormat("en-TT", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Port_of_Spain",
  }).format(date)}`;
}
