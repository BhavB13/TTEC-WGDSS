import { useMemo, useState } from "react";
import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";
import type { ChartDataset } from "chart.js";

import type { DashboardTimeContext } from "../types/dashboard";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

const SERIES = [
  { id: "demand", label: "Observed demand", color: "#22d3ee" },
  { id: "tra", label: "Observed TRA", color: "#fbbf24" },
  { id: "spin", label: "Observed system spin", color: "#34d399" },
] as const;

export default function SelectedDayChart({
  context,
  theme = "dark",
}: {
  context: DashboardTimeContext;
  theme?: "dark" | "light";
}) {
  const [visible, setVisible] = useState<Record<string, boolean>>({
    demand: true,
    tra: true,
    spin: false,
  });
  const text = theme === "light" ? "#334155" : "#cbd5e1";
  const grid = theme === "light" ? "rgba(71,85,105,.16)" : "rgba(148,163,184,.12)";
  const points = context.series;
  const data = useMemo(
    () => {
      const datasets: ChartDataset<"line", (number | null)[]>[] = [];
      if (visible.demand) {
        datasets.push({
          label: "Observed demand",
          data: points.map((point) => point.demand_mw ?? null),
          borderColor: "#22d3ee",
          backgroundColor: "#22d3ee",
          borderWidth: 2,
          pointRadius: points.length > 72 ? 0 : 1.5,
          spanGaps: false,
          tension: 0.2,
        });
      }
      if (visible.tra) {
        datasets.push({
          label: "Observed TRA",
          data: points.map((point) => point.generation_tra_mw ?? null),
          borderColor: "#fbbf24",
          backgroundColor: "#fbbf24",
          borderDash: [7, 4],
          borderWidth: 2,
          pointRadius: points.length > 72 ? 0 : 1.5,
          spanGaps: false,
          tension: 0.2,
        });
      }
      if (visible.spin) {
        datasets.push({
          label: "Observed system spin",
          data: points.map((point) => point.spinning_reserve_mw ?? null),
          borderColor: "#34d399",
          backgroundColor: "#34d399",
          borderWidth: 2,
          pointRadius: points.length > 72 ? 0 : 1.5,
          spanGaps: false,
          tension: 0.2,
        });
      }
      return {
        labels: points.map((point) =>
        new Intl.DateTimeFormat("en-TT", {
          hour: "numeric",
        }).format(new Date(point.timestamp)),
        ),
        datasets,
      };
    },
    [context.granularity, points, visible],
  );

  return (
    <section className="flex h-full min-h-0 w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Completed June Day Replay
          </p>
          <h2 className="mt-1 text-base font-semibold text-white">
            Recorded demand, TRA, and system spin
          </h2>
        </div>
        <div className="chart-series-controls" aria-label="Chart series">
          {SERIES.map((series) => (
            <button
              key={series.id}
              type="button"
              aria-pressed={visible[series.id]}
              className={visible[series.id] ? "is-active" : ""}
              onClick={() =>
                setVisible((current) => ({
                  ...current,
                  [series.id]: !current[series.id],
                }))
              }
            >
              <span style={{ backgroundColor: series.color }} />
              {series.label}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-2 min-h-[16rem] flex-1">
        <Line
          data={data}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  afterBody: (items) => {
                    const point = points[items[0]?.dataIndex ?? 0];
                    return point
                      ? [`Quality: ${point.quality_status}`, `Coverage: ${point.completeness_percent.toFixed(0)}%`]
                      : [];
                  },
                },
              },
            },
            scales: {
              x: { ticks: { color: text, maxTicksLimit: 12 }, grid: { display: false } },
              y: {
                ticks: { color: text, callback: (value) => `${value} MW` },
                grid: { color: grid },
              },
            },
          }}
        />
      </div>
    </section>
  );
}
