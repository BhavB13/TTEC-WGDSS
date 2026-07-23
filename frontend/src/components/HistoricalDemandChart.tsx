import { useMemo } from "react";
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Chart } from "react-chartjs-2";

import type { ReplayDashboard } from "../types/dashboard";

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Tooltip, Legend);

export default function HistoricalDemandChart({
  replay,
  theme = "dark",
}: {
  replay: ReplayDashboard;
  theme?: "dark" | "light";
}) {
  const text = theme === "light" ? "#334155" : "#cbd5e1";
  const grid = theme === "light" ? "rgba(71,85,105,.16)" : "rgba(148,163,184,.12)";
  const data = useMemo(
    () => ({
      labels: replay.monthly_history.map((point) => point.month),
      datasets: [
        {
          type: "bar" as const,
          label: "Context average demand",
          data: replay.monthly_history.map((point) => point.average_demand_mw),
          backgroundColor: replay.monthly_history.map((point) =>
            point.data_phase === "REPLAY_SOURCE" ? "rgba(34,211,238,.75)" : "rgba(71,85,105,.7)",
          ),
          borderColor: replay.monthly_history.map((point) =>
            point.data_phase === "REPLAY_SOURCE" ? "#67e8f9" : "#64748b",
          ),
          borderWidth: 1,
          borderRadius: 3,
        },
        {
          type: "line" as const,
          label: "Context monthly peak",
          data: replay.monthly_history.map((point) => point.peak_demand_mw),
          borderColor: "#fb7185",
          backgroundColor: "#fb7185",
          borderWidth: 2,
          pointRadius: 2.5,
          tension: 0.25,
        },
      ],
    }),
    [replay.monthly_history],
  );

  return (
    <section className="flex h-full min-h-0 w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3 shadow-[0_0_34px_rgba(8,145,178,0.08)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">12-Month Simulation Context</p>
          <h2 className="mt-1 text-base font-semibold text-white">Synthetic 2025 context with remapped June SCADA</h2>
        </div>
        <span className="rounded-full border border-cyan-500/25 bg-cyan-500/10 px-2.5 py-1 text-[9px] font-semibold text-cyan-100">
          June = 2026 source replay
        </span>
      </div>
      <div className="mt-2 min-h-[16rem] flex-1">
        <Chart
          type="bar"
          data={data}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: { position: "bottom", labels: { color: text, boxWidth: 12, font: { size: 10 } } },
              tooltip: {
                callbacks: {
                  title: (items) => `${items[0]?.label ?? "Month"} · ${items[0]?.label === "Jun" ? "remapped 2026 SCADA" : "synthetic 2025 context"}`,
                  label: (context) => `${context.dataset.label}: ${Number(context.raw).toFixed(0)} MW`,
                },
              },
            },
            scales: {
              x: { ticks: { color: text }, grid: { display: false } },
              y: { min: 650, max: 1500, ticks: { color: text, callback: (value) => `${value} MW` }, grid: { color: grid } },
            },
          }}
        />
      </div>
    </section>
  );
}
