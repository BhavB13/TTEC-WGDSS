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
} from "chart.js";
import { Line } from "react-chartjs-2";

import type { ReplayDashboard } from "../types/dashboard";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

export default function ReplayLoadChart({
  replay,
  theme = "dark",
  compact = false,
}: {
  replay: ReplayDashboard;
  theme?: "dark" | "light";
  compact?: boolean;
}) {
  const text = theme === "light" ? "#334155" : "#cbd5e1";
  const grid = theme === "light" ? "rgba(71,85,105,.16)" : "rgba(148,163,184,.12)";
  const points = replay.full_day_load_forecast;
  const data = useMemo(
    () => ({
      labels: points.map((point) => formatHour(point.timestamp)),
      datasets: [
        {
          label: "Forecast demand",
          data: points.map((point) => point.forecast_demand_mw),
          borderColor: "#22d3ee",
          backgroundColor: "rgba(34,211,238,.10)",
          fill: true,
          borderWidth: 2,
          pointRadius: compact ? 0 : 1.8,
          tension: 0.3,
        },
        {
          label: "Historical hourly average",
          data: points.map((point) => point.historical_average_mw),
          borderColor: "#64748b",
          borderDash: [5, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
        },
        {
          label: "Revealed actual",
          data: points.map((point) => point.actual_demand_mw ?? null),
          borderColor: "#34d399",
          backgroundColor: "#34d399",
          borderWidth: 2.5,
          pointRadius: 2,
          spanGaps: false,
          tension: 0.2,
        },
      ],
    }),
    [compact, points],
  );

  return (
    <section className="flex h-full min-h-0 w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-2.5 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">Full-Day Load Forecast</p>
          <h2 className="mt-0.5 text-sm font-semibold text-white">Forecast vs historical baseline and revealed demand</h2>
        </div>
        <span className="rounded-full border border-cyan-500/25 bg-cyan-500/10 px-2 py-1 text-[9px] font-semibold text-cyan-100">
          Peak {replay.summary.current_day_peak_forecast_mw.toFixed(0)} MW
        </span>
      </div>
      <div className="mt-1.5 min-h-[12rem] flex-1">
        <Line
          data={data}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: { position: "bottom", labels: { color: text, boxWidth: 12, font: { size: 9 } } },
              tooltip: { callbacks: { label: (context) => `${context.dataset.label}: ${Number(context.raw).toFixed(0)} MW` } },
            },
            scales: {
              x: { ticks: { color: text, maxTicksLimit: 12, font: { size: 9 } }, grid: { color: grid } },
              y: { min: 650, max: 1500, ticks: { color: text, callback: (value) => `${value} MW`, font: { size: 9 } }, grid: { color: grid } },
            },
          }}
        />
      </div>
    </section>
  );
}

function formatHour(value: string): string {
  return new Intl.DateTimeFormat("en-TT", {
    hour: "numeric",
    hour12: true,
    timeZone: "America/Port_of_Spain",
  }).format(new Date(value));
}
