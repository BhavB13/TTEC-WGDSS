import { useMemo } from "react";
import {
  CategoryScale,
  Chart as ChartJS,
  LineElement,
  Legend,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";

import type { GridStatus, ProbabilityData } from "../types/dashboard";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);

interface DemandForecastChartProps {
  gridStatus: GridStatus;
  probability: ProbabilityData;
  className?: string;
}

export default function DemandForecastChart({
  gridStatus,
  probability,
  className = "",
}: DemandForecastChartProps) {
  const data = useMemo(
    () => ({
      labels: ["Current", "30m Forecast", "60m Forecast"],
      datasets: [
        {
          label: "Demand (MW)",
          data: [
            gridStatus.current_demand_mw,
            probability.forecast_demand_30m,
            probability.forecast_demand_60m,
          ],
          backgroundColor: ["rgba(34, 211, 238, 0.55)", "rgba(59, 130, 246, 0.55)", "rgba(244, 114, 182, 0.55)"],
          borderColor: ["rgba(34, 211, 238, 1)", "rgba(59, 130, 246, 1)", "rgba(244, 114, 182, 1)"],
          borderWidth: 1,
        },
      ],
    }),
    [gridStatus.current_demand_mw, probability.forecast_demand_30m, probability.forecast_demand_60m],
  );

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false,
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#cbd5e1",
          },
          grid: {
            color: "rgba(148, 163, 184, 0.14)",
          },
        },
        y: {
          beginAtZero: true,
          ticks: {
            color: "#cbd5e1",
          },
          grid: {
            color: "rgba(148, 163, 184, 0.14)",
          },
        },
      },
    }),
    [],
  );

  return (
    <div className={`flex h-full w-full min-w-0 flex-col rounded-2xl border border-cyan-500/15 bg-slate-900/80 p-3.5 shadow-[0_0_34px_rgba(8,145,178,0.08)] ${className}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Demand Forecast
          </p>
          <h2 className="mt-1 text-[1.05rem] font-semibold text-white">
            Current and Near-Term Load
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 px-2.5 py-1 text-[11px] font-medium text-slate-300">
          Chart.js
        </span>
      </div>

      <div className="min-h-[clamp(12rem,24vh,16rem)] flex-1 w-full min-w-0">
        <Line
          data={data}
          options={{
            ...options,
            elements: {
              line: {
                tension: 0.35,
                borderWidth: 2,
              },
              point: {
                radius: 4,
                hoverRadius: 6,
              },
            },
          }}
        />
      </div>
    </div>
  );
}
