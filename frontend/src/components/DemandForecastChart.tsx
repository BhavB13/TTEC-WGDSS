import { useMemo } from "react";
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
} from "chart.js";
import { Bar } from "react-chartjs-2";

import type { GridStatus, ProbabilityData } from "../types/dashboard";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

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
    <div className={`rounded-lg border border-slate-800 bg-slate-900/80 p-4 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            Demand Forecast
          </p>
          <h2 className="mt-1 text-lg font-semibold text-white">
            Current and Near-Term Load
          </h2>
        </div>
        <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-medium text-slate-300">
          Chart.js
        </span>
      </div>

      <div className="h-72">
        <Bar data={data} options={options} />
      </div>
    </div>
  );
}
